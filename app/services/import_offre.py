"""Import d'une offre déjà publiée sur le site web de l'entreprise.

Le recruteur colle le lien de son annonce : on lit la page publique et on pré-remplit
le formulaire de TalentConnect (intitulé, description, contrat, lieu, salaire, date limite,
niveau d'études, expérience, compétences). Il relit et corrige avant de publier.

Ordre de lecture :
1. l'annonce structurée schema.org « JobPosting » (le format utilisé par Google for Jobs,
   présent sur la plupart des sites carrière et des logiciels de recrutement) ;
2. à défaut, le titre, la description et le texte principal de la page.
"""
import re
import urllib.request
from html import unescape

from ..ia.orientation import BASE_SKILLS
from ..ia.scores import norm
from .suivi import _safe_url, import_from_url

SOFT_SKILLS = ["Communication", "Leadership", "Travail d'équipe", "Rigueur", "Autonomie", "Adaptabilité",
               "Organisation", "Esprit d'analyse", "Créativité", "Sens du service", "Gestion du stress"]
LANGUES = ["Français", "Anglais", "Espagnol", "Allemand", "Portugais", "Arabe", "Chinois"]

# employmentType schema.org / mots courants -> codes de TalentConnect
CONTRATS = [("intern", "internship"), ("stage", "internship"), ("alternan", "alternance"), ("apprenti", "alternance"),
            ("freelance", "freelance"), ("contractor", "freelance"), ("independant", "freelance"),
            ("temporary", "cdd"), ("cdd", "cdd"), ("duree determinee", "cdd"), ("interim", "interim"),
            ("volunteer", "volunteer"), ("benevol", "volunteer"), ("full_time", "cdi"), ("full-time", "cdi"),
            ("cdi", "cdi"), ("duree indeterminee", "cdi"), ("part_time", "cdd")]


def _contrat(texte):
    n = norm(texte).replace("_", " ")
    for cle, code in CONTRATS:
        if norm(cle).replace("_", " ") in n:
            return code
    return ""


def _niveau_etudes(texte):
    n = norm(texte)
    m = re.search(r"bac\s*\+\s*(\d)", n.replace("bac+", "bac +"))
    if m:
        return {"2": "bac2", "3": "bac3", "4": "bac4", "5": "bac5"}.get(m.group(1), "bac5" if int(m.group(1)) > 5 else "bac")
    for mots, code in [(("doctorat", "phd", "doctorate"), "doctorate"), (("master", "ingenieur", "mba"), "bac5"),
                       (("licence", "bachelor"), "bac3"), (("bts", "dut", "deug"), "bac2"), (("baccalaureat",), "bac"),
                       (("bepc",), "bepc")]:
        if any(re.search(rf"\b{m}\b", n) for m in mots):
            return code
    return ""


def _experience(texte):
    n = norm(texte)
    m = re.search(r"(\d{1,2})\s*(?:a|à|-|\s)?\s*\d{0,2}\s*(?:ans|annees|years?)\s*(?:d|of|minimum|mini)?\s*(?:experience|exp)", n) \
        or re.search(r"experience\s*(?:de|d|minimum|min|of)?\s*(\d{1,2})\s*(?:ans|annees|years?)", n)
    return float(m.group(1)) if m else None


def _trouver(liste, texte):
    """Éléments de la liste cités dans le texte (mot entier, sans tenir compte des accents)."""
    n = norm(texte)
    return [x for x in liste if len(norm(x)) > 1
            and re.search(r"(?<![a-z0-9])" + re.escape(norm(x)) + r"(?![a-z0-9])", n)]


def _texte_page(html):
    """Description de secours : meta description + texte principal (sans menus ni scripts)."""
    meta = re.search(r'<meta[^>]+(?:name|property)="(?:og:)?description"[^>]+content="([^"]+)"', html, re.I)
    corps = re.search(r"<(main|article)[^>]*>(.*?)</\1>", html, re.S | re.I)
    bloc = corps.group(2) if corps else html
    bloc = re.sub(r"<(script|style|nav|header|footer|form)[^>]*>.*?</\1>", " ", bloc, flags=re.S | re.I)
    bloc = re.sub(r"<(br|p|li|h\d|div)[^>]*>", "\n", bloc, flags=re.I)
    texte = unescape(re.sub(r"<[^>]+>", " ", bloc))
    lignes = [" ".join(l.split()) for l in texte.splitlines()]
    texte = "\n".join(l for l in lignes if len(l) > 2)
    debut = unescape(meta.group(1)).strip() if meta else ""
    return (debut + "\n\n" + texte).strip()[:6000] if texte else debut


def lire_offre(url):
    """Renvoie un dictionnaire de champs du formulaire d'offre, ou {"error": ...}."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    data = import_from_url(url)
    if data.get("blocked"):
        return {"error": "blocked"}
    if data.get("error"):
        return {"error": data["error"]}
    description = data.get("description", "")
    if not description:   # pas d'annonce structurée : on lit le texte de la page
        try:
            if _safe_url(url):
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; TalentConnect/1.0)"})
                with urllib.request.urlopen(req, timeout=12) as r:
                    html = r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="ignore")
                description = _texte_page(html)
                if not data.get("title"):
                    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
                    if h1:
                        data["title"] = unescape(re.sub(r"<[^>]+>", " ", h1.group(1))).strip()
        except Exception:
            pass
    titre = (data.get("title") or "").strip()
    if not titre and not description:
        return {"error": "vide"}
    tout = f"{titre}\n{description}"
    salaire = re.findall(r"\d[\d\s.]{2,}", data.get("salary", "") or "")
    montants = [int(re.sub(r"\D", "", s)) for s in salaire if re.sub(r"\D", "", s)]
    return {
        "title": titre[:200],
        "description": description[:6000],
        "contract_type": _contrat(data.get("contract", "")) or _contrat(tout) or "cdi",
        "education_level": _niveau_etudes(tout),
        "min_experience": _experience(tout),
        "skills": _trouver(BASE_SKILLS, tout)[:12],
        "soft_skills": _trouver(SOFT_SKILLS, tout)[:6],
        "languages": _trouver(LANGUES, tout)[:4],
        "city": (data.get("city") or "")[:120],
        "country_code": (data.get("country_code") or "")[:2],
        "salary_min": montants[0] if montants else None,
        "salary_max": montants[1] if len(montants) > 1 else None,
        "deadline": data.get("deadline") or "",
        "source": data.get("source", ""),
        "url": url,
    }
