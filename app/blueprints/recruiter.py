from collections import defaultdict
from datetime import datetime, timedelta, date

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, jsonify, g
from flask_login import current_user
from sqlalchemy import or_

from ..extensions import db
from ..models import (Job, Company, Application, User, CandidateProfile, Sponsorship, TalentPool, MessageTemplate,
                      APPLICATION_STATUSES, CONTRACT_TYPES, EDUCATION_LEVELS, EDU_RANK)
from ..utils import role_required, access_required, split_list, to_int, to_float
from ..i18n import t
from ..services import scoring, hiring, mailer, orientation
from .. import geo

bp = Blueprint("recruiter", __name__)


@bp.before_request
@role_required("recruiter")
def _guard():
    pass


def company():
    return current_user.recruiter.company


def own_job(job_id):
    job = db.get_or_404(Job, job_id)
    if job.company_id != company().id:
        abort(403)
    return job


def own_app(app_id):
    a = db.get_or_404(Application, app_id)
    if a.job.company_id != company().id:
        abort(403)
    return a


# --------------------------------------------------------------------------- tableau de bord
@bp.route("/")
def dashboard():
    co = company()
    jobs = Job.query.filter_by(company_id=co.id).all()
    apps = Application.query.join(Job).filter(Job.company_id == co.id).all()
    pending = [a for a in apps if a.status in ("received", "shortlisted")]
    decided = [a for a in apps if a.decided_at]
    avg_days = round(sum((a.decided_at - a.created_at).total_seconds() for a in decided) / 86400 / len(decided), 1) if decided else None
    since = datetime.utcnow() - timedelta(days=29)
    per_day = defaultdict(int)
    for a in apps:
        if a.created_at >= since:
            per_day[a.created_at.date().isoformat()] += 1
    days = [(since + timedelta(days=i)).date().isoformat() for i in range(30)]
    funnel = {s: sum(1 for a in apps if a.status == s) for s in APPLICATION_STATUSES}
    top_jobs = sorted(jobs, key=lambda j: -j.applications.count())[:5]
    pool_count = TalentPool.query.filter_by(company_id=co.id).count()
    return render_template("recruiter/dashboard.html", co=co, jobs=jobs, apps=apps, pending=pending, avg_days=avg_days,
                           response_rate=scoring.company_response_rate(co.id), days=days,
                           per_day=[per_day[d] for d in days], funnel=funnel, top_jobs=top_jobs, pool_count=pool_count,
                           open_jobs=sum(1 for j in jobs if j.status == "open"))


@bp.route("/entreprise", methods=["GET", "POST"], endpoint="company")
def company_view():
    co = company()
    if request.method == "POST":
        f = request.form
        co.name = f.get("name", co.name).strip() or co.name
        co.sector = f.get("sector", "").strip()
        co.size = f.get("size", "")
        co.website = f.get("website", "").strip()
        co.description = f.get("description", "").strip()
        co.registration_number = f.get("registration_number", "").strip()
        co.country_code = f.get("country_code", co.country_code)
        co.city = f.get("city", co.city)
        current_user.recruiter.position = f.get("position", "").strip()
        db.session.commit()
        flash(t("Entreprise mise à jour."), "success")
        return redirect(url_for("recruiter.company"))
    return render_template("recruiter/company.html", co=co)



# --------------------------------------------------------------------------- offres
@bp.route("/offres")
@access_required
def jobs():
    js = Job.query.filter_by(company_id=company().id).order_by(Job.created_at.desc()).all()
    counts = {}
    for j in js:
        apps = j.applications.all()
        counts[j.id] = {"total": len(apps), "new": sum(1 for a in apps if a.status == "received"),
                        "interview": sum(1 for a in apps if a.status == "interview")}
    return render_template("recruiter/jobs.html", jobs=js, counts=counts)


def _fill_job(job, f):
    job.title = f.get("title", "").strip()
    job.description = f.get("description", "").strip()
    job.field = f.get("field", "").strip()
    job.contract_type = f.get("contract_type", "cdi")
    job.education_level = f.get("education_level", "bac")
    job.min_experience = to_float(f.get("min_experience"), 0)
    job.skills = split_list(f.get("skills"))
    job.soft_skills = split_list(f.get("soft_skills"))
    job.languages = split_list(f.get("languages"))
    job.country_code = f.get("country_code", "CI")
    job.city = f.get("city", "").strip()
    job.remote = bool(f.get("remote"))
    job.salary_min = to_int(f.get("salary_min"))
    job.salary_max = to_int(f.get("salary_max"))
    job.currency = f.get("currency") or geo.currency_for(job.country_code)
    job.status = f.get("status", "open")
    d = f.get("deadline")
    job.deadline = date.fromisoformat(d) if d else None


@bp.route("/offres/nouvelle", methods=["GET", "POST"])
@access_required
def job_new():
    if not current_user.recruiter.is_verified:
        flash(t("Avant de publier une offre, prouvez que vous travaillez bien pour cette entreprise."), "warning")
        return redirect(url_for("recruiter.verification"))
    co = company()
    job = Job(company_id=co.id, recruiter_id=current_user.id, country_code=co.country_code, city=co.city,
              currency=geo.currency_for(co.country_code), skills=[], soft_skills=[], languages=[])
    if request.method == "POST":
        _fill_job(job, request.form)
        db.session.add(job)
        db.session.commit()
        n = len(pool_suggestions(job))
        flash(t("Offre publiée !") + (" " + t("{n} talent(s) de votre vivier correspondent déjà.", n=n) if n else ""), "success")
        return redirect(url_for("recruiter.job_pipeline", job_id=job.id))
    return render_template("recruiter/job_form.html", job=job, contracts=CONTRACT_TYPES, levels=EDUCATION_LEVELS,
                           fields=[x["field"] for x in orientation.FIELDS],
                           skill_suggestions=orientation.skill_suggestions(g.lang))


@bp.route("/offres/<int:job_id>/modifier", methods=["GET", "POST"])
@access_required
def job_edit(job_id):
    job = own_job(job_id)
    if request.method == "POST":
        _fill_job(job, request.form)
        db.session.commit()
        hiring.refresh_scores(job)
        flash(t("Offre mise à jour, scores recalculés."), "success")
        return redirect(url_for("recruiter.job_pipeline", job_id=job.id))
    return render_template("recruiter/job_form.html", job=job, contracts=CONTRACT_TYPES, levels=EDUCATION_LEVELS,
                           fields=[x["field"] for x in orientation.FIELDS],
                           skill_suggestions=orientation.skill_suggestions(g.lang))


@bp.route("/offres/<int:job_id>/statut", methods=["POST"])
@access_required
def job_toggle(job_id):
    job = own_job(job_id)
    job.status = "closed" if job.status == "open" else "open"
    db.session.commit()
    flash(t("Offre fermée.") if job.status == "closed" else t("Offre réouverte."), "info")
    return redirect(request.referrer or url_for("recruiter.jobs"))


@bp.route("/offres/<int:job_id>")
@access_required
def job_pipeline(job_id):
    job = own_job(job_id)
    apps = job.applications.order_by(Application.match_score.desc()).all()
    cols = {s: [a for a in apps if a.status == s] for s in APPLICATION_STATUSES}
    return render_template("recruiter/pipeline.html", job=job, cols=cols, total=len(apps),
                           suggestions=pool_suggestions(job)[:6])


@bp.route("/candidatures/<int:app_id>/statut", methods=["POST"])
@access_required
def set_status(app_id):
    a = own_app(app_id)
    new = request.values.get("status")
    if new not in APPLICATION_STATUSES:
        abort(400)
    notify = request.values.get("notify") == "1"
    if new == "hired":
        hiring.mark_hired(a)
    elif notify and new in ("interview", "second_chance", "rejected"):
        hiring.decide([a], new, current_user, note=request.values.get("note", ""))
    else:
        a.status = new
        if new in ("interview", "offer", "rejected", "second_chance"):
            a.decided_at = a.decided_at or datetime.utcnow()
        db.session.commit()
        hiring._sync(a)
    if request.headers.get("HX-Request"):
        return jsonify(ok=True)
    flash(t("Statut mis à jour."), "success")
    return redirect(request.referrer or url_for("recruiter.job_pipeline", job_id=a.job_id))


# --------------------------------------------------------------------------- tri assisté + envoi groupé
@bp.route("/offres/<int:job_id>/tri", methods=["GET", "POST"])
@access_required
def job_triage(job_id):
    job = own_job(job_id)
    if request.method == "POST":
        groups = defaultdict(list)
        for key, val in request.form.items():
            if key.startswith("g_") and val in ("interview", "second_chance", "rejected"):
                a = db.session.get(Application, int(key[2:]))
                if a and a.job_id == job.id:
                    groups[val].append(a)
        total = 0
        for g, apps in groups.items():
            total += hiring.decide(apps, g, current_user, note=request.form.get(f"note_{g}", ""),
                                   custom_subject=request.form.get(f"subject_{g}") or None,
                                   custom_body=request.form.get(f"body_{g}") or None)
        flash(t("{n} réponse(s) envoyée(s) par e-mail et dans l'app.", n=total), "success")
        return redirect(url_for("recruiter.job_pipeline", job_id=job.id))
    pending = job.applications.filter(Application.status.in_(["received", "shortlisted"])) \
        .order_by(Application.match_score.desc()).all()
    for a in pending:
        a.ai_group, a.ai_reason = scoring.triage(a)
    db.session.commit()
    tpls = {k: mailer.get_template(k, job.company_id) for k in ("interview", "second_chance", "rejected")}
    return render_template("recruiter/triage.html", job=job, pending=pending, tpls=tpls,
                           hi=scoring.Setting.get("triage_interview"), mid=scoring.Setting.get("triage_second_chance"))


# --------------------------------------------------------------------------- fiche candidat
def candidate_context(cand, job=None):
    sps = Sponsorship.query.filter_by(candidate_id=cand.id, status="active").all()
    ctx = dict(cand=cand, cp=cand.candidate, sps=sps, passport=scoring.skill_passport(cand),
               strength=round(scoring.sponsorship_strength(cand) * 100))
    if job:
        ctx["score"], ctx["d"] = scoring.match(cand, job)
    return ctx


@bp.route("/candidatures/<int:app_id>")
@access_required
def application(app_id):
    a = own_app(app_id)
    from ..models import Message
    msgs = Message.query.filter_by(application_id=a.id).order_by(Message.created_at).all()
    return render_template("recruiter/candidate.html", a=a, job=a.job, msgs=msgs, **candidate_context(a.candidate, a.job))


@bp.route("/talents/<int:user_id>")
@access_required
def candidate_view(user_id):
    cand = db.get_or_404(User, user_id)
    if cand.role != "candidate" or not cand.candidate or not cand.candidate.visible_to_recruiters:
        abort(404)
    jobs = Job.query.filter_by(company_id=company().id, status="open").all()
    return render_template("recruiter/candidate.html", a=None, job=None, msgs=[], my_jobs=jobs, **candidate_context(cand))


@bp.route("/talents/<int:user_id>/inviter", methods=["POST"])
@access_required
def invite(user_id):
    cand = db.get_or_404(User, user_id)
    job = own_job(int(request.form["job_id"]))
    link = url_for("candidate.job_detail", job_id=job.id, _external=True)
    mailer.send(cand, t("{company} vous invite à postuler : {job}", company=job.company.name, job=job.title),
                t("Bonjour {name},\n\nVotre profil a retenu l'attention de {company}. Nous vous invitons à postuler à l'offre « {job} ».\n\n{msg}\n\nVoir l'offre : {link}",
                  name=cand.first_name, company=job.company.name, job=job.title, msg=request.form.get("message", ""), link=link),
                kind="custom", sender=current_user)
    flash(t("Invitation envoyée à {name}.", name=cand.full_name), "success")
    return redirect(url_for("recruiter.candidate_view", user_id=cand.id))


@bp.route("/parrainages/<int:sid>/signaler", methods=["POST"])
@access_required
def flag_sponsorship(sid):
    s = db.get_or_404(Sponsorship, sid)
    s.status = "flagged"
    scoring.update_reputation(s.sponsor_id, -10)
    db.session.commit()
    flash(t("Parrainage signalé. L'équipe TalentConnect va l'examiner."), "info")
    return redirect(request.referrer or url_for("recruiter.dashboard"))


# --------------------------------------------------------------------------- recherche de talents
@bp.route("/talents")
@access_required
def talents():
    a = request.args
    skills = split_list(a.get("skills"))
    softs = split_list(a.get("soft_skills"))
    field = a.get("field", "").strip()
    country = a.get("country", "")
    city = a.get("city", "").strip()
    min_level = a.get("level", "")
    min_exp = to_float(a.get("min_exp"), 0)
    sponsored = a.get("sponsored") == "1"
    q = CandidateProfile.query.join(User).filter(CandidateProfile.visible_to_recruiters.is_(True), User.is_active_account.is_(True))
    if country:
        q = q.filter(or_(User.country_code == country, CandidateProfile.open_to_international.is_(True)))
    if city:
        q = q.filter(User.city.ilike(f"%{city}%"))
    if field:
        q = q.filter(CandidateProfile.field.ilike(f"%{field}%"))
    if min_exp:
        q = q.filter(CandidateProfile.years_experience >= min_exp)
    results = []
    searched = any([skills, softs, field, country, city, min_level, min_exp, sponsored])
    if searched:
        for cp in q.limit(500).all():
            if min_level and cp.edu_rank < EDU_RANK.get(min_level, 0):
                continue
            u = cp.user
            strength = scoring.sponsorship_strength(u)
            if sponsored and strength == 0:
                continue
            passport = scoring.skill_passport(u)
            s1, found, missing = scoring.overlap(skills, (cp.skills or []) + list(passport))
            s2, sfound, _ = scoring.overlap(softs, (cp.soft_skills or []) + list(passport))
            score = round((s1 * 0.6 + s2 * 0.2 + strength * 0.2) * 100)
            results.append({"u": u, "cp": cp, "score": score, "found": found, "sfound": sfound, "missing": missing,
                            "strength": round(strength * 100), "passport": passport})
        results.sort(key=lambda r: -r["score"])
    return render_template("recruiter/talents.html", results=results[:60], searched=searched, levels=EDUCATION_LEVELS,
                           f=dict(skills=", ".join(skills), soft_skills=", ".join(softs), field=field, country=country,
                                  city=city, level=min_level, min_exp=a.get("min_exp", ""), sponsored=sponsored),
                           fields=[x["field"] for x in orientation.FIELDS])


# --------------------------------------------------------------------------- vivier seconde chance
def pool_suggestions(job):
    out = []
    for p in TalentPool.query.filter_by(company_id=job.company_id).all():
        if job.applications.filter_by(candidate_id=p.candidate_id).first():
            continue
        s, _ = scoring.match(p.candidate, job)
        if s >= scoring.Setting.get("triage_second_chance"):
            out.append({"p": p, "score": s})
    return sorted(out, key=lambda x: -x["score"])


@bp.route("/vivier")
@access_required
def pool():
    co = company()
    items = TalentPool.query.filter_by(company_id=co.id).order_by(TalentPool.created_at.desc()).all()
    open_jobs = Job.query.filter_by(company_id=co.id, status="open").all()
    best = {}
    for it in items:
        scored = [(scoring.match(it.candidate, j)[0], j) for j in open_jobs if j.id != it.source_job_id]
        if scored:
            best[it.id] = max(scored, key=lambda x: x[0])
    return render_template("recruiter/pool.html", items=items, best=best)


@bp.route("/vivier/<int:pid>/retirer", methods=["POST"])
@access_required
def pool_remove(pid):
    p = db.get_or_404(TalentPool, pid)
    if p.company_id != company().id:
        abort(403)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for("recruiter.pool"))


# --------------------------------------------------------------------------- modèles de messages
@bp.route("/modeles", methods=["GET", "POST"])
@access_required
def templates():
    co = company()
    kinds = ["ack", "interview", "second_chance", "rejected"]
    if request.method == "POST":
        for k in kinds:
            tpl = MessageTemplate.query.filter_by(company_id=co.id, kind=k).first()
            if not tpl:
                tpl = MessageTemplate(company_id=co.id, kind=k)
                db.session.add(tpl)
            tpl.subject = request.form.get(f"subject_{k}", "")
            tpl.body = request.form.get(f"body_{k}", "")
        db.session.commit()
        flash(t("Modèles enregistrés."), "success")
        return redirect(url_for("recruiter.templates"))
    tpls = {k: mailer.get_template(k, co.id) for k in kinds}
    return render_template("recruiter/templates.html", tpls=tpls)


# --------------------------------------------------------------------------- preuve d'appartenance à l'entreprise
PROOF_TYPES = [("attestation", "Attestation de travail / employeur"), ("badge", "Badge ou carte professionnelle"),
               ("contrat", "Contrat ou bulletin de paie (montants masqués)"), ("mandat", "Mandat de recrutement signé")]
ALLOWED_PROOF = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def _domain(value):
    import re as _re
    v = (value or "").lower().strip()
    if "@" in v:
        v = v.split("@", 1)[1]
    v = _re.sub(r"^https?://", "", v).split("/")[0]
    return v[4:] if v.startswith("www.") else v


def _try_auto_verify(rp):
    """Vérification automatique : e-mail pro confirmé ET domaine identique au site de l'entreprise."""
    co = rp.company
    d_mail, d_site = _domain(rp.work_email), _domain(co.website if co else "")
    if rp.work_email_verified and d_mail and d_site and (d_mail == d_site or d_mail.endswith("." + d_site)) \
            and d_mail not in scoring.FREE_MAIL:
        rp.verification_status, rp.verification_method, rp.verified_at = "verified", "email_domain", datetime.utcnow()
        return True
    return False


@bp.route("/verification", methods=["GET", "POST"])
def verification():
    import os
    import secrets as _secrets
    from flask import current_app
    rp = current_user.recruiter
    co = rp.company
    if request.method == "POST":
        action = request.form.get("action")
        if action == "send_code":
            email = request.form.get("work_email", "").strip().lower()
            if "@" not in email or _domain(email) in scoring.FREE_MAIL:
                flash(t("Utilisez votre adresse professionnelle (pas Gmail, Yahoo, Outlook…)."), "danger")
            else:
                rp.work_email, rp.work_email_verified = email, False
                rp.email_code = f"{_secrets.randbelow(1000000):06d}"
                rp.email_code_sent_at = datetime.utcnow()
                db.session.commit()
                mailer.send(None, t("Votre code de vérification TalentConnect"),
                            t("Bonjour,\n\nVoici votre code pour confirmer que vous travaillez chez {company} : {code}\n\nIl est valable 30 minutes.",
                              company=co.name, code=rp.email_code), kind="system", email=email, sync=True)
                if not current_app.config.get("MAIL_USERNAME"):
                    flash(t("Mode test (e-mails non configurés) : votre code est {code}", code=rp.email_code), "info")
                else:
                    flash(t("Code envoyé à {email}.", email=email), "success")
        elif action == "check_code":
            code = request.form.get("code", "").strip()
            fresh = rp.email_code_sent_at and (datetime.utcnow() - rp.email_code_sent_at) < timedelta(minutes=30)
            if rp.email_code and fresh and code == rp.email_code:
                rp.work_email_verified, rp.email_code = True, None
                if _try_auto_verify(rp):
                    flash(t("Bravo ! Votre e-mail correspond au domaine de {company} : vous êtes recruteur vérifié.", company=co.name), "success")
                else:
                    flash(t("E-mail professionnel confirmé. Ajoutez un justificatif pour finaliser la vérification."), "success")
                db.session.commit()
            else:
                flash(t("Code incorrect ou expiré."), "danger")
        elif action == "upload":
            f = request.files.get("proof")
            ext = os.path.splitext(f.filename or "")[1].lower() if f else ""
            if not f or ext not in ALLOWED_PROOF:
                flash(t("Format accepté : PDF, PNG ou JPG (5 Mo maximum)."), "danger")
            else:
                folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "proofs")
                os.makedirs(folder, exist_ok=True)
                name = f"{current_user.id}_{_secrets.token_hex(8)}{ext}"
                f.save(os.path.join(folder, name))
                rp.proof_file, rp.proof_type = name, request.form.get("proof_type", "attestation")
                rp.proof_uploaded_at = datetime.utcnow()
                rp.linkedin = request.form.get("linkedin", rp.linkedin or "").strip()
                if rp.verification_status != "verified":
                    rp.verification_status, rp.verification_method = "pending", "document"
                db.session.commit()
                for admin in User.query.filter_by(role="admin").all():
                    mailer.send(admin, t("Recruteur à vérifier"),
                                t("{name} ({company}) a envoyé un justificatif d'appartenance à vérifier.",
                                  name=current_user.full_name, company=co.name), kind="system")
                flash(t("Justificatif envoyé. Notre équipe le vérifie sous 24 h."), "success")
        return redirect(url_for("recruiter.verification"))
    return render_template("recruiter/verification.html", rp=rp, co=co, proof_types=PROOF_TYPES,
                           site_domain=_domain(co.website))
