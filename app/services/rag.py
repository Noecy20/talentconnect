"""Assistant personnel (RAG) : chaque utilisateur alimente sa base de connaissances
(profil, CV, textes, FAQ, documents). Une question est découpée, on retrouve
les passages les plus pertinents (TF-IDF, multilingue grâce aux n-grammes de
caractères) puis on répond :
  - avec Claude si une clé API est configurée (réponse rédigée et sourcée) ;
  - sinon par extraction des phrases les plus pertinentes.
Évolution possible : remplacer TF-IDF par des embeddings stockés dans pgvector."""
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..i18n import t
from ..models import Assistant, Sponsorship, Job
from . import llm


def chunk(text, size=700, overlap=120):
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if len(text) <= size:
        return [text] if text else []
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return out


def profile_documents(user):
    """Génère automatiquement des documents à partir du profil de l'utilisateur."""
    docs = []
    name = user.full_name
    if user.role == "candidate" and user.candidate:
        cp = user.candidate
        langs = ", ".join(f"{l.get('name')} ({l.get('level', '')})" if isinstance(l, dict) else str(l) for l in (cp.languages or []))
        docs.append(("Profil", f"{name} — {cp.headline}. Filière : {cp.field}. Niveau d'études : {cp.education_level}. "
                               f"Expérience : {cp.years_experience} an(s). Ville : {user.city}. "
                               f"Poste recherché : {cp.desired_position}. Résumé : {cp.summary}"))
        if cp.skills:
            docs.append(("Compétences", f"Compétences de {name} : " + ", ".join(cp.skills)))
        if cp.soft_skills:
            docs.append(("Soft skills", f"Qualités humaines (soft skills) de {name} : " + ", ".join(cp.soft_skills)))
        if langs:
            docs.append(("Langues", f"Langues parlées par {name} : {langs}"))
        cv = cp.cv_data or {}
        for e in cv.get("exp", []) or []:
            docs.append(("Expérience", f"Expérience : {e.get('title')} chez {e.get('org')} ({e.get('date')}). "
                                       + " ".join(e.get("bul", []) or [])))
        for e in cv.get("edu", []) or []:
            docs.append(("Formation", f"Formation : {e.get('title')} — {e.get('sub')} ({e.get('period')})"))
        for p in cv.get("projets", []) or []:
            docs.append(("Projet", f"Projet : {p.get('title')} — {p.get('desc')}"))
        for c in cv.get("cert", []) or []:
            docs.append(("Certification", f"Certification : {c.get('title')} — {c.get('meta')}"))
        for s in Sponsorship.query.filter_by(candidate_id=user.id, status="active").all():
            sp = s.sponsor
            docs.append(("Parrainage", f"Recommandation de {sp.full_name} ({sp.sponsor.position if sp.sponsor else ''}, "
                                       f"{s.organization}) — relation : {s.relation}, période : {s.period}. {s.recommendation}"))
    elif user.role == "recruiter" and user.recruiter and user.recruiter.company:
        co = user.recruiter.company
        docs.append(("Entreprise", f"{co.name} — secteur : {co.sector}. Taille : {co.size}. Ville : {co.city}. "
                                   f"Site : {co.website}. {co.description}"))
        for j in Job.query.filter_by(company_id=co.id, status="open").all():
            docs.append(("Offre", f"Offre « {j.title} » ({j.contract_type}, {j.city}) : {j.description} "
                                  f"Compétences recherchées : {', '.join(j.skills or [])}"))
    elif user.role == "sponsor" and user.sponsor:
        sp = user.sponsor
        docs.append(("Parrain", f"{name} — {sp.position} chez {sp.organization}. {sp.bio}"))
    return docs


def corpus(assistant: Assistant):
    items = []
    if assistant.include_profile:
        for title, text in profile_documents(assistant.owner):
            for c in chunk(text):
                items.append({"title": title, "text": c})
    for d in assistant.documents.all():
        for c in chunk(d.content):
            items.append({"title": d.title or d.source, "text": c})
    return items


def retrieve(assistant, question, k=4):
    items = corpus(assistant)
    if not items:
        return []
    texts = [i["text"] for i in items]
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
    m = vec.fit_transform(texts + [question])
    sims = cosine_similarity(m[-1], m[:-1]).ravel()
    ranked = sorted(zip(sims, items), key=lambda x: -x[0])[:k]
    return [dict(i, score=round(float(s), 3)) for s, i in ranked if s > 0.04]


def _extractive(question, passages, owner_name):
    if not passages:
        return t("Je n'ai pas encore d'information à ce sujet. {name} peut enrichir ma base de connaissances.", name=owner_name)
    sents = []
    for p in passages:
        sents += [s.strip() for s in re.split(r"(?<=[.!?])\s+", p["text"]) if len(s.strip()) > 20]
    if not sents:
        return passages[0]["text"]
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
    m = vec.fit_transform(sents + [question])
    sims = cosine_similarity(m[-1], m[:-1]).ravel()
    best = [sents[i] for i in sims.argsort()[::-1][:3]]
    return t("Voici ce que je sais :") + "\n• " + "\n• ".join(best)


def answer(assistant, question, asker=None, history=None):
    passages = retrieve(assistant, question)
    owner = assistant.owner
    context = "\n\n".join(f"[{i + 1}] ({p['title']}) {p['text']}" for i, p in enumerate(passages))
    system = (
        f"Tu es « {assistant.name} », l'assistant personnel de {owner.full_name} sur TalentConnect, "
        f"une plateforme qui connecte talents et entreprises. Réponds uniquement à partir du CONTEXTE fourni ; "
        f"si l'information n'y est pas, dis-le simplement et propose de contacter {owner.full_name}. "
        f"Ne révèle jamais de numéro de téléphone ni d'adresse e-mail. Réponds dans la langue de la question, "
        f"de façon concise et chaleureuse. {assistant.persona or ''}"
    )
    hist = ""
    if history:
        hist = "\n".join(f"Q: {h.question}\nR: {h.answer}" for h in history[-4:]) + "\n\n"
    prompt = f"{hist}CONTEXTE :\n{context or '(vide)'}\n\nQUESTION : {question}"
    text = llm.generate(system, prompt, max_tokens=600)
    if not text:
        text = _extractive(question, passages, owner.full_name)
    return text, [{"title": p["title"], "score": p["score"]} for p in passages]
