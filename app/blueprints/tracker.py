"""Mon suivi de candidatures (Job Application Tracking) : Kanban, tableau, projets de mobilité,
versions de CV, lettres, contacts RH, relances et historique des échanges."""
import csv
import io
import os
import secrets
from datetime import date, datetime, timedelta

from flask import (Blueprint, render_template, redirect, url_for, request, flash, abort, jsonify, session,
                   current_app, send_from_directory, Response)
from flask_login import current_user
from sqlalchemy import or_

from ..extensions import db
from ..models import (TrackedApplication, TrackerEvent, MobilityProject, CVVersion, Job, CONTRACT_TYPES,
                      TRACKER_STAGES, STAGE_KEYS, FINAL_STAGES)
from ..utils import role_required, access_required, to_int
from ..i18n import t
from ..services import tracker as svc, jobsources, hiring

bp = Blueprint("tracker", __name__)

EVENT_KINDS = [("note", "Note", "sticky-note"), ("email", "E-mail", "mail"), ("call", "Appel", "phone"),
               ("meeting", "Rendez-vous", "calendar"), ("interview", "Entretien", "users-round"),
               ("followup", "Relance", "bell-ring"), ("stage", "Étape", "git-commit-horizontal")]
PROJECT_COLORS = ["#D86730", "#5A2C19", "#2B6CB0", "#2F855A", "#8E44AD", "#D9A441", "#C0392B", "#0E7490"]


@bp.before_request
@role_required("candidate")
@access_required
def _guard():
    pass


def _own(tid):
    tr = db.get_or_404(TrackedApplication, tid)
    if tr.user_id != current_user.id:
        abort(404)
    return tr


def _parse_date(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def _filtered():
    a = request.args
    q = TrackedApplication.query.filter_by(user_id=current_user.id, archived=False)
    if a.get("project"):
        q = q.filter_by(project_id=to_int(a.get("project")))
    if a.get("stage"):
        q = q.filter_by(stage=a.get("stage"))
    if a.get("source"):
        q = q.filter(TrackedApplication.source == a.get("source"))
    if a.get("q"):
        s = f"%{a.get('q').strip()}%"
        q = q.filter(or_(TrackedApplication.title.ilike(s), TrackedApplication.company.ilike(s),
                         TrackedApplication.city.ilike(s)))
    if a.get("due") == "1":
        q = q.filter(TrackedApplication.next_followup <= date.today())
    return q


# --------------------------------------------------------------------------- vues Kanban / tableau
@bp.route("/")
def board():
    view = request.args.get("view", session.get("tracker_view", "kanban"))
    session["tracker_view"] = view
    sort = request.args.get("sort", "updated")
    items = _filtered().all()
    order = {"updated": lambda x: x.updated_at or x.created_at, "deadline": lambda x: x.deadline or date.max,
             "applied": lambda x: x.applied_at or date.min, "company": lambda x: (x.company or "").lower(),
             "stage": lambda x: STAGE_KEYS.index(x.stage), "priority": lambda x: x.priority or 2}
    items.sort(key=order.get(sort, order["updated"]), reverse=sort in ("updated", "applied"))
    all_items = TrackedApplication.query.filter_by(user_id=current_user.id, archived=False).all()
    projects = MobilityProject.query.filter_by(user_id=current_user.id).order_by(MobilityProject.created_at).all()
    sources = sorted({x.source for x in all_items if x.source})
    return render_template("tracker/board.html", items=items, view=view, stages=TRACKER_STAGES, projects=projects,
                           st=svc.stats(_filtered().all() if request.args.get("project") else all_items),
                           sources=sources, f=request.args.to_dict(), sort=sort, today=date.today())


@bp.route("/export.csv")
def export_csv():
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    labels = dict(TRACKER_STAGES)
    w.writerow(["Poste", "Entreprise", "Ville", "Pays", "Étape", "Projet", "Source", "Salaire", "Contrat",
                "Date de candidature", "Date limite", "Prochaine relance", "Contact", "E-mail contact", "Lien"])
    for x in _filtered().order_by(TrackedApplication.created_at.desc()).all():
        w.writerow([x.title, x.company, x.city, x.country_code, labels.get(x.stage), x.project.name if x.project else "",
                    x.source, x.salary, x.contract, x.applied_at or "", x.deadline or "", x.next_followup or "",
                    x.contact_name, x.contact_email, x.url])
    return Response("﻿" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=mes-candidatures.csv"})


@bp.route("/<int:tid>/etape", methods=["POST"])
def move(tid):
    tr = _own(tid)
    if svc.set_stage(tr, request.values.get("stage")):
        db.session.commit()
    if request.headers.get("HX-Request"):
        return jsonify(ok=True, stage=tr.stage, followup=str(tr.next_followup or ""))
    return redirect(request.referrer or url_for("tracker.detail", tid=tid))


# --------------------------------------------------------------------------- création / modification
def _fill(tr, f):
    tr.title = f.get("title", tr.title or "").strip() or tr.title
    for k in ("company", "city", "salary", "contract", "url", "source", "contact_name", "contact_role",
              "contact_email", "contact_phone", "notes", "description"):
        if k in f:
            setattr(tr, k, f.get(k, "").strip())
    if "country_code" in f:
        tr.country_code = f.get("country_code", "")[:2]
    if "cover_letter" in f:
        tr.cover_letter = f.get("cover_letter", "")
    tr.project_id = to_int(f.get("project_id")) or None
    tr.priority = to_int(f.get("priority"), 2)
    tr.deadline = _parse_date(f.get("deadline"))
    tr.applied_at = _parse_date(f.get("applied_at")) or tr.applied_at
    if "next_followup" in f:
        tr.next_followup = _parse_date(f.get("next_followup"))
    tr.cv_version_id = to_int(f.get("cv_version_id")) or None
    up = request.files.get("cv_file")
    if up and up.filename:
        ext = os.path.splitext(up.filename)[1].lower()
        if ext in (".pdf", ".doc", ".docx"):
            folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "cv")
            os.makedirs(folder, exist_ok=True)
            name = f"{current_user.id}_{secrets.token_hex(8)}{ext}"
            up.save(os.path.join(folder, name))
            tr.cv_file = name
        else:
            flash(t("CV : formats acceptés PDF, DOC, DOCX."), "warning")


def _form_ctx(tr):
    return dict(tr=tr, stages=TRACKER_STAGES, contracts=CONTRACT_TYPES,
                projects=MobilityProject.query.filter_by(user_id=current_user.id).all(),
                versions=CVVersion.query.filter_by(user_id=current_user.id).order_by(CVVersion.created_at.desc()).all())


@bp.route("/nouveau", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        tr = TrackedApplication(user_id=current_user.id, title=request.form.get("title", "").strip() or t("Sans titre"))
        _fill(tr, request.form)
        stage = request.form.get("stage", "identified")
        tr.stage = stage if stage in STAGE_KEYS else "identified"
        db.session.add(tr)
        db.session.flush()
        svc.add_event(tr, "stage", t("Ajoutée au suivi") + f" : {dict(TRACKER_STAGES)[tr.stage]}")
        if tr.stage in ("sent", "waiting") and not tr.next_followup:
            tr.applied_at = tr.applied_at or date.today()
            tr.next_followup = tr.applied_at + timedelta(days=svc.FOLLOWUP_DAYS)
        db.session.commit()
        flash(t("Opportunité ajoutée à votre suivi."), "success")
        if request.form.get("quick"):
            return redirect(request.referrer or url_for("tracker.board"))
        return redirect(url_for("tracker.detail", tid=tr.id))
    pre = session.pop("tracker_import", None) or {}
    tr = TrackedApplication(stage=request.args.get("stage", "identified"), priority=2,
                            project_id=to_int(request.args.get("project")), source=pre.get("source", ""))
    for k in ("title", "company", "city", "country_code", "salary", "contract", "url", "description"):
        if pre.get(k):
            setattr(tr, k, pre[k])
    if pre.get("deadline"):
        tr.deadline = _parse_date(pre["deadline"])
    return render_template("tracker/form.html", imported=pre, **_form_ctx(tr))


@bp.route("/importer", methods=["POST"])
def import_url():
    url = request.form.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    data = svc.import_from_url(url)
    if data.get("blocked"):
        flash(t("LinkedIn n'autorise pas la lecture automatique de ses pages : le lien est enregistré, complétez le poste et l'entreprise."), "info")
    elif data.get("error"):
        flash(t("Impossible de lire cette page. Le lien est enregistré, complétez les informations."), "warning")
    elif data.get("partial"):
        flash(t("Annonce lue partiellement : vérifiez et complétez les champs."), "info")
    else:
        flash(t("Annonce importée : vérifiez les informations puis enregistrez."), "success")
    session["tracker_import"] = data
    return redirect(url_for("tracker.new", project=request.form.get("project")))


@bp.route("/depuis-offre/<int:job_id>", methods=["POST"])
def from_job(job_id):
    job = db.get_or_404(Job, job_id)
    tr = TrackedApplication.query.filter_by(user_id=current_user.id, job_id=job.id).first()
    if not tr:
        tr = TrackedApplication(user_id=current_user.id, job_id=job.id, title=job.title, company=job.company.name,
                                city=job.city, country_code=job.country_code, contract=job.contract_type,
                                source="TalentConnect", stage="identified", deadline=job.deadline,
                                url=url_for("candidate.job_detail", job_id=job.id, _external=True),
                                salary=f"{job.salary_min or ''} – {job.salary_max} {job.currency}".strip(" –") if job.salary_max else "")
        db.session.add(tr)
        db.session.flush()
        svc.add_event(tr, "stage", t("Ajoutée au suivi depuis TalentConnect"))
        db.session.commit()
        flash(t("Offre ajoutée à votre suivi."), "success")
    return redirect(url_for("tracker.detail", tid=tr.id))


@bp.route("/<int:tid>", methods=["GET"])
def detail(tid):
    tr = _own(tid)
    return render_template("tracker/detail.html", events=tr.events.all(), kinds=EVENT_KINDS, today=date.today(),
                           **_form_ctx(tr))


@bp.route("/<int:tid>/modifier", methods=["GET", "POST"])
def edit(tid):
    tr = _own(tid)
    if request.method == "POST":
        _fill(tr, request.form)
        new_stage = request.form.get("stage")
        if new_stage and new_stage != tr.stage:
            svc.set_stage(tr, new_stage)
        db.session.commit()
        flash(t("Candidature mise à jour."), "success")
        return redirect(url_for("tracker.detail", tid=tr.id))
    return render_template("tracker/form.html", imported={}, **_form_ctx(tr))


@bp.route("/<int:tid>/evenement", methods=["POST"])
def add_event(tid):
    tr = _own(tid)
    kind = request.form.get("kind", "note")
    content = request.form.get("content", "").strip()
    at = request.form.get("at")
    when = datetime.fromisoformat(at) if at else datetime.utcnow()
    if content:
        svc.add_event(tr, kind, content, when)
    if kind == "followup":
        tr.next_followup = date.today() + timedelta(days=svc.FOLLOWUP_DAYS)
    nf = _parse_date(request.form.get("next_followup"))
    if nf:
        tr.next_followup = nf
    tr.updated_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for("tracker.detail", tid=tid) + "#historique")


@bp.route("/<int:tid>/relance", methods=["POST"])
def followup_done(tid):
    tr = _own(tid)
    svc.add_event(tr, "followup", request.form.get("content") or t("Relance effectuée"))
    tr.next_followup = date.today() + timedelta(days=svc.FOLLOWUP_DAYS)
    db.session.commit()
    flash(t("Relance notée. Prochain rappel dans {n} jours.", n=svc.FOLLOWUP_DAYS), "success")
    return redirect(request.referrer or url_for("tracker.board"))


@bp.route("/<int:tid>/lettre", methods=["POST"])
def letter(tid):
    tr = _own(tid)
    if tr.job:
        text = hiring.cover_letter(current_user, tr.job)
    else:
        text = hiring.cover_letter_for(current_user, tr.title, tr.company, tr.description or "")
    return render_template("candidate/_cover_letter.html", letter=text)


@bp.route("/<int:tid>/archiver", methods=["POST"])
def archive(tid):
    tr = _own(tid)
    tr.archived = True
    db.session.commit()
    flash(t("Candidature archivée."), "info")
    return redirect(url_for("tracker.board"))


@bp.route("/<int:tid>/cv")
def cv_file(tid):
    tr = _own(tid)
    if not tr.cv_file:
        abort(404)
    return send_from_directory(os.path.join(current_app.config["UPLOAD_FOLDER"], "cv"), tr.cv_file, as_attachment=True)


# --------------------------------------------------------------------------- projets de mobilité
@bp.route("/projets", methods=["GET", "POST"])
def projects():
    if request.method == "POST":
        pid = to_int(request.form.get("id"))
        p = db.session.get(MobilityProject, pid) if pid else MobilityProject(user_id=current_user.id)
        if p.user_id != current_user.id:
            abort(404)
        if request.form.get("action") == "delete" and pid:
            TrackedApplication.query.filter_by(project_id=p.id).update({"project_id": None})
            db.session.delete(p)
        else:
            p.name = request.form.get("name", "").strip() or t("Projet")
            p.country_code = request.form.get("country_code", "CI")
            p.city = request.form.get("city", "")
            p.target_role = request.form.get("target_role", "").strip()
            p.color = request.form.get("color", "#D86730")
            p.notes = request.form.get("notes", "").strip()
            if not pid:
                db.session.add(p)
        db.session.commit()
        flash(t("Projets mis à jour."), "success")
        return redirect(url_for("tracker.projects"))
    ps = MobilityProject.query.filter_by(user_id=current_user.id).order_by(MobilityProject.created_at).all()
    counts = {p.id: svc.stats(TrackedApplication.query.filter_by(user_id=current_user.id, project_id=p.id, archived=False).all()) for p in ps}
    return render_template("tracker/projects.html", projects=ps, counts=counts, colors=PROJECT_COLORS)


# --------------------------------------------------------------------------- versions de CV
@bp.route("/cv-versions", methods=["GET", "POST"])
def cv_versions():
    if request.method == "POST":
        v = db.session.get(CVVersion, to_int(request.form.get("id"))) if request.form.get("id") else None
        if v and v.user_id == current_user.id:
            if request.form.get("action") == "delete":
                TrackedApplication.query.filter_by(cv_version_id=v.id).update({"cv_version_id": None})
                db.session.delete(v)
            else:
                v.name = request.form.get("name", v.name).strip() or v.name
            db.session.commit()
        elif request.form.get("action") == "snapshot":
            cp = current_user.candidate
            db.session.add(CVVersion(user_id=current_user.id, name=request.form.get("name") or t("Mon CV"),
                                     data=cp.cv_data or {}))
            db.session.commit()
            flash(t("Version enregistrée."), "success")
        return redirect(url_for("tracker.cv_versions"))
    vs = CVVersion.query.filter_by(user_id=current_user.id).order_by(CVVersion.created_at.desc()).all()
    usage = {v.id: TrackedApplication.query.filter_by(cv_version_id=v.id).count() for v in vs}
    return render_template("tracker/cv_versions.html", versions=vs, usage=usage)


# --------------------------------------------------------------------------- offres externes (API officielles)
@bp.route("/recherche-externe")
def external():
    q = request.args.get("q", "").strip()
    where = request.args.get("where", "").strip()
    country = request.args.get("country", current_user.country_code or "")
    days = to_int(request.args.get("days"), 0)
    results, errors = ([], [])
    if q:
        results, errors = jobsources.search(q, where, country, days)
    tracked_urls = {x.url for x in TrackedApplication.query.filter_by(user_id=current_user.id).all()}
    return render_template("tracker/external.html", results=results, errors=errors, providers=jobsources.providers(),
                           f=dict(q=q, where=where, country=country, days=days), tracked=tracked_urls,
                           projects=MobilityProject.query.filter_by(user_id=current_user.id).all())
