from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, g
from flask_login import current_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy import or_

from ..extensions import db
from ..models import (Job, Company, Application, Sponsorship, SponsorshipRequest, CONTRACT_TYPES,
                      EDUCATION_LEVELS, APPLICATION_STATUSES, Message, Setting)
from ..utils import role_required, access_required, split_list, to_float, to_int
from ..i18n import t
from ..services import scoring, hiring, orientation, mailer
from ..cvbuilder import build_page

bp = Blueprint("candidate", __name__)

SOFT_SKILLS_SUGGESTIONS = ["Communication", "Leadership", "Travail d'équipe", "Rigueur", "Autonomie", "Adaptabilité",
                           "Créativité", "Gestion du stress", "Esprit d'analyse", "Organisation", "Empathie",
                           "Résolution de problèmes", "Sens du service", "Négociation", "Prise d'initiative", "Ponctualité"]
FIELDS_SUGGESTIONS = [f["field"] for f in orientation.FIELDS]


@bp.before_request
@role_required("candidate")
def _guard():
    pass


def cp():
    return current_user.candidate


def default_cv_from_profile(u):
    p = u.candidate
    return {
        "profile": {"name": u.full_name, "role": p.headline or p.desired_position or "", "tagline": "",
                    "phone": u.phone or "", "email": u.email, "linkedin": p.linkedin or "",
                    "city": ", ".join(x for x in [u.city, u.country_code] if x)},
        "summary": p.summary or "",
        "comp": [{"label": "Compétences", "on": True, "items": p.skills or []}],
        "soft": p.soft_skills or [],
        "lang": [{"name": l.get("name"), "level": l.get("level", "")} for l in (p.languages or []) if isinstance(l, dict)],
    }


# --------------------------------------------------------------------------- tableau de bord
@bp.route("/")
def dashboard():
    u = current_user
    score, actions = scoring.employability(u)
    apps = Application.query.filter_by(candidate_id=u.id).order_by(Application.created_at.desc()).all()
    by_status = {s: sum(1 for a in apps if a.status == s) for s in APPLICATION_STATUSES}
    recos = []
    if u.has_access:
        recos = recommended_jobs(limit=4)
    sponsors = Sponsorship.query.filter_by(candidate_id=u.id, status="active").count()
    msgs = Message.query.filter_by(recipient_id=u.id).order_by(Message.created_at.desc()).limit(5).all()
    return render_template("candidate/dashboard.html", score=score, actions=actions, apps=apps[:5], by_status=by_status,
                           total_apps=len(apps), recos=recos, sponsors=sponsors, msgs=msgs,
                           completeness=round(scoring.profile_completeness(u) * 100))


def recommended_jobs(limit=None, jobs=None):
    u = current_user
    if jobs is None:
        jobs = Job.query.filter_by(status="open").order_by(Job.created_at.desc()).limit(400).all()
    scored = []
    for j in jobs:
        s, d = scoring.match(u, j)
        scored.append({"job": j, "score": s, "detail": d})
    scored.sort(key=lambda x: -x["score"])
    if limit:
        scored = scored[:limit]
    for x in scored:
        x["prob"] = scoring.call_probability(u, x["job"], x["score"])
    return scored


# --------------------------------------------------------------------------- profil
@bp.route("/bienvenue")
def onboarding():
    flash(t("Commençons par votre profil : il sert à vous proposer les bonnes offres."), "info")
    return redirect(url_for("candidate.profile"))


@bp.route("/profil", methods=["GET", "POST"])
def profile():
    p = cp()
    u = current_user
    if request.method == "POST":
        f = request.form
        p.headline = f.get("headline", "").strip()
        p.summary = f.get("summary", "").strip()
        p.field = f.get("field", "").strip()
        p.education_level = f.get("education_level", "bac")
        p.years_experience = to_float(f.get("years_experience"), 0)
        p.skills = split_list(f.get("skills"))
        p.soft_skills = split_list(f.get("soft_skills"))
        langs = []
        for name, lvl in zip(f.getlist("lang_name"), f.getlist("lang_level")):
            if name.strip():
                langs.append({"name": name.strip(), "level": lvl.strip()})
        p.languages = langs
        p.desired_position = f.get("desired_position", "").strip()
        p.desired_contracts = f.getlist("desired_contracts")
        p.desired_cities = split_list(f.get("desired_cities"))
        p.open_to_international = bool(f.get("open_to_international"))
        p.salary_expectation = to_int(f.get("salary_expectation"))
        p.linkedin = f.get("linkedin", "").strip()
        p.visible_to_recruiters = bool(f.get("visible_to_recruiters"))
        u.country_code = f.get("country_code", u.country_code)
        u.city = f.get("city", u.city)
        u.phone = f.get("phone", u.phone)
        db.session.commit()
        flash(t("Profil enregistré. Vos recommandations sont mises à jour."), "success")
        return redirect(url_for("candidate.profile"))
    return render_template("candidate/profile.html", p=p, contracts=CONTRACT_TYPES, levels=EDUCATION_LEVELS,
                           soft_suggestions=SOFT_SKILLS_SUGGESTIONS, field_suggestions=FIELDS_SUGGESTIONS,
                           skill_suggestions=orientation.skill_suggestions(g.lang),
                           completeness=round(scoring.profile_completeness(u) * 100),
                           passport=scoring.skill_passport(u))


@bp.route("/cv-builder")
def cv_builder():
    data = cp().cv_data or default_cv_from_profile(current_user)
    return build_page(data, logged_in=True, csrf=generate_csrf())


# --------------------------------------------------------------------------- offres
@bp.route("/offres")
@access_required
def jobs():
    p = cp()
    u = current_user
    a = request.args
    for_me = a.get("mode", "me") == "me"
    # Filtres pré-remplis à partir du profil du candidat
    country = a.get("country", u.country_code if for_me else "")
    field = a.get("field", p.field if for_me else "")
    city = a.get("city", "")
    q = a.get("q", "").strip()
    company = a.get("company", "").strip()
    contract = a.get("contract", "")
    level = a.get("level", "")
    query = Job.query.filter_by(status="open").join(Company)
    if country:
        query = query.filter(or_(Job.country_code == country, Job.remote.is_(True)))
    if city:
        query = query.filter(Job.city.ilike(f"%{city}%"))
    if field:
        query = query.filter(or_(Job.field.ilike(f"%{field}%"), Job.title.ilike(f"%{field}%")))
    if q:
        query = query.filter(or_(Job.title.ilike(f"%{q}%"), Job.description.ilike(f"%{q}%")))
    if company:
        query = query.filter(Company.name.ilike(f"%{company}%"))
    if contract:
        query = query.filter(Job.contract_type == contract)
    if level:
        query = query.filter(Job.education_level == level)
    results = recommended_jobs(jobs=query.order_by(Job.created_at.desc()).limit(300).all())
    if a.get("sort") == "recent":
        results.sort(key=lambda x: x["job"].created_at, reverse=True)
    applied = {x.job_id for x in Application.query.filter_by(candidate_id=u.id).all()}
    tpl = "candidate/_job_list.html" if request.headers.get("HX-Request") else "candidate/jobs.html"
    return render_template(tpl, results=results, applied=applied, contracts=CONTRACT_TYPES, levels=EDUCATION_LEVELS,
                           f=dict(country=country, field=field, city=city, q=q, company=company, contract=contract,
                                  level=level, mode="me" if for_me else "all", sort=a.get("sort", "match")),
                           field_suggestions=FIELDS_SUGGESTIONS)


@bp.route("/offres/<int:job_id>")
@access_required
def job_detail(job_id):
    job = db.get_or_404(Job, job_id)
    job.views = (job.views or 0) + 1
    db.session.commit()
    score, detail = scoring.match(current_user, job)
    prob = scoring.call_probability(current_user, job, score)
    app = Application.query.filter_by(job_id=job.id, candidate_id=current_user.id).first()
    return render_template("candidate/job_detail.html", job=job, score=score, d=detail, prob=prob, app=app,
                           response_rate=scoring.company_response_rate(job.company_id),
                           n_apps=job.applications.count())


@bp.route("/offres/<int:job_id>/lettre", methods=["POST"])
@access_required
def cover_letter(job_id):
    job = db.get_or_404(Job, job_id)
    return render_template("candidate/_cover_letter.html", letter=hiring.cover_letter(current_user, job))


@bp.route("/offres/<int:job_id>/postuler", methods=["POST"])
@access_required
def apply(job_id):
    job = db.get_or_404(Job, job_id)
    if job.status != "open":
        flash(t("Cette offre n'est plus ouverte."), "warning")
        return redirect(url_for("candidate.job_detail", job_id=job.id))
    a, created = hiring.apply(current_user, job, request.form.get("cover_letter", ""))
    if created:
        flash(t("Candidature envoyée ! Un accusé de réception vient de vous être adressé."), "success")
    else:
        flash(t("Vous avez déjà postulé à cette offre."), "info")
    return redirect(url_for("candidate.applications"))


@bp.route("/candidatures")
@access_required
def applications():
    apps = Application.query.filter_by(candidate_id=current_user.id).order_by(Application.created_at.desc()).all()
    return render_template("candidate/applications.html", apps=apps)


# --------------------------------------------------------------------------- parrainages
@bp.route("/parrainages", methods=["GET", "POST"])
@access_required
def sponsorships():
    u = current_user
    if request.method == "POST":
        r = SponsorshipRequest(candidate_id=u.id, invitee_name=request.form.get("invitee_name", "").strip(),
                               invitee_email=request.form.get("invitee_email", "").strip(),
                               relation=request.form.get("relation", "").strip(),
                               message=request.form.get("message", "").strip())
        db.session.add(r)
        db.session.commit()
        link = url_for("sponsor.invitation", token=r.token, _external=True)
        if r.invitee_email:
            body = t("Bonjour {name},\n\n{candidate} vous sollicite pour un parrainage sur TalentConnect, la plateforme qui connecte les talents aux entreprises.\n\n« {message} »\n\nVotre recommandation l'aidera à être reconnu(e) par les recruteurs. Cela prend environ 5 minutes :\n{link}\n\nMerci pour votre confiance.",
                     name=r.invitee_name or "", candidate=u.full_name, message=r.message or t("J'aimerais beaucoup que vous me recommandiez."), link=link)
            mailer.send(None, t("{candidate} vous demande un parrainage", candidate=u.full_name), body,
                        kind="sponsorship", sender=u, email=r.invitee_email)
            flash(t("Invitation envoyée à {email}. Vous pouvez aussi partager le lien directement.", email=r.invitee_email), "success")
        else:
            flash(t("Lien de parrainage créé : copiez-le et envoyez-le à votre parrain."), "success")
        return redirect(url_for("candidate.sponsorships", new=r.id))
    reqs = SponsorshipRequest.query.filter_by(candidate_id=u.id).order_by(SponsorshipRequest.created_at.desc()).all()
    sps = Sponsorship.query.filter_by(candidate_id=u.id).order_by(Sponsorship.created_at.desc()).all()
    return render_template("candidate/sponsorships.html", reqs=reqs, sps=sps, passport=scoring.skill_passport(u),
                           strength=round(scoring.sponsorship_strength(u) * 100), new_id=request.args.get("new", type=int))


# --------------------------------------------------------------------------- orientation
@bp.route("/orientation", methods=["GET", "POST"], endpoint="orientation")
@access_required
def orientation_view():
    p = cp()
    if request.method == "POST":
        answers = {i: to_int(request.form.get(f"q{i}"), 3) for i in range(len(orientation.QUESTIONS))}
        subjects = request.form.getlist("subjects")
        scores = orientation.score_answers(answers)
        code, recos = orientation.recommend(scores, subjects)
        p.riasec = {"scores": scores, "code": code, "subjects": subjects,
                    "recos": [{"field": r["field"], "score": r["score"], "jobs": r["jobs"]} for r in recos]}
        db.session.commit()
        return redirect(url_for("candidate.orientation", result=1))
    show_result = p.riasec and request.args.get("retake") != "1"
    open_by_field = {}
    if show_result:
        for r in p.riasec.get("recos", []):
            key = r["field"].split("/")[0].strip()
            open_by_field[r["field"]] = Job.query.filter(Job.status == "open", or_(Job.field.ilike(f"%{key}%"), Job.title.ilike(f"%{key}%"))).count()
    return render_template("candidate/orientation.html", questions=orientation.QUESTIONS, subjects=orientation.SUBJECTS,
                           types=orientation.translated_types(), result=p.riasec if show_result else None,
                           open_by_field=open_by_field,
                           onet=orientation.onet_matches(p.riasec.get("code")) if show_result else [])

