"""Test de parcours complet (smoke test) de TalentConnect.

Parcourt toutes les pages de chaque rôle (public, candidat, recruteur, parrain, admin),
soumet les principaux formulaires et vérifie qu'aucune page ne renvoie d'erreur.
Prérequis : base de démonstration créée (flask --app run.py seed-demo).
Usage : python tests/test_parcours.py   ->  affiche "ERRORS 0" si tout fonctionne.
"""
import re, sys
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from app import create_app
from app.modeles import *
app = create_app()
app.config['WTF_CSRF_ENABLED'] = False
app.config['MAIL_USERNAME'] = ''
c = app.test_client()
errors = []
def get(url, expect=(200,302)):
    r = c.get(url)
    if r.status_code not in expect:
        errors.append((url, r.status_code, r.data[-1500:].decode('utf8','ignore')))
    return r
def login(email):
    c.get('/auth/deconnexion')
    pw = 'Demo1234!' if 'demo' in email else app.config['ADMIN_PASSWORD']
    r = c.post('/auth/connexion', data={'email': email, 'password': pw})
    assert r.status_code == 302, (email, r.status_code)
for u in ['/', '/cv', '/cv/cadre', '/abonnement/', '/auth/connexion', '/auth/inscription', '/auth/inscription?role=sponsor', '/api/cities/CI', '/xyz']:
    get(u, (200,302,404))
with app.app_context():
    tok = SponsorshipRequest.query.filter_by(status='sent').first().token
    job = Job.query.first(); app_ = Application.query.first(); cand = User.query.filter_by(email='aicha.kone@demo.tc').first()
    rec_email = app_.job.recruiter.email
get(f'/parrain/invitation/{tok}')
# candidate
login('aicha.kone@demo.tc')
for u in ['/candidat/', '/candidat/profil', '/candidat/cv-builder', '/candidat/offres', '/candidat/offres?mode=all', f'/candidat/offres/{job.id}', '/candidat/candidatures', '/candidat/parrainages', '/candidat/orientation', '/marche', '/assistant/', f'/assistant/discuter/{cand.id}', '/messages/', '/messages/?list=1', '/candidat/cv-builder/cadre', '/candidat/suivi/', '/candidat/suivi/?view=table', '/candidat/suivi/?view=table&sort=deadline&stage=sent', '/candidat/suivi/nouveau', '/candidat/suivi/projets', '/candidat/suivi/cv-versions', '/candidat/suivi/recherche-externe?q=data', '/candidat/suivi/export.csv', '/candidat/offres?posted=7', '/auth/compte', '/abonnement/']:
    get(u)
r = c.post(f'/candidat/offres/{job.id}/lettre'); print('letter', r.status_code, len(r.data))
r = c.post('/candidat/orientation', data={f'q{i}': (i%5)+1 for i in range(30)} | {'subjects': ['Mathématiques','Informatique']}); print('orient', r.status_code)
get('/candidat/orientation')
r = c.post(f'/assistant/discuter/{cand.id}', data={'question': 'Quelles sont ses compétences ?'}, headers={'HX-Request':'true'}); print('chat', r.status_code, r.data[:300])
r = c.post('/candidat/parrainages', data={'invitee_name':'Test','invitee_email':'x@y.com','relation':'boss','message':'hi'}); print('spreq', r.status_code)
r = c.post('/api/cv', json={'profile':{'name':'Aïcha','role':'Data Analyst'},'comp':[{'label':'C','on':True,'items':['dbt','Looker']}]}); print('cv', r.status_code, r.data)
r = c.post('/candidat/profil', data={'headline':'X','skills':'SQL, Python','soft_skills':'Rigueur','lang_name':['Français'],'lang_level':['C2'],'country_code':'CI','city':'Abidjan','education_level':'bac5','years_experience':'3','visible_to_recruiters':'on'}); print('profile', r.status_code)
# recruiter
login(rec_email)
for u in ['/recruteur/', '/recruteur/entreprise', '/recruteur/offres', '/recruteur/offres/nouvelle', f'/recruteur/offres/{app_.job_id}', f'/recruteur/offres/{app_.job_id}/modifier', f'/recruteur/offres/{app_.job_id}/tri', f'/recruteur/candidatures/{app_.id}', '/recruteur/talents', '/recruteur/talents?skills=Python,SQL&sponsored=1', '/recruteur/talents?skills=Python', f'/recruteur/talents/{cand.id}', '/recruteur/vivier', '/recruteur/modeles', '/recruteur/verification', '/marche', '/assistant/', '/messages/']:
    get(u)
# Publier une offre exige un recruteur vérifié : on vérifie celui de la démo pour le test.
with app.app_context():
    from app.extensions import db
    rp = User.query.filter_by(email=rec_email).first().recruiter
    rp.verification_status = 'verified'; db.session.commit()
r = c.post('/recruteur/offres/nouvelle', data={'title':'Test job','description':'desc','skills':'Python, SQL','country_code':'SN','city':'Dakar','contract_type':'cdi','education_level':'bac3','min_experience':'1','status':'open'}); print('newjob', r.status_code, r.location)
with app.app_context():
    j = Job.query.filter_by(title='Test job').first(); print('currency', j.currency)
    pend = Application.query.filter(Application.job_id==app_.job_id, Application.status.in_(['received','shortlisted'])).all()
    data = {f'g_{a.id}': g for a,g in zip(pend, ['interview','second_chance','rejected','rejected'])}
r = c.post(f'/recruteur/offres/{app_.job_id}/tri', data=data | {'note_interview':'Lundi 10h'}); print('triage', r.status_code, len(data))
r = c.post(f'/recruteur/candidatures/{app_.id}/statut', data={'status':'hired'}); print('hired', r.status_code)
# sponsor
login('kouadio.nguessan@demo.tc')
for u in ['/parrain/', '/parrain/eligibilite', f'/parrain/invitation/{tok}']:
    get(u)
with app.app_context():
    tok2 = SponsorshipRequest.query.filter_by(invitee_name='Test').first().token
r = c.post(f'/parrain/invitation/{tok2}', data={'relation':'manager','period':'2020','organization':'X','skill_SQL':'5','soft_Rigueur':'4','recommendation':'Excellent professionnel, je recommande vivement sans hésiter un instant.','would_rehire':'on'}); print('endorse', r.status_code, r.location)
# admin
login(app.config['ADMIN_EMAIL'])  # identifiants admin lus dans .env
for u in ['/admin/', '/admin/utilisateurs', '/admin/utilisateurs?role=candidate&access=no', '/admin/paiements', '/admin/paiements?status=all', '/admin/formules', '/admin/parrains', '/admin/parrains?status=all', '/admin/entreprises', '/admin/reglages', '/admin/recruteurs', '/admin/recruteurs?status=all', '/marche', '/messages/']:
    get(u)
with app.app_context():
    p = Payment.query.filter_by(status='pending').first()
r = c.post(f'/admin/paiements/{p.id}/confirm'); print('confirm', r.status_code)
r = c.post('/admin/reglages', data={'triage_interview':'72','triage_second_chance':'45','sponsor_auto_approve':'75','sponsor_min_score':'60','sponsor_max_per_year':'10','w_skills':'35'}); print('settings', r.status_code)
# languages
for l in ['en','es','pt']:
    get(f'/langue/{l}?next=/admin/')
    get('/admin/')
# new user registration + paywall
c.get('/auth/deconnexion')
r = c.post('/auth/inscription', data={'role':'candidate','first_name':'Nouveau','last_name':'User','email':'new@x.com','password':'Password1','country_code':'CA','city':'Montréal'}); print('register', r.status_code, r.location)
r = c.get('/candidat/offres'); print('paywall', r.status_code, r.location)
get('/candidat/'); get('/candidat/cv-builder')

# JAT actions as candidate
login('aicha.kone@demo.tc')
with app.app_context():
    from app.modeles import TrackedApplication, User
    aid = User.query.filter_by(email='aicha.kone@demo.tc').first().id
    tr = TrackedApplication.query.filter_by(user_id=aid).first(); tid = tr.id
    print('trackers', TrackedApplication.query.filter_by(user_id=aid).count())
get(f'/candidat/suivi/{tid}'); get(f'/candidat/suivi/{tid}/modifier')
r = c.post(f'/candidat/suivi/{tid}/etape', data={'stage':'interview'}, headers={'HX-Request':'true'}); print('move', r.status_code, r.data[:80])
r = c.post(f'/candidat/suivi/{tid}/evenement', data={'kind':'call','content':'Appel RH','next_followup':'2026-11-20'}); print('event', r.status_code)
r = c.post(f'/candidat/suivi/{tid}/relance'); print('followup', r.status_code)
r = c.post(f'/candidat/suivi/{tid}/lettre'); print('letter', r.status_code, len(r.data))
r = c.post('/candidat/suivi/nouveau', data={'title':'Test ext','company':'ACME','stage':'sent','source':'LinkedIn','priority':'1'}); print('new', r.status_code, r.location)
r = c.post('/candidat/suivi/importer', data={'url':'https://www.linkedin.com/jobs/view/123'}); print('import li', r.status_code, r.location)
get('/candidat/suivi/nouveau')
r = c.post('/candidat/suivi/projets', data={'name':'Dakar','country_code':'SN','city':'Dakar','color':'#2F855A'}); print('proj', r.status_code)
r = c.post('/api/cv/version', json={'name':'V test','data':{'a':1}}); print('cvver', r.status_code, r.data)
r = c.post('/candidat/suivi/cv-versions', data={'action':'snapshot','name':'Snap'}); print('snap', r.status_code)
with app.app_context():
    j = Job.query.filter_by(status='open').first().id
r = c.post(f'/candidat/suivi/depuis-offre/{j}'); print('fromjob', r.status_code)
# messages
with app.app_context():
    rec = User.query.filter_by(email='awa.traore@demo.tc').first().id
r = c.get(f'/messages/c/{rec}'); print('thread', r.status_code)
r = c.post(f'/messages/c/{rec}', data={'body':'Bonjour, merci !'}, headers={'HX-Request':'true'}); print('send', r.status_code, b'Bonjour, merci' in r.data)
get(f'/messages/c/0'); get(f'/messages/c/{rec}/fil')
# recruiter verification flow with new recruiter
c.get('/auth/deconnexion')
r = c.post('/auth/inscription', data={'role':'recruiter','first_name':'Rex','last_name':'Test','email':'rex@x.com','password':'Password1','company_name':'Acme','country_code':'CI','city':'Abidjan'}); print('reg rec', r.status_code)
r = c.get('/recruteur/offres/nouvelle'); print('gate', r.status_code, r.location)
r = c.post('/recruteur/entreprise', data={'name':'Acme','website':'acme.ci','country_code':'CI','city':'Abidjan'}); print('company', r.status_code)
r = c.post('/recruteur/verification', data={'action':'send_code','work_email':'rex@acme.ci'}); print('code', r.status_code)
with app.app_context():
    code = User.query.filter_by(email='rex@x.com').first().recruiter.email_code
r = c.post('/recruteur/verification', data={'action':'check_code','code':code}); print('check', r.status_code)
with app.app_context():
    print('status', User.query.filter_by(email='rex@x.com').first().recruiter.verification_status)
import io
r = c.post('/recruteur/verification', data={'action':'upload','proof_type':'badge','proof':(io.BytesIO(b'%PDF-1.4 test'),'p.pdf')}, content_type='multipart/form-data'); print('upload', r.status_code)
print('ERRORS', len(errors))
for e in errors: print(e[0], e[1]); print(e[2][-1200:]); print('-----')
