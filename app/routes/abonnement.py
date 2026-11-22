from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import current_user, login_required

from ..extensions import db
from ..modeles import Plan, Payment, Setting, User
from ..outils import to_int
from ..langues import t
from ..services import emails

bp = Blueprint("billing", __name__)

METHODS = ["wave", "orange_money", "mtn_momo", "moov_money", "card", "bank", "paypal", "cash"]


@bp.route("/")
def pricing():
    role = request.args.get("role") or (current_user.role if current_user.is_authenticated and current_user.role in ("candidate", "recruiter") else "candidate")
    plans = Plan.query.filter_by(role=role, active=True).order_by(Plan.price).all()
    my_payments = []
    if current_user.is_authenticated:
        my_payments = Payment.query.filter_by(user_id=current_user.id).order_by(Payment.created_at.desc()).all()
    tpl = "abonnement/tarifs_espace.html" if current_user.is_authenticated else "abonnement/tarifs.html"
    return render_template(tpl, plans=plans, role=role, my_payments=my_payments,
                           instructions=Setting.get("payment_instructions"), methods=METHODS)


@bp.route("/payer/<int:plan_id>", methods=["POST"])
@login_required
def pay(plan_id):
    plan = db.get_or_404(Plan, plan_id)
    ref = request.form.get("reference", "").strip()
    if not ref:
        flash(t("Indiquez la référence de votre transaction."), "danger")
        return redirect(url_for("billing.pricing"))
    p = Payment(user_id=current_user.id, plan_id=plan.id, amount=plan.price, currency=plan.currency,
                method=request.form.get("method", "wave"), reference=ref, note=request.form.get("note", ""))
    db.session.add(p)
    db.session.commit()
    for admin in User.query.filter_by(role="admin").all():
        emails.send(admin, t("Nouveau paiement à valider"),
                    t("{name} ({email}) déclare un paiement de {amount} {cur} pour « {plan} ». Réf : {ref}.",
                      name=current_user.full_name, email=current_user.email, amount=plan.price, cur=plan.currency,
                      plan=plan.name, ref=ref), kind="system", sender=current_user)
    flash(t("Merci ! Votre paiement est en cours de vérification. Votre accès sera activé dès validation."), "success")
    return redirect(url_for("billing.pricing"))
