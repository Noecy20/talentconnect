"""Exporte les données de TalentConnect au format CSV pour le tableau de bord Power BI.

Usage :
    python ml/exporter_powerbi.py            # écrit les fichiers dans powerbi/

Les fichiers sont anonymisés : aucun nom, e-mail ni téléphone n'est exporté
(chaque personne est identifiée par un numéro). Ils peuvent donc être partagés
ou montrés en soutenance sans exposer de données personnelles.

Fichiers produits (séparateur « ; », encodage UTF-8 avec BOM pour Excel et Power BI) :
  utilisateurs.csv, candidats.csv, offres.csv, candidatures.csv, paiements.csv,
  parrainages.csv, suivi_candidatures.csv, competences_demandees.csv,
  etudes_entrainement.csv, equite_modeles.csv
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "powerbi")


def write(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        w.writerows(rows)
    print(f"  {name:28s} {len(rows):6d} lignes")


def d(x):
    return x.strftime("%Y-%m-%d") if x else ""


def main():
    from app import create_app
    from app import geographie as geo
    from app.modeles import (Application, CandidateProfile, Job, Payment, Sponsorship, TrackedApplication, User)
    os.makedirs(OUT, exist_ok=True)
    app = create_app()
    with app.app_context():
        print(f"Export vers {OUT}")
        users = User.query.all()
        write("utilisateurs.csv", ["id_utilisateur", "role", "code_pays", "pays", "ville", "date_inscription", "acces_payant_actif"],
              [[u.id, u.role, u.country_code, geographie.country_name(u.country_code, "fr"), u.city, d(u.created_at),
                1 if u.has_access else 0] for u in users])

        write("candidats.csv", ["id_utilisateur", "filiere", "niveau_etudes", "annees_experience", "nb_competences",
                                "ouvert_international", "test_riasec_fait", "code_riasec"],
              [[c.user_id, c.field, c.education_level, c.years_experience or 0, len(c.skills or []),
                1 if c.open_to_international else 0, 1 if c.riasec else 0,
                (c.riasec or {}).get("code", "") if isinstance(c.riasec, dict) else ""] for c in CandidateProfile.query.all()])

        jobs = Job.query.all()
        write("offres.csv", ["id_offre", "id_entreprise", "secteur_entreprise", "intitule", "filiere", "type_contrat",
                             "niveau_etudes_requis", "experience_min", "code_pays", "pays", "ville", "teletravail",
                             "salaire_min", "salaire_max", "devise", "statut", "date_publication", "vues", "nb_candidatures"],
              [[j.id, j.company_id, j.company.sector if j.company else "", j.title, j.field, j.contract_type,
                j.education_level, j.min_experience, j.country_code, geographie.country_name(j.country_code, "fr"), j.city,
                1 if j.remote else 0, j.salary_min or "", j.salary_max or "", j.currency, j.status, d(j.created_at),
                j.views or 0, j.applications.count()] for j in jobs])

        rows = []
        for a in Application.query.all():
            delay = ""
            if a.decided_at and a.created_at:
                delay = round((a.decided_at - a.created_at).total_seconds() / 86400, 1)
            parraine = 1 if Sponsorship.query.filter_by(candidate_id=a.candidate_id, status="active").count() else 0
            rows.append([a.id, a.job_id, a.candidate_id, a.status, a.match_score, a.call_probability, a.ai_group or "",
                         1 if a.ack_sent_at else 0, 1 if a.feedback else 0, parraine, d(a.created_at), d(a.decided_at), delay])
        write("candidatures.csv", ["id_candidature", "id_offre", "id_candidat", "statut", "score_compatibilite",
                                   "probabilite_contact", "groupe_ia", "accuse_reception_envoye", "retour_constructif",
                                   "candidat_parraine", "date_candidature", "date_decision", "delai_reponse_jours"], rows)

        write("paiements.csv", ["id_paiement", "id_utilisateur", "role", "formule", "montant", "devise", "moyen",
                                "statut", "date_declaration", "date_validation"],
              [[p.id, p.user_id, p.user.role if p.user else "", p.plan.name if p.plan else "", p.amount, p.currency,
                p.method, p.status, d(p.created_at), d(p.validated_at)] for p in Payment.query.all()])

        write("parrainages.csv", ["id_parrainage", "id_parrain", "id_candidat", "relation", "statut", "date"],
              [[s.id, s.sponsor_id, s.candidate_id, s.relation, s.status, d(s.created_at)] for s in Sponsorship.query.all()])

        write("suivi_candidatures.csv", ["id_suivi", "id_candidat", "etape", "source", "pays", "ville", "contrat",
                                         "date_candidature", "archive"],
              [[t.id, t.user_id, t.stage, t.source, t.country_code, t.city, t.contract, d(t.applied_at),
                1 if t.archived else 0] for t in TrackedApplication.query.all()])

        comp = {}
        for j in jobs:
            for s in j.skills or []:
                comp[s] = comp.get(s, 0) + 1
        write("competences_demandees.csv", ["competence", "nb_offres"], sorted(comp.items(), key=lambda kv: -kv[1]))

    # Données « monde » : études réelles ayant servi à entraîner le modèle
    rep_path = os.path.join(ROOT, "ml", "rapport", "rapport_entrainement.json")
    if os.path.exists(rep_path):
        rep = json.load(open(rep_path, encoding="utf-8"))
        pays = {"bertrand_mullainathan_2004": ("États-Unis", "Boston et Chicago", 2001),
                "phillips_2019": ("États-Unis", "Washington DC", 2015),
                "karachi_it": ("Pakistan", "Karachi", None),
                "time_to_degree": ("États-Unis", "Plusieurs villes", None)}
        rows = []
        for k, v in rep["sources"].items():
            p = pays.get(k, ("", "", None))
            rows.append([k, p[0], p[1], v["candidatures"], round(v["taux_reponse_positive"] * 100, 2), v["reference"]])
        fr = rep.get("modele_france")
        if fr:
            rows.append(["behaghel_2015", "France", "Pôle emploi (plusieurs régions)", fr["candidatures"],
                         round(fr["taux_entretien"] * 100, 2), fr["reference"]])
        write("etudes_entrainement.csv", ["etude", "pays", "lieu", "nb_candidatures", "taux_reponse_positive_pct", "reference"], rows)

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
        write("equite_modeles.csv", ["etude", "critere", "groupe", "effectif_test", "taux_reel_pct", "taux_predit_modele_pct"], rows)
    print("✓ Terminé. Dans Power BI : Obtenir des données > Texte/CSV (délimiteur point-virgule).")


if __name__ == "__main__":
    main()
