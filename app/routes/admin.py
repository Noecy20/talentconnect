from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import current_user
from sqlalchemy import func, or_

from ..extensions import db
from ..modeles import (User, Payment, Plan, SponsorProfile, Sponsorship, Company, Job, Application, Setting, Message, ROLES)
from ..outils import role_required, to_int, split_list
from ..langues import t
from ..ia import scores
from ..services import emails

bp = Blueprint("admin", __name__)


@bp.before_request
@role_required("admin")
def _guard():
    pass


@bp.route("/")
def dashboard():
    counts = {r: User.query.filter_by(role=r).count() for r in ROLES}
    paid = {r: User.query.filter_by(role=r, access_granted=True).count() for r in ("candidate", "recruiter")}
    revenue = defaultdict(int)
    for p in Payment.query.filter_by(status="confirmed").all():
        revenue[p.currency] += p.amount
    since = datetime.utcnow() - timedelta(days=29)
    days = [(since + timedelta(days=i)).date() for i in range(30)]
    signups = {r: [0] * 30 for r in ("candidate", "recruiter", "sponsor")}
    for u in User.query.filter(User.created_at >= since).all():
        if u.role in signups:
            idx = (u.created_at.date() - days[0]).days
            if 0 <= idx < 30:
                signups[u.role][idx] += 1
    countries = db.session.query(User.country_code, func.count(User.id)).group_by(User.country_code) \
        .order_by(func.count(User.id).desc()).limit(8).all()
    from ..services import donnees_demo
    return render_template("admin/tableau_de_bord.html", nb_offres_demo=len(donnees_demo.offres_demo()),
                           counts=counts, paid=paid, revenue=dict(revenue),
                           pending_payments=Payment.query.filter_by(status="pending").count(),
                           pending_sponsors=SponsorProfile.query.filter_by(status="pending_review").count(),
                           jobs=Job.query.filter_by(status="open").count(), apps=Application.query.count(),
                           sponsorships=Sponsorship.query.filter_by(status="active").count(),
                           flagged=Sponsorship.query.filter_by(status="flagged").count(),
                           days=[d.strftime("%d/%m") for d in days], signups=signups, countries=countries,
                           recent=User.query.order_by(User.created_at.desc()).limit(8).all(),
                           msgs=Message.query.count())


# --------------------------------------------------------------------------- utilisateurs & accès
@bp.route("/offres-demo/supprimer", methods=["POST"])
def delete_demo_jobs():
    """Bouton du tableau de bord : retire les offres de démonstration (suppression définitive)."""
    from ..services import donnees_demo
    if request.form.get("confirmation") != "SUPPRIMER":
        flash(t("Tapez SUPPRIMER pour confirmer."), "warning")
        return redirect(url_for("admin.dashboard"))
    n, c = donnees_demo.supprimer_offres_demo()
    flash(t("{n} offre(s) de démo et {c} candidature(s) liée(s) supprimées.", n=n, c=c), "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/utilisateurs")
def users():
    q = User.query
    role = request.args.get("role", "")
    access = request.args.get("access", "")
    s = request.args.get("q", "").strip()
    if role:
        q = q.filter_by(role=role)
    if access == "yes":
        q = q.filter_by(access_granted=True)
    elif access == "no":
        q = q.filter_by(access_granted=False)
    if s:
        q = q.filter(or_(User.email.ilike(f"%{s}%"), User.first_name.ilike(f"%{s}%"), User.last_name.ilike(f"%{s}%")))
    page = request.args.get("page", 1, type=int)
    pag = q.order_by(User.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    return render_template("admin/utilisateurs.html", pag=pag, f=dict(role=role, access=access, q=s), plans=Plan.query.filter_by(active=True).all())


@bp.route("/utilisateurs/<int:uid>/acces", methods=["POST"])
def user_access(uid):
    u = db.get_or_404(User, uid)
    action = request.form.get("action")
    if action == "grant":
        days = to_int(request.form.get("days"), 0)
        u.grant_access(days or None)
        emails.send(u, t("Votre accès TalentConnect est activé"),
                    t("Bonjour {name},\n\nVotre accès complet à TalentConnect est maintenant actif{until}. Bonne découverte !",
                      name=u.first_name, until=(" " + t("pour {d} jours", d=days)) if days else ""),
                    kind="system", sender=current_user)
        flash(t("Accès accordé à {name}.", name=u.full_name), "success")
    elif action == "revoke":
        u.access_granted = False
        u.access_until = None
        flash(t("Accès retiré à {name}.", name=u.full_name), "info")
    elif action == "toggle_active":
        if u.id == current_user.id:
            abort(400)
        u.is_active_account = not u.is_active_account
        flash(t("Compte activé.") if u.is_active_account else t("Compte désactivé."), "info")
    elif action == "role" and request.form.get("role") in ROLES:
        u.role = request.form["role"]
    db.session.commit()
    return redirect(request.referrer or url_for("admin.users"))


# --------------------------------------------------------------------------- paiements
@bp.route("/paiements", methods=["GET", "POST"])
def payments():
    if request.method == "POST":
        # Enregistrement manuel d'un paiement (espèces, virement…)
        u = User.query.filter_by(email=request.form.get("email", "").lower().strip()).first()
        plan = db.session.get(Plan, to_int(request.form.get("plan_id")))
        if not u or not plan:
            flash(t("Utilisateur ou formule introuvable."), "danger")
        else:
            p = Payment(user_id=u.id, plan_id=plan.id, amount=to_int(request.form.get("amount"), plan.price),
                        currency=plan.currency, method=request.form.get("method", "cash"),
                        reference=request.form.get("reference", ""), status="pending")
            db.session.add(p)
            db.session.commit()
            _confirm(p)
            flash(t("Paiement enregistré et accès activé."), "success")
        return redirect(url_for("admin.payments"))
    status = request.args.get("status", "pending")
    q = Payment.query
    if status != "all":
        q = q.filter_by(status=status)
    pays = q.order_by(Payment.created_at.desc()).limit(300).all()
    totals = defaultdict(int)
    for p in Payment.query.filter_by(status="confirmed").all():
        totals[(p.user.role, p.currency)] += p.amount
    return render_template("admin/paiements.html", pays=pays, status=status, totals=dict(totals),
                           plans=Plan.query.order_by(Plan.role).all())


def _confirm(p):
    p.status = "confirmed"
    p.validated_by = current_user.id
    p.validated_at = datetime.utcnow()
    days = p.plan.duration_days if p.plan else 30
    p.user.grant_access(days or None)
    db.session.commit()
    emails.send(p.user, t("Paiement confirmé — accès activé"),
                t("Bonjour {name},\n\nNous avons bien reçu votre paiement de {amount} {cur} (réf. {ref}). Votre accès est actif. Merci pour votre confiance !",
                  name=p.user.first_name, amount=p.amount, cur=p.currency, ref=p.reference or "—"),
                kind="system", sender=current_user)


@bp.route("/paiements/<int:pid>/<action>", methods=["POST"])
def payment_action(pid, action):
    p = db.get_or_404(Payment, pid)
    if action == "confirm" and p.status != "confirmed":
        _confirm(p)
        flash(t("Paiement confirmé, accès activé."), "success")
    elif action == "reject":
        p.status = "rejected"
        p.note = request.form.get("note", "")
        p.validated_by = current_user.id
        p.validated_at = datetime.utcnow()
        db.session.commit()
        emails.send(p.user, t("Paiement non validé"),
                    t("Bonjour {name},\n\nNous n'avons pas pu valider votre paiement (réf. {ref}). {note}\nRépondez à ce message si besoin.",
                      name=p.user.first_name, ref=p.reference or "—", note=p.note), kind="system", sender=current_user)
        flash(t("Paiement refusé."), "info")
    return redirect(request.referrer or url_for("admin.payments"))


# --------------------------------------------------------------------------- formules
@bp.route("/formules", methods=["GET", "POST"])
def plans():
    if request.method == "POST":
        pid = to_int(request.form.get("id"))
        plan = db.session.get(Plan, pid) if pid else Plan()
        plan.role = request.form.get("role", "candidate")
        plan.name = request.form.get("name", "").strip()
        plan.description = request.form.get("description", "").strip()
        plan.price = to_int(request.form.get("price"), 0)
        plan.currency = (request.form.get("currency") or "XOF").upper()[:3]
        plan.duration_days = to_int(request.form.get("duration_days"), 30)
        plan.features = split_list(request.form.get("features"))
        plan.active = bool(request.form.get("active"))
        plan.highlighted = bool(request.form.get("highlighted"))
        if not pid:
            db.session.add(plan)
        db.session.commit()
        flash(t("Formule enregistrée."), "success")
        return redirect(url_for("admin.plans"))
    return render_template("admin/formules.html", plans=Plan.query.order_by(Plan.role, Plan.price).all(),
                           instructions=Setting.get("payment_instructions"))


@bp.route("/formules/instructions", methods=["POST"])
def payment_instructions():
    Setting.set("payment_instructions", request.form.get("instructions", ""))
    db.session.commit()
    flash(t("Instructions de paiement mises à jour."), "success")
    return redirect(url_for("admin.plans"))


# --------------------------------------------------------------------------- parrains
@bp.route("/parrains")
def sponsors():
    status = request.args.get("status", "pending_review")
    q = SponsorProfile.query
    if status != "all":
        q = q.filter_by(status=status)
    return render_template("admin/parrains.html", sps=q.order_by(SponsorProfile.created_at.desc()).all(), status=status,
                           flagged=Sponsorship.query.filter_by(status="flagged").all())


@bp.route("/parrains/<int:sid>/<action>", methods=["POST"])
def sponsor_action(sid, action):
    sp = db.get_or_404(SponsorProfile, sid)
    if action == "approve":
        sp.status = "approved"
        sp.level = scores.sponsor_level(sp.eligibility_score or 60)
        Sponsorship.query.filter_by(sponsor_id=sp.user_id, status="pending").update({"status": "active"})
        emails.send(sp.user, t("Vous êtes parrain certifié TalentConnect"),
                    t("Bonjour {name},\n\nVotre dossier a été validé. Vos recommandations sont désormais visibles des recruteurs. Merci de votre engagement !", name=sp.user.first_name),
                    kind="system", sender=current_user)
    elif action == "reject":
        sp.status = "rejected"
    sp.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(t("Dossier mis à jour."), "success")
    return redirect(request.referrer or url_for("admin.sponsors"))


@bp.route("/parrainages/<int:sid>/<action>", methods=["POST"])
def sponsorship_action(sid, action):
    s = db.get_or_404(Sponsorship, sid)
    if action == "restore":
        s.status = "active"
        scores.update_reputation(s.sponsor_id, +10)
    elif action == "revoke":
        s.status = "revoked"
    db.session.commit()
    return redirect(request.referrer or url_for("admin.sponsors"))


# --------------------------------------------------------------------------- entreprises
@bp.route("/entreprises")
def companies():
    cos = Company.query.order_by(Company.created_at.desc()).all()
    rates = {c.id: scores.company_response_rate(c.id) for c in cos}
    return render_template("admin/entreprises.html", cos=cos, rates=rates)


@bp.route("/entreprises/<int:cid>/verifier", methods=["POST"])
def company_verify(cid):
    c = db.get_or_404(Company, cid)
    c.verified = not c.verified
    db.session.commit()
    return redirect(url_for("admin.companies"))


# --------------------------------------------------------------------------- réglages des modèles
@bp.route("/reglages", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        for k in ("sponsor_auto_approve", "sponsor_min_score", "sponsor_max_per_year", "triage_interview", "triage_second_chance"):
            Setting.set(k, to_int(request.form.get(k), Setting.DEFAULTS[k]))
        weights = {k: to_int(request.form.get(f"w_{k}"), 0) for k in Setting.DEFAULTS["match_weights"]}
        Setting.set("match_weights", weights)
        db.session.commit()
        flash(t("Réglages enregistrés. Ils s'appliquent immédiatement."), "success")
        return redirect(url_for("admin.settings"))
    keys = ("sponsor_auto_approve", "sponsor_min_score", "sponsor_max_per_year", "triage_interview", "triage_second_chance")
    return render_template("admin/reglages.html", s={k: Setting.get(k) for k in keys}, w=Setting.get("match_weights"))


# --------------------------------------------------------------------------- recruteurs (preuve d'appartenance)
@bp.route("/recruteurs")
def recruiters():
    from ..modeles import RecruiterProfile
    status = request.args.get("status", "pending")
    q = RecruiterProfile.query
    if status != "all":
        q = q.filter_by(verification_status=status)
    return render_template("admin/recruteurs.html", rps=q.all(), status=status)


@bp.route("/recruteurs/<int:rid>/<action>", methods=["POST"])
def recruiter_action(rid, action):
    from ..modeles import RecruiterProfile
    rp = db.get_or_404(RecruiterProfile, rid)
    if action == "approve":
        rp.verification_status, rp.verified_at = "verified", datetime.utcnow()
        rp.verification_method = rp.verification_method or "admin"
        emails.send(rp.user, t("Vous êtes recruteur vérifié"),
                    t("Bonjour {name},\n\nVotre appartenance à {company} est confirmée. Vous pouvez publier vos offres.",
                      name=rp.user.first_name, company=rp.company.name if rp.company else ""), kind="system", sender=current_user)
    elif action == "reject":
        rp.verification_status = "rejected"
        rp.verification_note = request.form.get("note", "")
        emails.send(rp.user, t("Vérification recruteur refusée"),
                    t("Bonjour {name},\n\nNous n'avons pas pu confirmer votre appartenance à l'entreprise. {note}",
                      name=rp.user.first_name, note=rp.verification_note), kind="system", sender=current_user)
    db.session.commit()
    flash(t("Dossier mis à jour."), "success")
    return redirect(request.referrer or url_for("admin.recruiters"))


@bp.route("/recruteurs/<int:rid>/justificatif")
def recruiter_proof(rid):
    import os
    from flask import send_from_directory, current_app
    from ..modeles import RecruiterProfile
    rp = db.get_or_404(RecruiterProfile, rid)
    if not rp.proof_file:
        abort(404)
    from ..outils import send_stored
    return send_stored(rp.proof_file, "proofs")
