"""Données du tableau de bord Power BI.

Deux pages, deux familles de fichiers CSV (séparateur « ; », UTF-8 avec BOM) :

1. « L'emploi dans le monde » : les problèmes de l'emploi pays par pays, d'après les
   indicateurs de l'Organisation internationale du travail (OIT) publiés par la Banque mondiale
   (World Development Indicators) : chômage, chômage des jeunes, chômage des diplômés,
   jeunes sans emploi ni formation (NEET), emploi vulnérable (informel), participation au
   marché du travail, écart femmes / hommes.
     monde_pays.csv            un pays par ligne (région, niveau de revenu, coordonnées)
     monde_indicateurs.csv     une valeur par pays, indicateur et année (2010 -> aujourd'hui)
     monde_derniere_valeur.csv la valeur la plus récente de chaque indicateur, par pays (cartes)
     monde_definitions.csv     libellé, définition et source de chaque indicateur

2. « Activité de TalentConnect » : ce qui se passe sur la plateforme, jour par jour.
     activite_quotidienne.csv  inscriptions, offres, candidatures, entretiens, embauches,
                               messages, paiements, parrainages… par jour
     activite_evenements.csv   un événement par ligne (date, type, rôle, pays) pour filtrer librement
     + les fichiers détaillés (utilisateurs, offres, candidatures, paiements, parrainages…)

Aucune donnée personnelle : pas de nom, d'e-mail ni de téléphone, seulement des numéros.
Les fichiers sont produits par ml/exporter_powerbi.py (sur l'ordinateur) ou téléchargés depuis
l'administration du site (Power BI peut aussi les lire directement par un lien secret).
"""
import csv
import io
import json
import os
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta

from .. import geographie

# --------------------------------------------------------------------------- emploi dans le monde
API = "https://api.worldbank.org/v2"
ANNEE_DEBUT = 2010

# code Banque mondiale -> (nom court, libellé, thème, définition)
INDICATEURS = {
    "SL.UEM.TOTL.ZS": ("chomage", "Taux de chômage (%)", "Chômage",
                       "Part de la population active sans emploi qui cherche un travail (estimation OIT)."),
    "SL.UEM.1524.ZS": ("chomage_jeunes", "Chômage des 15-24 ans (%)", "Jeunes",
                       "Part des actifs de 15 à 24 ans sans emploi (estimation OIT)."),
    "SL.UEM.NEET.ZS": ("neet", "Jeunes sans emploi ni formation – NEET (%)", "Jeunes",
                       "Part des jeunes qui ne sont ni en emploi, ni en études, ni en formation."),
    "SL.UEM.ADVN.ZS": ("chomage_diplomes", "Chômage des diplômés du supérieur (%)", "Diplômés",
                       "Taux de chômage des actifs ayant un niveau d'études supérieur."),
    "SL.UEM.INTM.ZS": ("chomage_niveau_moyen", "Chômage – niveau secondaire (%)", "Diplômés",
                       "Taux de chômage des actifs ayant un niveau d'études intermédiaire."),
    "SL.UEM.BASC.ZS": ("chomage_niveau_base", "Chômage – niveau primaire (%)", "Diplômés",
                       "Taux de chômage des actifs ayant un niveau d'études de base."),
    "SL.EMP.VULN.ZS": ("emploi_vulnerable", "Emploi vulnérable (%)", "Qualité de l'emploi",
                       "Travailleurs indépendants et aides familiaux : emplois souvent informels, sans contrat ni protection sociale."),
    "SL.TLF.CACT.ZS": ("participation", "Taux de participation au marché du travail (%)", "Participation",
                       "Part des 15 ans et plus qui travaillent ou cherchent un emploi."),
    "SL.TLF.CACT.FE.ZS": ("participation_femmes", "Participation des femmes (%)", "Femmes",
                          "Part des femmes de 15 ans et plus présentes sur le marché du travail."),
    "SL.UEM.TOTL.FE.ZS": ("chomage_femmes", "Chômage des femmes (%)", "Femmes",
                          "Part des femmes actives sans emploi (estimation OIT)."),
    "SL.UEM.1524.FE.ZS": ("chomage_jeunes_femmes", "Chômage des jeunes femmes 15-24 ans (%)", "Femmes",
                          "Part des jeunes femmes actives de 15 à 24 ans sans emploi."),
}
SOURCE = "Banque mondiale, World Development Indicators (estimations de l'OIT, ILOSTAT)"

REGIONS_FR = {
    "Sub-Saharan Africa": "Afrique subsaharienne", "Middle East & North Africa": "Moyen-Orient et Afrique du Nord",
    "Middle East, North Africa, Afghanistan & Pakistan": "Moyen-Orient et Afrique du Nord",
    "Europe & Central Asia": "Europe et Asie centrale", "East Asia & Pacific": "Asie de l'Est et Pacifique",
    "South Asia": "Asie du Sud", "Latin America & Caribbean": "Amérique latine et Caraïbes",
    "North America": "Amérique du Nord",
}
REVENUS_FR = {"High income": "Revenu élevé", "Upper middle income": "Revenu intermédiaire supérieur",
              "Lower middle income": "Revenu intermédiaire inférieur", "Low income": "Faible revenu"}
# Agrégats utiles pour comparer (Monde, Afrique subsaharienne, UEMOA…)
AGREGATS = {"WLD": "Monde", "SSF": "Afrique subsaharienne", "MEA": "Moyen-Orient et Afrique du Nord",
            "ECS": "Europe et Asie centrale", "EAS": "Asie de l'Est et Pacifique", "SAS": "Asie du Sud",
            "LCN": "Amérique latine et Caraïbes", "NAC": "Amérique du Nord", "EUU": "Union européenne",
            "LIC": "Pays à faible revenu", "LMC": "Revenu intermédiaire inférieur",
            "UMC": "Revenu intermédiaire supérieur", "HIC": "Pays à revenu élevé"}

_CACHE = {"quand": 0, "donnees": None}
DUREE_CACHE = 24 * 3600


def _lire(url, essais=3):
    for i in range(essais):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TalentConnect/1.0 (tableau de bord Power BI)"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if i == essais - 1:
                raise
            time.sleep(1.5 * (i + 1))


def _pages(url):
    """Toutes les pages d'une réponse de l'API de la Banque mondiale."""
    sep = "&" if "?" in url else "?"
    premiere = _lire(f"{url}{sep}format=json&per_page=20000&page=1")
    if not isinstance(premiere, list) or len(premiere) < 2 or premiere[1] is None:
        return []
    lignes, pages = list(premiere[1]), int(premiere[0].get("pages", 1))
    for p in range(2, pages + 1):
        lignes += _lire(f"{url}{sep}format=json&per_page=20000&page={p}")[1] or []
    return lignes


def donnees_monde(forcer=False):
    """Télécharge (ou reprend du cache, 24 h) les indicateurs de l'emploi de tous les pays."""
    if not forcer and _CACHE["donnees"] and time.time() - _CACHE["quand"] < DUREE_CACHE:
        return _CACHE["donnees"]
    try:
        return _telecharger()
    except Exception:
        if _CACHE["donnees"]:          # Banque mondiale injoignable : on garde la dernière version
            return _CACHE["donnees"]
        raise


def _telecharger():
    pays = {}
    for c in _pages(f"{API}/country"):
        iso3, region = c.get("id"), (c.get("region") or {}).get("value", "").strip()
        if region == "Aggregates" and iso3 not in AGREGATS:
            continue
        est_pays = region != "Aggregates"
        iso2 = c.get("iso2Code", "")
        nom = geographie.country_name(iso2, "fr") if est_pays else AGREGATS[iso3]
        pays[iso3] = {"iso3": iso3, "iso2": iso2 if est_pays else "", "nom": nom if nom and nom != iso2 else c.get("name", ""),
                      "type": "Pays" if est_pays else "Ensemble régional",
                      "region": REGIONS_FR.get(region, region) if est_pays else "",
                      "revenu": REVENUS_FR.get((c.get("incomeLevel") or {}).get("value", ""), "") if est_pays else "",
                      "capitale": c.get("capitalCity", ""), "latitude": c.get("latitude", ""), "longitude": c.get("longitude", "")}
    valeurs = []
    annee_fin = date.today().year
    for code in INDICATEURS:
        for v in _pages(f"{API}/country/all/indicator/{code}?date={ANNEE_DEBUT}:{annee_fin}"):
            iso3 = v.get("countryiso3code")
            if v.get("value") is None or iso3 not in pays:
                continue
            valeurs.append((iso3, int(v["date"]), code, round(float(v["value"]), 2)))
    if not valeurs:
        raise RuntimeError("Aucune donnée reçue de la Banque mondiale")
    _CACHE.update(quand=time.time(), donnees={"pays": pays, "valeurs": valeurs})
    return _CACHE["donnees"]


def fichiers_monde(forcer=False):
    d = donnees_monde(forcer)
    pays, valeurs = d["pays"], d["valeurs"]
    sorties = {}
    sorties["monde_pays.csv"] = (
        ["code_iso3", "code_iso2", "pays", "type", "region", "niveau_revenu", "capitale", "latitude", "longitude"],
        [[p["iso3"], p["iso2"], p["nom"], p["type"], p["region"], p["revenu"], p["capitale"], p["latitude"], p["longitude"]]
         for p in sorted(pays.values(), key=lambda x: (x["type"] != "Pays", x["nom"]))])
    sorties["monde_indicateurs.csv"] = (
        ["code_iso3", "pays", "annee", "code_indicateur", "indicateur", "theme", "valeur"],
        [[iso3, pays[iso3]["nom"], an, code, INDICATEURS[code][1], INDICATEURS[code][2], val]
         for iso3, an, code, val in sorted(valeurs)])
    derniere = {}
    for iso3, an, code, val in valeurs:
        if (iso3, code) not in derniere or an > derniere[(iso3, code)][0]:
            derniere[(iso3, code)] = (an, val)
    codes = list(INDICATEURS)
    entete = ["code_iso3", "code_iso2", "pays", "type", "region", "niveau_revenu"]
    for c in codes:
        entete += [INDICATEURS[c][0], f"{INDICATEURS[c][0]}_annee"]
    lignes = []
    for iso3, p in pays.items():
        ligne = [iso3, p["iso2"], p["nom"], p["type"], p["region"], p["revenu"]]
        for c in codes:
            an, val = derniere.get((iso3, c), ("", ""))
            ligne += [val, an]
        if any(derniere.get((iso3, c)) for c in codes):
            lignes.append(ligne)
    sorties["monde_derniere_valeur.csv"] = (entete, sorted(lignes, key=lambda l: (l[3] != "Pays", l[2])))
    sorties["monde_definitions.csv"] = (
        ["code_indicateur", "nom_colonne", "indicateur", "theme", "definition", "source"],
        [[c, v[0], v[1], v[2], v[3], SOURCE] for c, v in INDICATEURS.items()])
    return sorties


# --------------------------------------------------------------------------- activité de la plateforme
def _j(x):
    return x.strftime("%Y-%m-%d") if x else ""


def fichiers_activite():
    """Activité de TalentConnect (à appeler dans un contexte d'application)."""
    from ..modeles import (Application, CandidateProfile, Job, Message, Payment, Sponsorship, SponsorshipRequest,
                           SponsorProfile, TrackedApplication, User)
    sorties = {}
    users = User.query.all()
    role_de = {u.id: u.role for u in users}
    pays_de = {u.id: u.country_code or "" for u in users}

    # ---- événements : une ligne = un fait daté
    ev = []   # (date, evenement, role, pays, montant)
    for u in users:
        ev.append((u.created_at, "Inscription", u.role, u.country_code or "", ""))
        if u.last_seen and u.role != "admin":
            ev.append((u.last_seen, "Dernière connexion", u.role, u.country_code or "", ""))
    jobs = Job.query.all()
    for j in jobs:
        ev.append((j.created_at, "Offre publiée", "recruiter", j.country_code or "", ""))
    apps = Application.query.all()
    for a in apps:
        ev.append((a.created_at, "Candidature", "candidate", pays_de.get(a.candidate_id, ""), ""))
        if a.decided_at:
            libelle = {"interview": "Invitation à un entretien", "offer": "Proposition d'embauche", "hired": "Embauche",
                       "rejected": "Refus avec retour", "second_chance": "Seconde chance"}.get(a.status)
            if libelle:
                ev.append((a.decided_at, libelle, "recruiter", pays_de.get(a.candidate_id, ""), ""))
    for m in Message.query.with_entities(Message.created_at, Message.sender_id, Message.kind).all():
        ev.append((m.created_at, "Message envoyé" if m.kind == "custom" else "Message automatique",
                   role_de.get(m.sender_id, "plateforme"), pays_de.get(m.sender_id, ""), ""))
    for p in Payment.query.all():
        ev.append((p.created_at, "Paiement déclaré", role_de.get(p.user_id, ""), pays_de.get(p.user_id, ""), p.amount))
        if p.status == "confirmed" and p.validated_at:
            ev.append((p.validated_at, "Paiement validé", role_de.get(p.user_id, ""), pays_de.get(p.user_id, ""), p.amount))
    for r in SponsorshipRequest.query.all():
        ev.append((r.created_at, "Demande de parrainage", "candidate", pays_de.get(r.candidate_id, ""), ""))
    for s in Sponsorship.query.all():
        ev.append((s.created_at, "Recommandation de parrain", "sponsor", pays_de.get(s.sponsor_id, ""), ""))
    for sp in SponsorProfile.query.filter(SponsorProfile.status.in_(["approved", "rejected"])).all():
        ev.append((sp.reviewed_at or sp.created_at, "Parrain certifié" if sp.status == "approved" else "Parrain refusé",
                   "sponsor", pays_de.get(sp.user_id, ""), ""))
    for t in TrackedApplication.query.all():
        ev.append((t.created_at, "Offre ajoutée au suivi", "candidate", pays_de.get(t.user_id, ""), ""))
    ev = [e for e in ev if e[0]]
    ev.sort(key=lambda e: e[0])
    roles_fr = {"candidate": "Candidat", "recruiter": "Recruteur", "sponsor": "Parrain", "admin": "Administrateur",
                "plateforme": "Plateforme"}
    sorties["activite_evenements.csv"] = (
        ["date", "annee", "mois", "semaine", "evenement", "role", "code_pays", "pays", "montant"],
        [[_j(d), d.year, d.strftime("%Y-%m"), d.strftime("%G-S%V"), e, roles_fr.get(r, r), c,
          geographie.country_name(c, "fr") if c else "", m] for d, e, r, c, m in ev])

    # ---- tableau quotidien (une colonne par indicateur)
    colonnes = ["Inscription candidat", "Inscription recruteur", "Inscription parrain", "Offre publiée", "Candidature",
                "Invitation à un entretien", "Embauche", "Message envoyé", "Paiement validé", "Recommandation de parrain",
                "Offre ajoutée au suivi"]
    par_jour = defaultdict(lambda: defaultdict(float))
    for d, e, r, c, m in ev:
        cle = f"Inscription {roles_fr.get(r, '').lower()}" if e == "Inscription" else e
        par_jour[d.date()][cle] += 1
        if e == "Paiement validé":
            par_jour[d.date()]["Montant encaissé"] += float(m or 0)
    if par_jour:
        debut, fin = min(par_jour), max(max(par_jour), date.today())
    else:
        debut = fin = date.today()
    lignes, cumul = [], defaultdict(float)
    jour = debut
    while jour <= fin:
        v = par_jour.get(jour, {})
        for k in ("Inscription candidat", "Inscription recruteur", "Inscription parrain"):
            cumul[k] += v.get(k, 0)
        lignes.append([_j(jour), jour.strftime("%Y-%m"), jour.strftime("%G-S%V")] +
                      [int(v.get(k, 0)) for k in colonnes] + [int(v.get("Montant encaissé", 0)),
                      int(cumul["Inscription candidat"] + cumul["Inscription recruteur"] + cumul["Inscription parrain"])])
        jour += timedelta(days=1)
    sorties["activite_quotidienne.csv"] = (
        ["date", "mois", "semaine", "inscriptions_candidats", "inscriptions_recruteurs", "inscriptions_parrains",
         "offres_publiees", "candidatures", "entretiens", "embauches", "messages_envoyes", "paiements_valides",
         "recommandations", "offres_suivies", "montant_encaisse", "utilisateurs_cumules"], lignes)

    # ---- chiffres clés (une ligne) pour les cartes de la page
    actifs_30j = sum(1 for u in users if u.last_seen and u.last_seen >= datetime.utcnow() - timedelta(days=30) and u.role != "admin")
    sorties["activite_chiffres_cles.csv"] = (
        ["date_export", "utilisateurs", "candidats", "recruteurs", "parrains", "actifs_30_jours", "offres_ouvertes",
         "candidatures", "entretiens", "embauches", "taux_reponse_pct", "parrains_certifies", "chiffre_affaires"],
        [[_j(datetime.utcnow()), sum(1 for u in users if u.role != "admin"),
          sum(1 for u in users if u.role == "candidate"), sum(1 for u in users if u.role == "recruiter"),
          sum(1 for u in users if u.role == "sponsor"), actifs_30j, sum(1 for j in jobs if j.status == "open"), len(apps),
          sum(1 for a in apps if a.status in ("interview", "offer", "hired")), sum(1 for a in apps if a.status == "hired"),
          round(sum(1 for a in apps if a.ack_sent_at) / len(apps) * 100, 1) if apps else 0,
          SponsorProfile.query.filter_by(status="approved").count(),
          sum(p.amount or 0 for p in Payment.query.filter_by(status="confirmed").all())]])

    # ---- fichiers détaillés (anonymisés)
    sorties["utilisateurs.csv"] = (
        ["id_utilisateur", "role", "code_pays", "pays", "ville", "date_inscription", "derniere_connexion", "acces_payant_actif"],
        [[u.id, u.role, u.country_code, geographie.country_name(u.country_code, "fr"), u.city, _j(u.created_at),
          _j(u.last_seen), 1 if u.has_access else 0] for u in users])
    sorties["candidats.csv"] = (
        ["id_utilisateur", "filiere", "niveau_etudes", "annees_experience", "nb_competences", "ouvert_international",
         "test_riasec_fait", "code_riasec", "test_personnalite_fait", "type_personnalite"],
        [[c.user_id, c.field, c.education_level, c.years_experience or 0, len(c.skills or []),
          1 if c.open_to_international else 0, 1 if c.riasec else 0,
          (c.riasec or {}).get("code", "") if isinstance(c.riasec, dict) else "",
          1 if c.personnalite else 0,
          (f'{c.personnalite.get("type", "")} – {c.personnalite.get("nom", "")}'
           if isinstance(c.personnalite, dict) and c.personnalite.get("type") else "")]
         for c in CandidateProfile.query.all()])
    nb_cand = defaultdict(int)
    for a in apps:
        nb_cand[a.job_id] += 1
    sorties["offres.csv"] = (
        ["id_offre", "id_entreprise", "secteur_entreprise", "intitule", "filiere", "type_contrat", "niveau_etudes_requis",
         "experience_min", "code_pays", "pays", "ville", "teletravail", "salaire_min", "salaire_max", "devise", "statut",
         "date_publication", "vues", "nb_candidatures", "ponderation_personnalisee"],
        [[j.id, j.company_id, j.company.sector if j.company else "", j.title, j.field, j.contract_type, j.education_level,
          j.min_experience, j.country_code, geographie.country_name(j.country_code, "fr"), j.city, 1 if j.remote else 0,
          j.salary_min or "", j.salary_max or "", j.currency, j.status, _j(j.created_at), j.views or 0, nb_cand[j.id],
          1 if j.ponderations else 0] for j in jobs])
    parraines = {s.candidate_id for s in Sponsorship.query.filter_by(status="active").all()}
    sorties["candidatures.csv"] = (
        ["id_candidature", "id_offre", "id_candidat", "statut", "score_compatibilite", "probabilite_contact", "groupe_ia",
         "accuse_reception_envoye", "retour_constructif", "candidat_parraine", "date_candidature", "date_decision",
         "delai_reponse_jours"],
        [[a.id, a.job_id, a.candidate_id, a.status, a.match_score, a.call_probability, a.ai_group or "",
          1 if a.ack_sent_at else 0, 1 if a.feedback else 0, 1 if a.candidate_id in parraines else 0,
          _j(a.created_at), _j(a.decided_at),
          round((a.decided_at - a.created_at).total_seconds() / 86400, 1) if a.decided_at and a.created_at else ""]
         for a in apps])
    sorties["paiements.csv"] = (
        ["id_paiement", "id_utilisateur", "role", "formule", "montant", "devise", "moyen", "statut", "date_declaration",
         "date_validation"],
        [[p.id, p.user_id, role_de.get(p.user_id, ""), p.plan.name if p.plan else "", p.amount, p.currency, p.method,
          p.status, _j(p.created_at), _j(p.validated_at)] for p in Payment.query.all()])
    sorties["parrainages.csv"] = (
        ["id_parrainage", "id_parrain", "id_candidat", "relation", "statut", "date"],
        [[s.id, s.sponsor_id, s.candidate_id, s.relation, s.status, _j(s.created_at)] for s in Sponsorship.query.all()])
    sorties["suivi_candidatures.csv"] = (
        ["id_suivi", "id_candidat", "etape", "source", "pays", "ville", "contrat", "date_ajout", "date_candidature", "archive"],
        [[t.id, t.user_id, t.stage, t.source, t.country_code, t.city, t.contract, _j(t.created_at), _j(t.applied_at),
          1 if t.archived else 0] for t in TrackedApplication.query.all()])
    comp = defaultdict(int)
    for j in jobs:
        for s in j.skills or []:
            comp[s] += 1
    sorties["competences_demandees.csv"] = (["competence", "nb_offres"], sorted(comp.items(), key=lambda kv: -kv[1]))
    return sorties


# --------------------------------------------------------------------------- modèles d'IA (page existante)
def fichiers_modeles():
    """Études réelles qui ont servi à entraîner le modèle et contrôle d'équité."""
    rep_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "ml", "rapport", "rapport_entrainement.json")
    if not os.path.exists(rep_path):
        return {}
    rep = json.load(open(rep_path, encoding="utf-8"))
    pays = {"bertrand_mullainathan_2004": ("États-Unis", "Boston et Chicago"),
            "phillips_2019": ("États-Unis", "Washington DC"),
            "karachi_it": ("Pakistan", "Karachi"),
            "time_to_degree": ("États-Unis", "Plusieurs villes")}
    rows = []
    for k, v in rep["sources"].items():
        p = pays.get(k, ("", ""))
        rows.append([k, p[0], p[1], v["candidatures"], round(v["taux_reponse_positive"] * 100, 2), v["reference"]])
    fr = rep.get("modele_france")
    if fr:
        rows.append(["behaghel_2015", "France", "Pôle emploi (plusieurs régions)", fr["candidatures"],
                     round(fr["taux_entretien"] * 100, 2), fr["reference"]])
    sorties = {"etudes_entrainement.csv": (
        ["etude", "pays", "lieu", "nb_candidatures", "taux_reponse_positive_pct", "reference"], rows)}
    rows = []
    equite = dict(rep.get("equite", {}))
    mono = rep.get("modele_deploye", {}).get("equite_modele_etats_unis")
    if mono:      # modèle réellement déployé pour les États-Unis
        equite["bertrand_mullainathan_2004"] = mono
    for etude, groupes in equite.items():
        for critere, vals in groupes.items():
            for g, m in vals.items():
                rows.append([etude, critere, g, m["n"], round(m["taux_reel"] * 100, 2), round(m["taux_predit"] * 100, 2)])
    if fr:
        for critere, vals in fr.get("equite", {}).items():
            for g, m in vals.items():
                rows.append(["behaghel_2015", critere, g, m["n"], round(m["taux_reel"] * 100, 2), round(m["taux_predit"] * 100, 2)])
    sorties["equite_modeles.csv"] = (
        ["etude", "critere", "groupe", "effectif_test", "taux_reel_pct", "taux_predit_modele_pct"], rows)
    return sorties


def en_csv(entete, lignes):
    """Contenu CSV (« ; », UTF-8 avec BOM : Excel et Power BI l'ouvrent directement)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(entete)
    w.writerows(lignes)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def tous_les_fichiers(avec_monde=True):
    sorties = fichiers_activite()
    sorties.update(fichiers_modeles())
    if avec_monde:
        try:
            sorties.update(fichiers_monde())
        except Exception as exc:   # pas d'Internet : la page « Monde » garde ses derniers fichiers
            sorties["_erreur_monde.txt"] = str(exc)
    return sorties
