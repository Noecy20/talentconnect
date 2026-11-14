from flask import Blueprint, render_template, redirect, url_for, request, flash, session, g
from flask_login import login_user, logout_user, login_required, current_user

from ..extensions import db
from ..models import User, CandidateProfile, RecruiterProfile, SponsorProfile, Company, Assistant
from ..i18n import t

bp = Blueprint("auth", __name__)


def _safe_next(default):
    nxt = request.values.get("next")
    return nxt if nxt and nxt.startswith("/") and not nxt.startswith("//") else default


def create_user(email, password, role, first_name="", last_name="", country="CI", city="", lang="fr", company_name=""):
    u = User(email=email.lower().strip(), role=role, first_name=first_name.strip(), last_name=last_name.strip(),
             country_code=country or "CI", city=city.strip(), language=lang)
    u.set_password(password)
    db.session.add(u)
    db.session.flush()
    if role == "candidate":
        db.session.add(CandidateProfile(user_id=u.id, skills=[], soft_skills=[], languages=[]))
    elif role == "recruiter":
        co = Company(name=company_name or t("Mon entreprise"), country_code=u.country_code, city=u.city)
        db.session.add(co)
        db.session.flush()
        db.session.add(RecruiterProfile(user_id=u.id, company_id=co.id))
    elif role == "sponsor":
        db.session.add(SponsorProfile(user_id=u.id, professional_email=u.email))
    if role != "admin":
        db.session.add(Assistant(user_id=u.id, name=t("Assistant de {name}", name=u.first_name or u.email.split("@")[0])))
    return u


@bp.route("/connexion", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        u = User.query.filter_by(email=request.form.get("email", "").lower().strip()).first()
        if u and u.check_password(request.form.get("password", "")):
            if not u.is_active:
                flash(t("Ce compte est désactivé. Contactez l'administrateur."), "danger")
            else:
                login_user(u, remember=bool(request.form.get("remember")))
                session["lang"] = u.language
                flash(t("Bon retour, {name} !", name=u.first_name or u.full_name), "success")
                return redirect(_safe_next(url_for("main.dashboard")))
        else:
            flash(t("E-mail ou mot de passe incorrect."), "danger")
    return render_template("auth/login.html")


@bp.route("/inscription", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    role = request.values.get("role", "candidate")
    if role not in ("candidate", "recruiter", "sponsor"):
        role = "candidate"
    if request.method == "POST":
        email = request.form.get("email", "").lower().strip()
        pw = request.form.get("password", "")
        if User.query.filter_by(email=email).first():
            flash(t("Un compte existe déjà avec cet e-mail."), "danger")
        elif len(pw) < 8:
            flash(t("Le mot de passe doit contenir au moins 8 caractères."), "danger")
        elif request.form.get("password_confirm") is not None and request.form.get("password_confirm") != pw:
            flash(t("Les deux mots de passe ne correspondent pas."), "danger")
        elif "@" not in email:
            flash(t("Adresse e-mail invalide."), "danger")
        else:
            u = create_user(email, pw, role, request.form.get("first_name", ""), request.form.get("last_name", ""),
                            request.form.get("country_code", "CI"), request.form.get("city", ""), g.lang,
                            request.form.get("company_name", ""))
            db.session.commit()
            login_user(u)
            flash(t("Bienvenue sur TalentConnect !"), "success")
            if role == "sponsor":
                return redirect(_safe_next(url_for("sponsor.eligibility")))
            if role == "candidate":
                return redirect(_safe_next(url_for("candidate.onboarding")))
            return redirect(_safe_next(url_for("recruiter.company")))
    return render_template("auth/register.html", role=role)


@bp.route("/deconnexion")
def logout():
    logout_user()
    return redirect(url_for("main.index"))


@bp.route("/compte", methods=["GET", "POST"])
@login_required
def account():
    u = current_user
    if request.method == "POST":
        if request.form.get("action") == "password":
            if not u.check_password(request.form.get("current", "")):
                flash(t("Mot de passe actuel incorrect."), "danger")
            elif len(request.form.get("new", "")) < 8:
                flash(t("Le mot de passe doit contenir au moins 8 caractères."), "danger")
            else:
                u.set_password(request.form["new"])
                db.session.commit()
                flash(t("Mot de passe modifié."), "success")
        else:
            u.first_name = request.form.get("first_name", u.first_name)
            u.last_name = request.form.get("last_name", u.last_name)
            u.phone = request.form.get("phone", u.phone)
            u.country_code = request.form.get("country_code", u.country_code)
            u.city = request.form.get("city", u.city)
            u.language = request.form.get("language", u.language)
            session["lang"] = u.language
            db.session.commit()
            flash(t("Compte mis à jour."), "success")
        return redirect(url_for("auth.account"))
    return render_template("auth/account.html")
