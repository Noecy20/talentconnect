"""« Métiers qui recrutent » : ce que disent les offres ouvertes d'un pays.

On analyse ensemble les offres publiées sur TalentConnect et celles lues sur les autres sites
(Emploi.ci, Educarriere, JSearch, Jooble…) : villes, filières, métiers, entreprises et
compétences demandées. Le résultat est gardé une heure en mémoire."""
import re
import time
import unicodedata
from collections import Counter

from flask import current_app

from ..extensions import db
from ..modeles import Job
from .. import geographie
from . import offres_externes

_CACHE = {}
DUREE = 3600

# Filière devinée à partir des mots de l'intitulé (les offres des autres sites n'en donnent pas)
FILIERES = [
    ("Finance / Comptabilité", "comptab compta financ audit fiscal tresor contrôle de gestion controle de gestion credit banque caiss recouvr"),
    ("Commercial / Vente", "commercial vente vendeu vendeus business developer chargé de clientèle charge de clientele televente télévente agent terrain mandataire prospect"),
    ("Informatique / Data", "informati develop développ devops data donnée donnees réseau reseau system système logiciel web sécurité securite cloud it support helpdesk analyste bi"),
    ("Marketing / Communication", "marketing communication digital community brand contenu graphiste design média media relations publiques"),
    ("Logistique / Transport", "logisti transport transit douane chauffeur magasin entrepôt entrepot stock supply achat approvision coursier livreur"),
    ("Ressources humaines", "ressources humaines rh recrut paie talent formation formateur"),
    ("Administration / Assistanat", "assistant assistante secrétaire secretaire administratif administrative accueil réception reception office"),
    ("BTP / Ingénierie", "btp génie genie civil ingénieur ingenieur technicien électric electric mécanic mecanic maintenance chantier topograph architecte conducteur de travaux qhse hse"),
    ("Santé / Social", "santé sante médecin medecin infirm pharmac sage-femme laboratoire social psycholog"),
    ("Hôtellerie / Restauration", "hôtel hotel cuisin restaurant serveu barman chef de rang hôtess hotess"),
    ("Enseignement", "enseign professeur instituteur éducat educat formateur"),
    ("Juridique", "juridique juriste avocat notaire conformité conformite compliance"),
    ("Agriculture / Environnement", "agricol agronom agro élevage elevage environnement forest"),
    ("Entretien / Sécurité", "nettoyage agent d'entretien gardien vigile sécurité agent de sécurité"),
]


def _sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFD", (texte or "").lower()) if unicodedata.category(c) != "Mn")


def filiere(titre):
    t = _sans_accents(titre)
    for nom, mots in FILIERES:
        if any(_sans_accents(m) in t for m in mots.split(" ") if len(m) > 2):
            return nom
    return "Autres métiers"


def metier(titre):
    """« Comptable Junior / Stagiaire - Abidjan, Cocody (H/F) » -> « Comptable junior »."""
    t = re.split(r"\s[-–|]\s|\(|/|,", titre or "")[0]
    t = re.sub(r"\b(h/f|f/h|hf|urgent|recrute|recrutement)\b", "", t, flags=re.I)
    t = re.sub(r"^\d+\s*", "", t).strip(" .:-")
    return t[:1].upper() + t[1:].lower() if t else ""


def _ville(texte, pays):
    """Ville reconnue dans le texte du lieu (« Abidjan, Cocody » -> Abidjan), avec ses coordonnées."""
    if not texte:
        return None, None
    morceaux = [m.strip() for m in re.split(r"[,/;-]", texte) if m.strip()]
    for m in morceaux:
        c = geographie.city_coords(pays, m)
        if c:
            return m.title() if m.isupper() or m.islower() else m, c
    return None, None


def analyse(pays):
    pays = (pays or "CI").upper()
    if pays in _CACHE and time.time() - _CACHE[pays][0] < DUREE:
        return _CACHE[pays][1]

    offres = []   # forme commune : titre, entreprise, lieu, compétences, filière
    for j in Job.query.filter_by(status="open", country_code=pays).all():
        offres.append(dict(titre=j.title, entreprise=j.company.name if j.company else "", lieu=j.city or "",
                           competences=list(j.skills or []), filiere=j.field or filiere(j.title), origine="TalentConnect"))
    externes, _ = offres_externes.search(current_app.config.get("OFFRES_RECHERCHE_DEFAUT", "emploi"), "", pays)
    for r in externes:
        offres.append(dict(titre=r.get("title") or "", entreprise=r.get("company") or "", lieu=r.get("city") or "",
                           competences=list(r.get("skills") or []), filiere=filiere(r.get("title")),
                           origine=r.get("source") or ""))

    villes, coords = Counter(), {}
    for o in offres:
        v, c = _ville(o["lieu"], pays)
        if v:
            villes[v] += 1
            coords[v] = c
    resultat = dict(
        total=len(offres),
        internes=sum(1 for o in offres if o["origine"] == "TalentConnect"),
        villes=villes.most_common(10),
        points=[{"city": v, "n": n, "lat": coords[v][0], "lng": coords[v][1]} for v, n in villes.items()],
        filieres=Counter(o["filiere"] for o in offres).most_common(12),
        metiers=[(m, n) for m, n in Counter(metier(o["titre"]) for o in offres if metier(o["titre"])).most_common(12)],
        entreprises=[(e, n) for e, n in Counter(o["entreprise"].strip() for o in offres
                                                 if o["entreprise"].strip() and o["entreprise"].strip().lower() not in ("un particulier", "une entreprise", "confidentiel", "entreprise confidentielle")).most_common(10)],
        competences=Counter(c.strip() for o in offres for c in o["competences"] if c.strip()).most_common(24),
        sources=Counter(o["origine"] for o in offres).most_common(),
    )
    if offres:
        _CACHE[pays] = (time.time(), resultat)
    return resultat
