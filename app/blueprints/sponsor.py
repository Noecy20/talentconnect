from datetime import datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import current_user, login_required

from ..extensions import db
from ..models import SponsorProfile, SponsorshipRequest, Sponsorship, Setting, EDUCATION_LEVELS
from ..utils import role_required, to_int
from ..i18n import t
from ..services import scoring, mailer

bp = Blueprint("sponsor", __name__)

SENIORITIES = ["employee", "manager", "senior_manager", "director", "executive"]


def used_this_year(uid):
    since = datetime.utcnow() - timedelta(days=365)
    return Sponsorship.query.filter(Sponsorship.sponsor_id == uid, Sponsorship.created_at >= since).count()


@bp.route("/invitation/<token>", methods=["GET", "POST"])
def invitation(token):
    req = SponsorshipRequest.query.filter_by(token=token).first_or_404()
    cand = req.candidate
    if req.status == "sent":
        req.status = "opened"
        db.session.commit()
    sp = current_user.sponsor if current_user.is_authenticated and current_user.role == "sponsor" else None
    if request.method == "POST":
        if not sp:
            abort(403)
        if sp.status not in ("approved", "pending_review"):
            flash(t("Vous devez d'abord réussir le test d'éligibilité."), "warning")
            return redirect(url_for("sponsor.eligibility", next=request.path))
        if Sponsorship.query.filter_by(sponsor_id=current_user.id, candidate_id=cand.id).first():
            flash(t("Vous avez déjà parrainé ce candidat."), "info")
            return redirect(url_for("sponsor.dashboard"))
        if used_this_year(current_user.id) >= Setting.get("sponsor_max_per_year"):
            flash(t("Vous avez atteint le nombre maximal de parrainages pour cette année."), "danger")
            return redirect(url_for("sponsor.dashboard"))
        f = request.form
        skill_r = {k[6:]: to_int(v, 0) for k, v in f.items() if k.startswith("skill_") and to_int(v, 0)}
        soft_r = {k[5:]: to_int(v, 0) for k, v in f.items() if k.startswith("soft_") and to_int(v, 0)}
        s = Sponsorship(sponsor_id=current_user.id, candidate_id=cand.id, request_id=req.id,
                        relation=f.get("relation", ""), period=f.get("period", ""), organization=f.get("organization", ""),
                        skill_ratings=skill_r, soft_ratings=soft_r, recommendation=f.get("recommendation", "").strip(),
                        would_rehire=bool(f.get("would_rehire")),
                        status="active" if sp.status == "approved" else "pending")
        db.session.add(s)
        req.status = "completed"
        db.session.commit()
        mailer.send(cand, t("{name} vous a parrainé(e) sur TalentConnect 🎉", name=current_user.full_name),
                    t("Bonne nouvelle ! {name} vient de publier une recommandation pour vous. Elle apparaît désormais sur votre fiche, visible des recruteurs.", name=current_user.full_name),
                    kind="sponsorship", sender=current_user)
        flash(t("Merci ! Votre recommandation a été enregistrée."), "success")
        return redirect(url_for("sponsor.dashboard"))
    cp = cand.candidate
    return render_template("sponsor/invitation.html", req=req, cand=cand, cp=cp, sp=sp)


@bp.route("/")
@login_required
@role_required("sponsor")
def dashboard():
    sp = current_user.sponsor
    sps = Sponsorship.query.filter_by(sponsor_id=current_user.id).order_by(Sponsorship.created_at.desc()).all()
    from ..models import Application
    outcomes = {}
    for s in sps:
        apps = Application.query.filter_by(candidate_id=s.candidate_id).all()
        outcomes[s.id] = {"apps": len(apps), "interviews": sum(1 for a in apps if a.status in ("interview", "offer", "hired")),
                          "hired": any(a.status == "hired" for a in apps)}
    return render_template("sponsor/dashboard.html", sp=sp, sps=sps, outcomes=outcomes,
                           used=used_this_year(current_user.id), maxi=Setting.get("sponsor_max_per_year"))


@bp.route("/eligibilite", methods=["GET", "POST"])
@login_required
@role_required("sponsor")
def eligibility():
    sp = current_user.sponsor
    if request.method == "POST":
        f = request.form
        sp.kind = f.get("kind", "individual")
        sp.position = f.get("position", "").strip()
        sp.organization = f.get("organization", "").strip()
        sp.organization_website = f.get("organization_website", "").strip()
        sp.professional_email = f.get("professional_email", "").strip()
        sp.linkedin = f.get("linkedin", "").strip()
        sp.seniority = f.get("seniority", "employee")
        sp.years_experience = to_int(f.get("years_experience"), 0)
        sp.education_level = f.get("education_level", "bac")
        sp.team_size = to_int(f.get("team_size"), 0)
        sp.registration_number = f.get("registration_number", "").strip()
        sp.bio = f.get("bio", "").strip()
        status = scoring.decide_sponsor(sp, current_user)
        db.session.commit()
        if status == "approved":
            # Les recommandations en attente deviennent visibles
            Sponsorship.query.filter_by(sponsor_id=current_user.id, status="pending").update({"status": "active"})
            db.session.commit()
            flash(t("Félicitations ! Vous êtes parrain certifié TalentConnect."), "success")
        elif status == "pending_review":
            flash(t("Votre dossier est en cours de vérification par notre équipe."), "info")
        else:
            flash(t("Votre profil ne remplit pas encore les critères pour devenir parrain."), "warning")
        nxt = request.args.get("next")
        if nxt and nxt.startswith("/") and status != "rejected":
            return redirect(nxt)
        return redirect(url_for("sponsor.eligibility", done=1))
    return render_template("sponsor/eligibility.html", sp=sp, seniorities=SENIORITIES, levels=EDUCATION_LEVELS,
                           auto=Setting.get("sponsor_auto_approve"), minimum=Setting.get("sponsor_min_score"))
