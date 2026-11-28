"""Tests des retours sur la version de démonstration (novembre 2026).

- annuaire et profil des parrains (filtres, sollicitation) ;
- une seule tentative au test d'éligibilité parrain, même avec un autre compte ;
- modèles de message personnalisés et envoi depuis la fiche candidat ;
- pondérations du score choisies par le recruteur ;
- import d'une offre depuis le site web de l'entreprise ;
- plus de paiement en espèces ;
- tables de la base en français.

Prérequis : base de démonstration (flask --app run.py seed-demo).
Usage : python tests/test_retours.py   ->  affiche "ERREURS 0" si tout fonctionne.
"""

import io
import os
import random
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import inspect  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.modeles import (User, Job, Application, SponsorProfile, SponsorshipRequest, MessageTemplate,  # noqa: E402
                         Message, Payment, Plan)
from app.ia import scores  # noqa: E402
from app.services import suivi, import_offre  # noqa: E402

app = create_app()
app.config["WTF_CSRF_ENABLED"] = False
erreurs = []


def verifier(cond, msg):
    print(("ok   " if cond else "ÉCHEC ") + msg)
    if not cond:
        erreurs.append(msg)


def connecter(c, email, pw="Demo1234!"):
    c.get("/auth/deconnexion")
    r = c.post("/auth/connexion", data={"email": email, "password": pw})
    assert r.status_code == 302, (email, r.status_code)


def donner_acces(email):
    from datetime import datetime, timedelta
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        u.access_granted, u.access_until = True, datetime.now() + timedelta(days=30)
        db.session.commit()


# --------------------------------------------------------------------------- tables en français
with app.app_context():
    tables = set(inspect(db.engine).get_table_names())
    for nom in ("utilisateurs", "offres", "candidatures", "profils_parrains", "parrainages", "paiements",
                "formules", "vivier", "modeles_messages", "suivi_candidatures", "refus_parrains"):
        verifier(nom in tables, f"table « {nom} » présente")
    verifier("users" not in tables and "jobs" not in tables, "anciennes tables anglaises supprimées")
    cand = User.query.filter_by(role="candidate", email="aicha.kone@demo.tc").first()
    app_ = Application.query.first()
    rec_email = app_.job.recruiter.email
    sp_ok = SponsorProfile.query.filter_by(status="approved").first()
    sp_id, sp_nom, sp_email, sp_uid = sp_ok.id, sp_ok.user.last_name, sp_ok.user.email, sp_ok.user_id
    app_id, job_id, cand_id = app_.id, app_.job_id, cand.id

# --------------------------------------------------------------------------- annuaire des parrains
c = app.test_client()
connecter(c, "aicha.kone@demo.tc")
donner_acces("aicha.kone@demo.tc")
r = c.get("/parrains")
verifier(r.status_code == 200 and str(__import__("markupsafe").escape(sp_nom)) in r.get_data(as_text=True), "annuaire : liste des parrains certifiés")
for qs in ("?q=" + sp_nom, "?niveau=gold", "?tri=recommandations", "?type=individual&exp=5",
           "?pays=CI&ville=Abidjan", "?seniorite=director"):
    verifier(c.get("/parrains" + qs).status_code == 200, f"annuaire : filtre {qs}")
r = c.get("/parrains?q=zzzzzz")
verifier("Aucun parrain" in r.get_data(as_text=True), "annuaire : recherche sans résultat")
r = c.get(f"/parrains/{sp_id}")
verifier(r.status_code == 200 and ("Solliciter son parrainage" in r.get_data(as_text=True) or "déjà recommandé" in r.get_data(as_text=True)), "profil du parrain (vu par un candidat)")
r = c.post(f"/candidat/parrainages/solliciter/{sp_id}", data={"message": "Bonjour, pourriez-vous me recommander ?"})
with app.app_context():
    ok = SponsorshipRequest.query.filter_by(candidate_id=cand_id, invitee_email=sp_email).first() is not None
    ok_msg = Message.query.filter_by(recipient_id=sp_uid, kind="sponsorship").first() is not None
verifier(r.status_code == 302 and ok and ok_msg, "sollicitation d'un parrain depuis l'annuaire")

# --------------------------------------------------------------------------- recruteur
connecter(c, rec_email)
donner_acces(rec_email)
verifier(c.get(f"/parrains/{sp_id}").status_code == 200, "profil du parrain (vu par un recruteur)")
r = c.post("/recruteur/modeles", data={"action": "ajouter", "name": "Demande de diplômes",
                                       "subject": "Pièces pour {job}", "body": "Bonjour {candidate}, merci d'envoyer vos diplômes."})
with app.app_context():
    tpl = MessageTemplate.query.filter_by(kind="custom", name="Demande de diplômes").first()
tpl_id = tpl.id if tpl else 0
verifier(r.status_code == 302 and tpl is not None, "création d'un modèle de message")
page = c.get("/recruteur/modeles").get_data(as_text=True)
verifier("Demande de diplômes" in page, "le nouveau modèle s'affiche")
r = c.post("/recruteur/modeles", data={"action": "modifier", "id": tpl_id, "name": "Demande de diplômes (v2)",
                                       "subject": "Pièces", "body": "Texte"})
with app.app_context():
    verifier(db.session.get(MessageTemplate, tpl_id).name.endswith("(v2)"), "modification d'un modèle")
page = c.get(f"/recruteur/candidatures/{app_id}").get_data(as_text=True)
verifier("Envoyer un message" in page and "Demande de dipl" in page, "fiche candidat : choix du modèle")
r = c.post(f"/recruteur/candidatures/{app_id}/message", data={"subject": "Bonjour {candidate}", "body": "Poste {job}"})
with app.app_context():
    m = Message.query.filter_by(application_id=app_id, kind="custom").order_by(Message.id.desc()).first()
    verifier(r.status_code == 302 and m and "{" not in m.subject + m.body, "envoi d'un message depuis la fiche candidat")
page = c.get(f"/recruteur/offres/{job_id}/tri").get_data(as_text=True)
verifier("Partir d" in page, "tri IA : choix d'un modèle")
r = c.post("/recruteur/modeles", data={"action": "supprimer", "id": tpl_id})
with app.app_context():
    verifier(db.session.get(MessageTemplate, tpl_id) is None, "suppression d'un modèle")

# pondérations
page = c.get(f"/recruteur/offres/{job_id}/modifier").get_data(as_text=True)
verifier("Pondération du score" in page, "formulaire d'offre : pondérations")
with app.app_context():
    job = db.session.get(Job, job_id)
    form = {"title": job.title, "description": job.description or "x", "field": job.field, "contract_type": job.contract_type,
            "education_level": job.education_level, "min_experience": job.min_experience, "skills": ",".join(job.skills or []),
            "soft_skills": ",".join(job.soft_skills or []), "languages": ",".join(job.languages or []),
            "country_code": job.country_code, "city": job.city, "status": "open"}
    avant = scores.match(db.session.get(Application, app_id).candidate, job)[0]
poids = {"p_skills": 0, "p_field": 0, "p_experience": 0, "p_education": 0, "p_location": 50, "p_soft_skills": 0, "p_languages": 0}
c.post(f"/recruteur/offres/{job_id}/modifier", data={**form, **poids})
with app.app_context():
    job = db.session.get(Job, job_id)
    a = db.session.get(Application, app_id)
    loc = scores.match(a.candidate, job)[1]["parts"]["location"]
    verifier(job.ponderations and job.ponderations["location"] == 50, "pondérations enregistrées sur l'offre")
    verifier(a.match_score == loc, f"score recalculé avec la pondération ({avant} -> {a.match_score})")
c.post(f"/recruteur/offres/{job_id}/modifier", data={**form, **{k: v for k, v in zip(poids, [35, 15, 15, 10, 10, 10, 5])}})
with app.app_context():
    verifier(db.session.get(Job, job_id).ponderations is None, "retour à la pondération par défaut")

# import d'une offre depuis le site de l'entreprise (page simulée)
PAGE = ('<html><head><script type="application/ld+json">{"@type":"JobPosting","title":"Chargé(e) de recrutement",'
        '"description":"<p>Licence en RH, 2 ans d\'expérience. Excel, Recrutement. Anglais. Rigueur.</p>",'
        '"employmentType":"CONTRACTOR","jobLocation":{"address":{"addressLocality":"Bouaké","addressCountry":"CI"}},'
        '"validThrough":"2027-01-15"}</script></head><body></body></html>')


class _Rep(io.BytesIO):
    headers = type("H", (), {"get_content_charset": lambda self: "utf-8"})()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


vrai_urlopen, vrai_safe = urllib.request.urlopen, suivi._safe_url
urllib.request.urlopen = lambda req, timeout=0: _Rep(PAGE.encode())
suivi._safe_url = import_offre._safe_url = lambda u: True
r = c.post("/recruteur/offres/importer", data={"url": "https://carrieres.exemple.ci/offre/42"})
page = r.get_data(as_text=True)
verifier(r.status_code == 200 and "Chargé(e) de recrutement" in page and "Bouak" in page, "import d'une offre depuis un site web")
verifier('value="freelance" selected' in page, "import : type de contrat reconnu")
urllib.request.urlopen, suivi._safe_url, import_offre._safe_url = vrai_urlopen, vrai_safe, vrai_safe
r = c.post("/recruteur/offres/importer", data={"url": "https://www.linkedin.com/jobs/view/1"}, follow_redirects=True)
verifier("interdit la lecture" in r.get_data(as_text=True), "import : LinkedIn refusé")

# --------------------------------------------------------------------------- paiement sans espèces
connecter(c, "aicha.kone@demo.tc")
page = c.get("/abonnement/").get_data(as_text=True)
verifier('value="cash"' not in page, "les espèces ne sont plus proposées")
with app.app_context():
    plan_id = Plan.query.filter_by(role="candidate").first().id
    n = Payment.query.count()
c.post(f"/abonnement/payer/{plan_id}", data={"method": "cash", "reference": "ABC"})
with app.app_context():
    verifier(Payment.query.count() == n, "paiement en espèces refusé par le serveur")

# --------------------------------------------------------------------------- une seule tentative parrain
def inscrire(c, email, prenom, nom):
    c.get("/auth/deconnexion")
    r = c.post("/auth/inscription", data={"email": email, "password": "Motdepasse1!", "password_confirm": "Motdepasse1!",
                                           "role": "sponsor", "first_name": prenom, "last_name": nom,
                                           "country_code": "CI", "city": "Abidjan"})
    assert r.status_code == 302, r.status_code


def statut(email):
    with app.app_context():
        return User.query.filter_by(email=email).first().sponsor.status


faible = {"kind": "individual", "position": "Assistant", "organization": "Société Test", "seniority": "employee",
          "years_experience": "0", "education_level": "bac", "team_size": "0", "professional_email": "test@gmail.com",
          "linkedin": "https://www.linkedin.com/in/test-parrain-refuse", "bio": ""}
fort = {"seniority": "executive", "years_experience": "20", "team_size": "50", "education_level": "bac5"}
n = random.randint(10000, 99999)
c1 = app.test_client()
inscrire(c1, f"refus{n}@exemple.ci", "Yao", f"Refuse{n}")
c1.post("/parrain/eligibilite", data=faible)
verifier(statut(f"refus{n}@exemple.ci") == "rejected", "parrain non éligible refusé")
c1.post("/parrain/eligibilite", data={**faible, **fort})
verifier(statut(f"refus{n}@exemple.ci") == "rejected", "pas de seconde tentative sur le même compte")
c2 = app.test_client()
inscrire(c2, f"autre{n}@exemple.ci", "Marc", f"Autre{n}")
c2.post("/parrain/eligibilite", data={**faible, **fort, "organization": "Autre SA", "professional_email": f"marc{n}@autre.ci"})
verifier(statut(f"autre{n}@exemple.ci") == "rejected", "autre compte, même LinkedIn : bloqué")
c3 = app.test_client()
inscrire(c3, f"meme{n}@exemple.ci", "Yao", f"Refuse{n}")
c3.post("/parrain/eligibilite", data={**faible, **fort, "linkedin": "", "professional_email": f"y{n}@zz.ci"})
verifier(statut(f"meme{n}@exemple.ci") == "rejected", "autre compte, même nom et même organisation : bloqué")
inscrire(c1, f"nav{n}@exemple.ci", "Paul", f"Nav{n}")
page = c1.get("/parrain/eligibilite").get_data(as_text=True)
verifier("Demande de parrainage refusée" in page, "autre compte depuis le même navigateur : bloqué")
c4 = app.test_client()
inscrire(c4, f"neuf{n}@exemple.ci", "Awa", f"Neuve{n}")
c4.post("/parrain/eligibilite", data={**faible, **fort, "organization": "Orange CI", "professional_email": f"awa{n}@orange.ci",
                                      "linkedin": f"https://linkedin.com/in/awa-{n}", "organization_website": "orange.ci",
                                      "bio": "x" * 90, "seniority": "director"})
verifier(statut(f"neuf{n}@exemple.ci") == "approved", "une nouvelle personne éligible n'est pas bloquée")

print(f"\nERREURS {len(erreurs)}")
sys.exit(1 if erreurs else 0)
