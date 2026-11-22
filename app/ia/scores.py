"""Modèles de décision de TalentConnect.

Les scores de compatibilité, d'éligibilité et d'employabilité sont des modèles à règles
pondérées, transparents et ajustables par l'admin (table settings).
La probabilité d'être contacté repose sur un modèle d'apprentissage automatique entraîné
sur des données réelles (voir ia/modele_rappel.py et ml/entrainer_modele_rappel.py)."""
import math
import os
import re
import unicodedata
from difflib import SequenceMatcher

from ..modeles import (EDU_RANK, Application, Setting, Sponsorship, SponsorProfile, User)
from ..langues import t

FREE_MAIL = {"gmail.com", "yahoo.com", "yahoo.fr", "hotmail.com", "hotmail.fr", "outlook.com", "outlook.fr",
             "live.com", "icloud.com", "aol.com", "proton.me", "protonmail.com", "gmx.com", "mail.com", "ymail.com"}


# --------------------------------------------------------------------------- outils texte
def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9+#.]+", " ", s).strip()


def similar(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a == b or (len(a) > 3 and a in b) or (len(b) > 3 and b in a):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.84


def overlap(required, offered):
    """Part des éléments requis couverts par l'offre (0..1) + listes trouvées / manquantes."""
    required = [r for r in (required or []) if r]
    offered = [o for o in (offered or []) if o]
    if not required:
        return 1.0, [], []
    found, missing = [], []
    for r in required:
        (found if any(similar(r, o) for o in offered) else missing).append(r)
    return len(found) / len(required), found, missing


# --------------------------------------------------------------------------- parrainage
SENIORITY_POINTS = {"employee": 5, "manager": 15, "senior_manager": 20, "director": 25, "executive": 30}


def sponsor_eligibility(sp: SponsorProfile, user: User):
    """Score d'éligibilité d'un parrain sur 100 avec le détail des points."""
    b = {}
    if sp.kind == "company":
        b["Statut / immatriculation"] = 30 if sp.registration_number else 10
    else:
        b["Niveau du poste"] = SENIORITY_POINTS.get(sp.seniority, 5)
    b["Expérience"] = min(20, int(sp.years_experience or 0) * 2)
    b["Niveau d'études"] = min(14, EDU_RANK.get(sp.education_level or "none", 0) * 2)
    email = (sp.professional_email or "").lower().strip()
    domain = email.split("@")[-1] if "@" in email else ""
    pro = 0
    if domain and domain not in FREE_MAIL:
        pro = 8
        site = norm(sp.organization_website).replace(" ", "")
        if site and domain.split(".")[0] in site:
            pro = 12
    b["E-mail professionnel"] = pro
    b["Profil LinkedIn"] = 8 if "linkedin.com" in (sp.linkedin or "").lower() else 0
    ts = sp.team_size or 0
    b["Équipe encadrée"] = 8 if ts >= 20 else 6 if ts >= 5 else 4 if ts >= 1 else 0
    b["Organisation identifiée"] = (2 if sp.organization else 0) + (2 if sp.organization_website else 0)
    b["Présentation"] = 4 if len(sp.bio or "") >= 80 else 2 if len(sp.bio or "") >= 30 else 0
    score = int(sum(b.values()))
    return score, b


def sponsor_level(score):
    return "gold" if score >= 85 else "silver" if score >= 70 else "bronze"


def decide_sponsor(sp: SponsorProfile, user: User):
    """Applique les seuils : validation auto, revue admin, ou refus."""
    score, breakdown = sponsor_eligibility(sp, user)
    sp.eligibility_score, sp.eligibility_breakdown = score, breakdown
    auto, minimum = Setting.get("sponsor_auto_approve"), Setting.get("sponsor_min_score")
    if score >= auto:
        sp.status, sp.level = "approved", sponsor_level(score)
    elif score >= minimum:
        sp.status, sp.level = "pending_review", None
    else:
        sp.status, sp.level = "rejected", None
    return sp.status


def update_reputation(sponsor_user_id, delta):
    sp = SponsorProfile.query.filter_by(user_id=sponsor_user_id).first()
    if sp:
        sp.reputation = max(0.0, min(100.0, (sp.reputation or 50) + delta))


# --------------------------------------------------------------------------- passeport de compétences
def _par_requete(cle, calcul):
    """Mémorise un résultat le temps d'une requête HTTP (évite de refaire la même
    lecture en base pour chaque offre d'une liste)."""
    from flask import g, has_app_context
    if not has_app_context():
        return calcul()
    memo = g.setdefault("_scores", {})
    if cle not in memo:
        memo[cle] = calcul()
    return memo[cle]


def _parrainages_actifs(candidate_user):
    return _par_requete(("parrainages", candidate_user.id), lambda: Sponsorship.query.filter_by(
        candidate_id=candidate_user.id, status="active").all())


def skill_passport(candidate_user):
    """{compétence: {"count": n, "avg": note}} à partir des parrainages actifs."""
    out = {}
    sps = _parrainages_actifs(candidate_user)
    for s in sps:
        for k, v in list((s.skill_ratings or {}).items()) + list((s.soft_ratings or {}).items()):
            d = out.setdefault(k, {"count": 0, "total": 0})
            d["count"] += 1
            d["total"] += int(v or 0)
    for k, d in out.items():
        d["avg"] = round(d["total"] / d["count"], 1) if d["count"] else 0
    return out


def sponsorship_strength(candidate_user):
    """0..1 : nombre de parrains pondéré par leur niveau et leur réputation."""
    return _par_requete(("force", candidate_user.id), lambda: _force(candidate_user))


def _force(candidate_user):
    sps = _parrainages_actifs(candidate_user)
    # Tous les profils de parrain en une seule requête
    ids = [s.sponsor_id for s in sps]
    profils = {p.user_id: p for p in SponsorProfile.query.filter(SponsorProfile.user_id.in_(ids)).all()} if ids else {}
    total = 0.0
    for s in sps:
        sp = profils.get(s.sponsor_id)
        if not sp or not sp.is_approved:
            continue
        lvl = {"gold": 1.0, "silver": 0.8, "bronze": 0.6}.get(sp.level or "bronze", 0.6)
        total += lvl * ((sp.reputation or 50) / 50)
    return min(1.0, total / 3)


# --------------------------------------------------------------------------- compatibilité candidat / offre
def match(candidate_user, job):
    """Score 0..100 + détail par critère + points forts / manques."""
    cp = candidate_user.candidate
    w = Setting.get("match_weights")
    if cp is None:
        return 0, {}
    passport = skill_passport(candidate_user)
    cand_skills = list(cp.skills or []) + list(passport.keys())

    s_skill, found, missing = overlap(job.skills, cand_skills)
    s_soft, soft_found, soft_missing = overlap(job.soft_skills, list(cp.soft_skills or []) + list(passport.keys()))
    s_lang, _, lang_missing = overlap(job.languages, [l.get("name") if isinstance(l, dict) else l for l in (cp.languages or [])])

    if job.field and cp.field:
        if similar(job.field, cp.field):
            s_field = 1.0
        else:
            jt, ct = set(norm(job.field).split()), set(norm(cp.field).split())
            s_field = 0.5 if jt & ct else 0.1
    else:
        s_field = 0.6

    need = job.min_experience or 0
    have = cp.years_experience or 0
    s_exp = 1.0 if need <= 0 else min(1.0, have / need) if have < need else 1.0

    req, got = EDU_RANK.get(job.education_level or "none", 0), cp.edu_rank
    s_edu = 1.0 if got >= req else 0.6 if got == req - 1 else 0.25

    u = candidate_user
    if job.remote:
        s_loc = 1.0
    elif (u.city or "").lower() == (job.city or "").lower() and u.country_code == job.country_code:
        s_loc = 1.0
    elif any(similar(c, job.city) for c in (cp.desired_cities or [])):
        s_loc = 0.9
    elif u.country_code == job.country_code:
        s_loc = 0.7
    elif cp.open_to_international:
        s_loc = 0.55
    else:
        s_loc = 0.15

    parts = {"skills": s_skill, "field": s_field, "experience": s_exp, "education": s_edu,
             "location": s_loc, "soft_skills": s_soft, "languages": s_lang}
    total_w = sum(w.values()) or 1
    score = round(sum(parts[k] * w.get(k, 0) for k in parts) / total_w * 100)
    detail = {
        "parts": {k: round(v * 100) for k, v in parts.items()},
        "skills_found": found, "skills_missing": missing,
        "soft_found": soft_found, "soft_missing": soft_missing,
        "lang_missing": lang_missing,
        "experience_gap": max(0, need - have),
        "education_gap": max(0, req - got),
    }
    return int(score), detail


def profile_completeness(candidate_user):
    cp = candidate_user.candidate
    if not cp:
        return 0.0
    checks = [bool(cp.headline), len(cp.summary or "") > 60, len(cp.skills or []) >= 4,
              len(cp.soft_skills or []) >= 2, bool(cp.field), bool(cp.languages),
              bool(cp.cv_data), bool(candidate_user.city), bool(cp.desired_position), bool(cp.linkedin)]
    return sum(checks) / len(checks)


def company_response_rate(company_id):
    from ..modeles import Job
    apps = Application.query.join(Job).filter(Job.company_id == company_id).all()
    if not apps:
        return None
    answered = sum(1 for a in apps if a.ack_sent_at or a.status != "received")
    return round(answered / len(apps) * 100)


_ML_MODEL = None


def _load_ml():
    global _ML_MODEL
    if _ML_MODEL is None:
        path = os.path.join(os.path.dirname(__file__), "..", "..", "instance", "modeles", "modele_plateforme.joblib")
        if os.path.exists(path):
            try:
                import joblib
                _ML_MODEL = joblib.load(path)
            except Exception:
                _ML_MODEL = False
        else:
            _ML_MODEL = False
    return _ML_MODEL


def call_features(candidate_user, job, match_score=None):
    ms = match_score if match_score is not None else match(candidate_user, job)[0]
    n_apps = job.applications.count()
    return {
        "match": ms,
        "sponsorship": sponsorship_strength(candidate_user),
        "completeness": profile_completeness(candidate_user),
        "competition": n_apps,
        "response_rate": (company_response_rate(job.company_id) or 50) / 100,
    }


def call_probability(candidate_user, job, match_score=None):
    """Probabilité (%) d'être contacté pour un entretien.

    1. Si un modèle a été entraîné sur les candidatures de TalentConnect, il est utilisé.
    2. Sinon, les modèles entraînés sur des données réelles (États-Unis et France)
       donne la probabilité de base à partir du profil et des exigences de l'offre.
       Elle est ensuite ajustée par des facteurs propres à TalentConnect, absents de ces
       données : adéquation fine des compétences, parrainage, réactivité de l'entreprise,
       concurrence (coefficients fixés, non appris).
    3. À défaut de modèle, une formule logistique calibrée à la main est utilisée."""
    f = call_features(candidate_user, job, match_score)
    model = _load_ml()
    if model:
        try:
            import numpy as np
            x = np.array([[f["match"], f["sponsorship"], f["completeness"], f["competition"], f["response_rate"]]])
            return int(round(model.predict_proba(x)[0][1] * 100))
        except Exception:
            pass
    from . import modele_rappel
    try:
        base = modele_rappel.predict_for(candidate_user, job, f["completeness"])
    except Exception:
        base = None
    if base is not None:
        base = min(max(base, 0.005), 0.995)
        z = (math.log(base / (1 - base)) + 0.025 * (f["match"] - 60) + 1.3 * f["sponsorship"]
             + 0.6 * (f["response_rate"] - 0.5) - 0.006 * min(f["competition"], 150))
        p = 1 / (1 + math.exp(-z))
        return int(max(1, min(95, round(p * 100))))
    z = (-4.2 + 0.062 * f["match"] + 1.3 * f["sponsorship"] + 0.9 * f["completeness"]
         - 0.012 * min(f["competition"], 150) + 0.6 * f["response_rate"])
    p = 1 / (1 + math.exp(-z))
    return int(max(2, min(95, round(p * 100))))


# --------------------------------------------------------------------------- tri des candidatures
def triage(application):
    hi, mid = Setting.get("triage_interview"), Setting.get("triage_second_chance")
    s = application.match_score or 0
    d = application.match_breakdown or {}
    strengths = []
    if d.get("skills_found"):
        strengths.append(t("compétences : {x}", x=", ".join(d["skills_found"][:4])))
    if d.get("parts", {}).get("experience", 0) >= 100:
        strengths.append(t("expérience suffisante"))
    if sponsorship_strength(application.candidate) > 0:
        strengths.append(t("parrainé"))
    gaps = []
    if d.get("skills_missing"):
        gaps.append(t("manque : {x}", x=", ".join(d["skills_missing"][:4])))
    if d.get("experience_gap"):
        gaps.append(t("{n} an(s) d'expérience en moins", n=round(d["experience_gap"], 1)))
    if d.get("education_gap"):
        gaps.append(t("niveau d'études inférieur"))
    if s >= hi:
        group = "interview"
    elif s >= mid:
        group = "second_chance"
    else:
        group = "rejected"
    reason = " · ".join(strengths + gaps) or t("profil à examiner")
    return group, reason


# --------------------------------------------------------------------------- retour constructif
TRAINING_HINTS = {
    "excel": "Excel avancé (tableaux croisés, Power Query)",
    "python": "Python pour l'analyse de données",
    "sql": "SQL (requêtes, jointures)",
    "anglais": "Anglais professionnel (objectif B2)",
    "english": "Anglais professionnel (objectif B2)",
}


def refusal_feedback(application):
    d = application.match_breakdown or {}
    reasons, tips = [], []
    if d.get("skills_missing"):
        reasons.append(t("Certaines compétences clés du poste n'apparaissent pas dans votre profil : {x}.",
                         x=", ".join(d["skills_missing"][:5])))
        for sk in d["skills_missing"][:2]:
            hint = TRAINING_HINTS.get(norm(sk))
            tips.append(t("Renforcez « {x} » (formation courte, projet concret) et ajoutez-le à votre profil.", x=hint or sk))
    if d.get("experience_gap"):
        reasons.append(t("Le poste demande environ {n} an(s) d'expérience de plus.", n=round(d["experience_gap"], 1)))
        tips.append(t("Valorisez stages, missions freelance et projets personnels comme expérience."))
    if d.get("education_gap"):
        reasons.append(t("Le niveau d'études demandé est supérieur au vôtre."))
    if d.get("lang_missing"):
        reasons.append(t("Langue(s) attendue(s) : {x}.", x=", ".join(d["lang_missing"])))
    if sponsorship_strength(application.candidate) == 0:
        tips.append(t("Demandez un parrainage à un ancien manager : les profils parrainés sont davantage contactés."))
    if profile_completeness(application.candidate) < 0.8:
        tips.append(t("Complétez votre profil (résumé, compétences, langues) pour améliorer votre score."))
    if not reasons:
        reasons.append(t("D'autres profils correspondaient plus étroitement aux besoins actuels du poste."))
    return {"reasons": reasons, "tips": tips[:4]}


# --------------------------------------------------------------------------- employabilité
def employability(candidate_user):
    """Score global 0..100 et actions concrètes avec leur gain estimé."""
    cp = candidate_user.candidate
    if not cp:
        return 0, []
    comp = profile_completeness(candidate_user)
    spons = sponsorship_strength(candidate_user)
    skills = min(1.0, len(cp.skills or []) / 8)
    soft = min(1.0, len(cp.soft_skills or []) / 4)
    exp = min(1.0, (cp.years_experience or 0) / 5)
    langs = min(1.0, len(cp.languages or []) / 2)
    score = round(100 * (0.30 * comp + 0.25 * spons + 0.15 * skills + 0.10 * soft + 0.12 * exp + 0.08 * langs))
    actions = []
    if spons < 0.34:
        actions.append({"label": t("Obtenir un parrainage d'un ancien manager"), "gain": 12, "url": "candidate.sponsorships"})
    if not cp.cv_data:
        actions.append({"label": t("Créer votre CV avec le CV Builder"), "gain": 6, "url": "candidate.cv_builder"})
    if len(cp.skills or []) < 8:
        actions.append({"label": t("Ajouter au moins 8 compétences"), "gain": 5, "url": "candidate.profile"})
    if len(cp.summary or "") <= 60:
        actions.append({"label": t("Rédiger un résumé de profil percutant"), "gain": 4, "url": "candidate.profile"})
    if len(cp.soft_skills or []) < 4:
        actions.append({"label": t("Ajouter vos soft skills"), "gain": 3, "url": "candidate.profile"})
    if len(cp.languages or []) < 2:
        actions.append({"label": t("Renseigner vos langues"), "gain": 3, "url": "candidate.profile"})
    if not cp.linkedin:
        actions.append({"label": t("Ajouter votre lien LinkedIn"), "gain": 2, "url": "candidate.profile"})
    return int(score), actions
