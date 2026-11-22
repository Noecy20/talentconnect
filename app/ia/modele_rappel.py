"""Modèle « probabilité d'être contacté » entraîné sur des données réelles.

Données d'entraînement : 4 expériences de terrain publiées (16 407 candidatures réelles
envoyées à de vraies offres d'emploi, aux États-Unis et au Pakistan). Pour chaque
candidature, on sait si le recruteur a répondu positivement (rappel, entretien).

  - Bertrand & Mullainathan (2004), American Economic Review — 4 870 CV, Boston et Chicago
  - Phillips (2019), Journal of Human Resources — 2 260 candidatures, emplois peu qualifiés, Washington DC
  - Audit de CV dans le secteur informatique à Karachi (Harvard Dataverse) — 2 032 candidatures
  - Expérience « Time to Baccalaureate Degree » (Harvard Dataverse) — 7 245 candidatures de jeunes diplômés

Chaque étude ne mesure pas toutes les variables : les valeurs absentes sont laissées vides
et le modèle apprend à s'en passer. Une variable « contexte » (l'étude d'origine) capte les
différences de niveau de rappel entre marchés ; pour un candidat TalentConnect, la
prédiction est la moyenne sur les quatre contextes.

Un second modèle est entraîné sur des candidats réels en France :
  - Behaghel, Crépon & Le Barbanchon (2015), « Unintended Effects of Anonymous Résumés »,
    American Economic Journal: Applied Economics — 1 471 candidatures de demandeurs d'emploi
    adressées par Pôle emploi à 677 offres ; cible = le candidat a été convoqué en entretien.
La probabilité affichée est la moyenne des deux modèles (contexte américain et contexte français).

Ce module définit les variables et leur calcul depuis un candidat et une offre de la
plateforme ; le même code sert à l'entraînement (ml/entrainer_modele_rappel.py).
Les variables sensibles (origine, genre, âge, classe sociale, prénom) sont exclues.
"""
import math
import os
import re
import unicodedata

SOURCES = ["bertrand_mullainathan_2004", "phillips_2019", "karachi_it", "time_to_degree"]

BASE_FEATURES = [
    "years_experience",      # années d'expérience du candidat
    "college_degree",        # diplôme de niveau licence ou plus (0/1)
    "years_college",         # années d'études supérieures (0 à 4)
    "computer_skills",       # compétences informatiques (0/1)
    "special_skills",        # compétences particulières mises en avant (0/1)
    "resume_quality",        # CV / profil de bonne qualité (0/1)
    "req_experience",        # années d'expérience exigées par l'offre
    "meets_experience",      # le candidat atteint l'expérience exigée (0/1)
    "req_education",         # l'offre exige un diplôme du supérieur (0/1)
    "req_computer",          # l'offre exige l'informatique (0/1)
    "req_communication",     # l'offre exige la communication (0/1)
    "req_organization",      # l'offre exige l'organisation (0/1)
    "distance_km",           # distance domicile-lieu de travail (km)
]
FEATURES = BASE_FEATURES + [f"src_{s}" for s in SOURCES]

# Le modèle entraîné est rangé à côté de ce fichier.
MODEL_PATH = os.path.join(os.path.dirname(__file__), "modele_rappel.joblib")

COMPUTER_WORDS = {
    "excel", "word", "powerpoint", "office", "informatique", "bureautique", "python", "sql", "java", "javascript",
    "html", "css", "php", "react", "django", "flask", "linux", "reseau", "reseaux", "sage", "erp", "sap", "power bi",
    "tableau", "photoshop", "autocad", "wordpress", "git", "c#", "c++", "data", "cloud", "developpement", "programmation",
    "computer", "software",
}
COMMUNICATION_WORDS = {"communication", "relationnel", "oral", "ecoute", "negociation", "presentation", "relation client"}
ORGANIZATION_WORDS = {"organisation", "organise", "rigueur", "rigoureux", "gestion du temps", "planification", "autonomie"}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def _has_any(items, words):
    """1 si l'un des éléments contient l'un des mots (mot entier, insensible aux accents)."""
    for it in items or []:
        n = _norm(it)
        for w in words:
            if re.search(r"(^|[^a-z0-9])" + re.escape(w) + r"($|[^a-z0-9])", n):
                return 1
    return 0


def _distance_km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def years_college_from_rank(rank):
    """Rang TalentConnect (bac=2, bac+2=3, licence=4, master=6…) -> années d'études supérieures (0-4)."""
    return {0: 0, 1: 0, 2: 0, 3: 2, 4: 3}.get(rank, 4)


def from_platform(candidate_user, job, completeness):
    """Variables du modèle pour un candidat et une offre TalentConnect (sans le contexte)."""
    from ..modeles import EDU_RANK
    from .. import geographie
    cp = candidate_user.candidate
    rank = cp.edu_rank if cp else 0
    years = min(35.0, float((cp.years_experience if cp else 0) or 0))
    skills = list((cp.skills if cp else None) or [])
    soft = list((cp.soft_skills if cp else None) or [])
    req = float(job.min_experience or 0)
    dist = float("nan")
    if job.remote:
        dist = 0.0
    else:
        try:
            a = geographie.city_coords(candidate_user.country_code, candidate_user.city)
            b = geographie.city_coords(job.country_code, job.city)
            if a and b:
                dist = round(_distance_km(a, b), 1)
        except Exception:
            pass
    return {
        "years_experience": years,
        "college_degree": 1 if rank >= 4 else 0,
        "years_college": float(years_college_from_rank(rank)),
        "computer_skills": _has_any(skills, COMPUTER_WORDS),
        "special_skills": 1 if len(skills) + len(soft) >= 6 else 0,
        "resume_quality": 1 if completeness >= 0.7 else 0,
        "req_experience": req,
        "meets_experience": 1 if years >= req else 0,
        "req_education": 1 if EDU_RANK.get(job.education_level or "none", 0) >= 4 else 0,
        "req_computer": _has_any(job.skills, COMPUTER_WORDS),
        "req_communication": _has_any(job.soft_skills, COMMUNICATION_WORDS),
        "req_organization": _has_any(job.soft_skills, ORGANIZATION_WORDS),
        "distance_km": dist,
    }


_BUNDLE = None


def load():
    """Charge le modèle entraîné (ou False s'il n'existe pas)."""
    global _BUNDLE
    if _BUNDLE is None:
        _BUNDLE = False
        if os.path.exists(MODEL_PATH):
            try:
                import joblib
                _BUNDLE = joblib.load(MODEL_PATH)
            except Exception:
                _BUNDLE = False
    return _BUNDLE


FR_FEATURES = [
    "fr_education",          # 0 aucun diplôme, 1 CAP/BEP/BEPC, 2 bac, 3 bac+2, 4 bac+3 et plus
    "fr_years_experience",   # années d'expérience (plafonnées à 10, comme dans les données)
    "fr_overqualified",      # niveau d'études nettement supérieur à celui demandé (0/1)
    "fr_underqualified",     # niveau d'études inférieur à celui demandé (0/1)
    "fr_adequate_experience",  # expérience suffisante pour le poste (0/1)
    "fr_english",            # parle anglais (0/1)
    "fr_other_language",     # parle une autre langue étrangère (0/1)
    "fr_job_executive",      # poste de cadre (0/1)
    "fr_job_intermediate",   # profession intermédiaire (technicien, agent de maîtrise…) (0/1)
    "fr_permanent_contract",  # CDI (0/1)
    "fr_large_firm",         # entreprise de plus de 200 salariés (0/1)
    "fr_resume_good",        # CV de bonne qualité (0/1)
    "fr_anonymous",          # CV anonyme (toujours 0 sur TalentConnect)
]


def _languages(cp):
    out = []
    for l in (cp.languages if cp else None) or []:
        out.append(_norm(l.get("name") if isinstance(l, dict) else l))
    return out


def from_platform_fr(candidate_user, job, completeness):
    """Variables du modèle « France » pour un candidat et une offre TalentConnect."""
    from ..modeles import EDU_RANK
    cp = candidate_user.candidate
    rank = cp.edu_rank if cp else 0
    req = EDU_RANK.get(job.education_level or "none", 0)
    years = float((cp.years_experience if cp else 0) or 0)
    langs = _languages(cp)
    english = 1 if any(x in ("anglais", "english") for x in langs) else 0
    other = 1 if any(x and x not in ("anglais", "english", "francais", "french") for x in langs) else 0
    size = (job.company.size if job.company else "") or ""
    return {
        "fr_education": float(min(rank, 4)),
        "fr_years_experience": min(10.0, years),
        "fr_overqualified": 1 if rank >= req + 2 else 0,
        "fr_underqualified": 1 if rank < req else 0,
        "fr_adequate_experience": 1 if years >= float(job.min_experience or 0) else 0,
        "fr_english": english,
        "fr_other_language": other,
        "fr_job_executive": 1 if req >= 5 else 0,
        "fr_job_intermediate": 1 if req in (3, 4) else 0,
        "fr_permanent_contract": 1 if (job.contract_type or "") == "cdi" else 0,
        "fr_large_firm": 1 if size in ("201-1000", "1000+") else 0,
        "fr_resume_good": 1 if completeness >= 0.8 else 0,
        "fr_anonymous": 0,
    }


def _predict_one(b, features):
    import numpy as np
    rows = []
    for s in b.get("sources") or [None]:
        f = dict(features)
        for s2 in b.get("sources") or []:
            f[f"src_{s2}"] = 1.0 if s2 == s else 0.0
        rows.append([f.get(k, float("nan")) for k in b["features"]])
    p = b["model"].predict_proba(np.array(rows, dtype=float))[:, 1]
    return float(p.mean())


def predict_for(candidate_user, job, completeness):
    """Probabilité (0..1) d'être contacté : moyenne des modèles entraînés sur données réelles."""
    b = load()
    if not b:
        return None
    probs = []
    for m in b.get("models", [b]):
        f = from_platform_fr(candidate_user, job, completeness) if m.get("context") == "france" \
            else from_platform(candidate_user, job, completeness)
        probs.append(_predict_one(m, f))
    return float(sum(probs) / len(probs))


def average_rate():
    """Taux de réponse positive moyen observé dans les données d'entraînement (en %), ou None."""
    b = load()
    return round(b["base_rate"] * 100) if b else None
