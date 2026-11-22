"""Orientation : test d'intérêts RIASEC (modèle de Holland) + matières préférées.
Les correspondances filières/métiers peuvent être enrichies avec les données O*NET
(ml/importer_onet.py) qui associent chaque métier à un code RIASEC."""
import json
import os

from ..langues import t

# Fichiers facultatifs produits par ml/importer_onet.py et ml/importer_competences_esco.py
DATA_DIR = os.path.dirname(__file__)

TYPES = {
    "R": {"name": "Réaliste", "desc": "Concret, manuel, technique : vous aimez construire, réparer, manipuler des outils et des machines.", "color": "#B45309"},
    "I": {"name": "Investigateur", "desc": "Curieux et analytique : vous aimez comprendre, chercher, résoudre des problèmes complexes.", "color": "#7C3AED"},
    "A": {"name": "Artistique", "desc": "Créatif et expressif : vous aimez imaginer, concevoir, écrire, créer.", "color": "#DB2777"},
    "S": {"name": "Social", "desc": "Tourné vers les autres : vous aimez aider, enseigner, soigner, accompagner.", "color": "#059669"},
    "E": {"name": "Entreprenant", "desc": "Leader et persuasif : vous aimez convaincre, diriger, vendre, entreprendre.", "color": "#D86730"},
    "C": {"name": "Conventionnel", "desc": "Organisé et rigoureux : vous aimez les chiffres, l'ordre, les procédures fiables.", "color": "#2563EB"},
}

QUESTIONS = [
    ("R", "Réparer un appareil électrique ou un moteur"),
    ("R", "Travailler en extérieur, sur un chantier ou dans la nature"),
    ("R", "Utiliser des machines, des outils ou des équipements techniques"),
    ("R", "Construire ou assembler quelque chose de mes mains"),
    ("R", "Conduire, piloter ou faire fonctionner des véhicules ou des engins"),
    ("I", "Résoudre des problèmes de mathématiques ou de logique"),
    ("I", "Faire des expériences scientifiques en laboratoire"),
    ("I", "Analyser des données pour trouver une explication"),
    ("I", "Comprendre comment fonctionne un programme informatique"),
    ("I", "Lire des articles scientifiques ou techniques"),
    ("A", "Dessiner, peindre ou faire du design graphique"),
    ("A", "Écrire des histoires, des articles ou des scripts"),
    ("A", "Faire de la musique, du théâtre ou de la vidéo"),
    ("A", "Imaginer la décoration ou l'architecture d'un lieu"),
    ("A", "Créer du contenu pour les réseaux sociaux"),
    ("S", "Expliquer quelque chose à quelqu'un qui ne comprend pas"),
    ("S", "Aider des personnes malades ou en difficulté"),
    ("S", "Animer un groupe ou une association"),
    ("S", "Écouter et conseiller un ami qui a un problème"),
    ("S", "Travailler avec des enfants ou des jeunes"),
    ("E", "Vendre un produit ou négocier un prix"),
    ("E", "Diriger une équipe vers un objectif"),
    ("E", "Créer ma propre entreprise"),
    ("E", "Prendre la parole en public pour convaincre"),
    ("E", "Organiser un événement et trouver des partenaires"),
    ("C", "Tenir des comptes ou un budget à jour"),
    ("C", "Classer et organiser des documents ou des fichiers"),
    ("C", "Suivre une procédure précise sans erreur"),
    ("C", "Remplir des tableaux Excel et vérifier des chiffres"),
    ("C", "Préparer des plannings et des calendriers"),
]

SUBJECTS = ["Mathématiques", "Physique-Chimie", "SVT / Biologie", "Français / Lettres", "Anglais / Langues",
            "Histoire-Géographie", "Philosophie", "Économie", "Informatique", "Arts / Musique", "Sport", "Technologie"]

# Filières : code RIASEC dominant + matières qui renforcent la recommandation + métiers types
FIELDS = [
    {"field": "Génie civil / BTP", "codes": "RIC", "subjects": ["Mathématiques", "Physique-Chimie", "Technologie"],
     "jobs": ["Ingénieur génie civil", "Conducteur de travaux", "Technicien bâtiment", "Géomètre"]},
    {"field": "Électrotechnique / Énergie", "codes": "RIC", "subjects": ["Physique-Chimie", "Mathématiques", "Technologie"],
     "jobs": ["Électricien industriel", "Technicien énergie solaire", "Ingénieur électrique"]},
    {"field": "Mécanique / Maintenance industrielle", "codes": "RI", "subjects": ["Physique-Chimie", "Technologie"],
     "jobs": ["Technicien de maintenance", "Mécanicien automobile", "Ingénieur mécanique"]},
    {"field": "Agronomie / Agro-industrie", "codes": "RIS", "subjects": ["SVT / Biologie", "Physique-Chimie"],
     "jobs": ["Ingénieur agronome", "Technicien agricole", "Responsable qualité agroalimentaire"]},
    {"field": "Logistique / Transport", "codes": "RCE", "subjects": ["Mathématiques", "Histoire-Géographie"],
     "jobs": ["Logisticien", "Gestionnaire de transit", "Responsable d'entrepôt", "Supply chain analyst"]},
    {"field": "Informatique / Développement", "codes": "IRC", "subjects": ["Mathématiques", "Informatique", "Anglais / Langues"],
     "jobs": ["Développeur web", "Développeur mobile", "Ingénieur logiciel", "DevOps"]},
    {"field": "Data / Intelligence artificielle", "codes": "ICR", "subjects": ["Mathématiques", "Informatique"],
     "jobs": ["Data analyst", "Data scientist", "Ingénieur IA", "Analyste BI"]},
    {"field": "Réseaux / Cybersécurité", "codes": "IRC", "subjects": ["Informatique", "Mathématiques", "Technologie"],
     "jobs": ["Administrateur réseaux", "Analyste cybersécurité", "Technicien télécoms"]},
    {"field": "Médecine / Pharmacie", "codes": "ISR", "subjects": ["SVT / Biologie", "Physique-Chimie"],
     "jobs": ["Médecin", "Pharmacien", "Biologiste", "Technicien de laboratoire"]},
    {"field": "Sciences infirmières / Santé", "codes": "SIR", "subjects": ["SVT / Biologie"],
     "jobs": ["Infirmier(ère)", "Sage-femme", "Aide-soignant(e)", "Kinésithérapeute"]},
    {"field": "Design graphique / UX", "codes": "AEI", "subjects": ["Arts / Musique", "Informatique"],
     "jobs": ["Designer graphique", "UX/UI designer", "Motion designer", "Directeur artistique"]},
    {"field": "Architecture / Urbanisme", "codes": "ARI", "subjects": ["Arts / Musique", "Mathématiques", "Histoire-Géographie"],
     "jobs": ["Architecte", "Urbaniste", "Architecte d'intérieur", "Dessinateur projeteur"]},
    {"field": "Journalisme / Communication", "codes": "ASE", "subjects": ["Français / Lettres", "Anglais / Langues", "Histoire-Géographie"],
     "jobs": ["Journaliste", "Chargé de communication", "Community manager", "Rédacteur web"]},
    {"field": "Audiovisuel / Cinéma / Musique", "codes": "AER", "subjects": ["Arts / Musique", "Français / Lettres"],
     "jobs": ["Monteur vidéo", "Réalisateur", "Ingénieur du son", "Producteur"]},
    {"field": "Éducation / Enseignement", "codes": "SAI", "subjects": ["Français / Lettres", "Philosophie", "Histoire-Géographie"],
     "jobs": ["Enseignant", "Formateur", "Conseiller d'orientation", "Éducateur"]},
    {"field": "Psychologie / Travail social", "codes": "SIA", "subjects": ["Philosophie", "SVT / Biologie", "Français / Lettres"],
     "jobs": ["Psychologue", "Assistant social", "Éducateur spécialisé", "Coach"]},
    {"field": "Ressources humaines", "codes": "SEC", "subjects": ["Économie", "Français / Lettres", "Philosophie"],
     "jobs": ["Chargé de recrutement", "Gestionnaire paie", "Responsable RH", "Talent acquisition"]},
    {"field": "Droit / Sciences juridiques", "codes": "EIC", "subjects": ["Français / Lettres", "Philosophie", "Histoire-Géographie"],
     "jobs": ["Juriste d'entreprise", "Avocat", "Notaire", "Compliance officer"]},
    {"field": "Commerce / Marketing", "codes": "EAS", "subjects": ["Économie", "Anglais / Langues", "Français / Lettres"],
     "jobs": ["Commercial", "Chef de produit", "Responsable marketing digital", "Business developer"]},
    {"field": "Management / Entrepreneuriat", "codes": "ESC", "subjects": ["Économie", "Mathématiques"],
     "jobs": ["Chef de projet", "Entrepreneur", "Consultant", "Responsable d'agence"]},
    {"field": "Hôtellerie / Tourisme", "codes": "ESR", "subjects": ["Anglais / Langues", "Histoire-Géographie"],
     "jobs": ["Réceptionniste", "Chef de cuisine", "Guide touristique", "Responsable d'hôtel"]},
    {"field": "Finance / Comptabilité", "codes": "CEI", "subjects": ["Mathématiques", "Économie"],
     "jobs": ["Comptable", "Contrôleur de gestion", "Auditeur", "Analyste financier"]},
    {"field": "Banque / Assurance", "codes": "CES", "subjects": ["Économie", "Mathématiques"],
     "jobs": ["Conseiller clientèle", "Chargé d'affaires", "Actuaire", "Gestionnaire de risques"]},
    {"field": "Administration / Secrétariat", "codes": "CSE", "subjects": ["Français / Lettres", "Informatique"],
     "jobs": ["Assistant(e) de direction", "Secrétaire", "Office manager", "Gestionnaire administratif"]},
    {"field": "Sport / Animation", "codes": "SRE", "subjects": ["Sport", "SVT / Biologie"],
     "jobs": ["Coach sportif", "Professeur d'EPS", "Animateur", "Préparateur physique"]},
]


def score_answers(answers):
    """answers : {index_question: 1..5} -> scores par type (0..100)."""
    totals = {k: 0 for k in TYPES}
    counts = {k: 0 for k in TYPES}
    for i, (typ, _) in enumerate(QUESTIONS):
        v = answers.get(i)
        if v is None:
            continue
        totals[typ] += int(v) - 1
        counts[typ] += 4
    return {k: round(totals[k] / counts[k] * 100) if counts[k] else 0 for k in TYPES}


def recommend(scores, subjects=None, limit=6):
    subjects = set(subjects or [])
    order = sorted(scores, key=lambda k: -scores[k])
    code = "".join(order[:3])
    recos = []
    for f in FIELDS:
        s = 0.0
        for pos, letter in enumerate(f["codes"]):
            s += scores.get(letter, 0) * (1.0, 0.6, 0.35)[pos]
        s = s / 1.95
        bonus = len(subjects & set(f["subjects"])) * 6
        recos.append({**f, "score": min(99, round(s + bonus))})
    recos.sort(key=lambda r: -r["score"])
    return code, recos[:limit]


def translated_types():
    return {k: {**v, "name": t(v["name"]), "desc": t(v["desc"])} for k, v in TYPES.items()}


def onet_matches(code, limit=8):
    """Métiers O*NET dont les 2 premières lettres RIASEC correspondent (si ml/importer_onet.py a été lancé)."""
    path = os.path.join(DATA_DIR, "onet_riasec.json")
    if not code or not os.path.exists(path):
        return []
    rows = json.load(open(path, encoding="utf-8"))
    hits = [r for r in rows if r["code"][:2] == code[:2]] or [r for r in rows if r["code"][0] == code[0]]
    hits.sort(key=lambda r: -sum(r["scores"].get(c, 0) for c in code))
    return [r["title"] for r in hits[:limit]]


def skill_suggestions(lang="fr", limit=4000):
    """Liste ESCO (ml/importer_competences_esco.py) pour l'autocomplétion, sinon une liste de base."""
    for l in (lang, "fr", "en"):
        path = os.path.join(DATA_DIR, f"competences_{l}.json")
        if os.path.exists(path):
            return json.load(open(path, encoding="utf-8"))[:limit]
    return BASE_SKILLS


BASE_SKILLS = ["Excel", "Word", "PowerPoint", "SQL", "Python", "JavaScript", "React", "Node.js", "Django", "Flask", "Java",
               "PHP", "Git", "Docker", "Linux", "AWS", "Power BI", "Tableau", "Statistiques", "Machine learning", "Figma",
               "UX", "Photoshop", "Illustrator", "Canva", "Réseaux sociaux", "Rédaction web", "SEO", "Meta Ads",
               "Comptabilité", "Fiscalité", "Sage", "SAP", "Audit", "Analyse financière", "Modélisation financière",
               "Contrôle de gestion", "Gestion de projet", "Agile", "Scrum", "Jira", "Supply chain", "Gestion des stocks",
               "Transit", "Douane", "ERP", "Relation client", "Vente", "Négociation commerciale", "Marketing digital",
               "Ressources humaines", "Paie", "Recrutement", "Droit des affaires", "Anglais", "Réseaux", "Cisco",
               "Cybersécurité", "Fibre optique", "Électricité", "Maintenance", "AutoCAD", "BTP", "Management d'équipe"]
