from flask import Blueprint, render_template, redirect, url_for, request, flash, session, g, current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_login import login_user, logout_user, login_required, current_user

from ..extensions import db
from ..modeles import User, CandidateProfile, RecruiterProfile, SponsorProfile, Company, Assistant
from ..langues import t
from ..services.emails import send

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
    return render_template("authentification/connexion.html")


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
    return render_template("authentification/inscription.html", role=role)


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
    return render_template("authentification/compte.html")


# --------------------------------------------------------------------------- mot de passe oublié
# Le lien envoyé par e-mail contient un jeton signé avec la clé secrète de l'app.
# On y glisse la fin du hachage du mot de passe actuel : dès que le mot de passe
# change, l'ancien lien ne marche plus (il ne sert donc qu'une fois).
DUREE_LIEN = 3600  # une heure


def _signeur():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="mot-de-passe-oublie")


def _jeton_pour(u):
    return _signeur().dumps({"id": u.id, "h": (u.password_hash or "")[-12:]})


def _utilisateur_du_jeton(jeton):
    try:
        data = _signeur().loads(jeton, max_age=DUREE_LIEN)
    except (BadSignature, SignatureExpired):
        return None
    u = db.session.get(User, data.get("id"))
    if not u or (u.password_hash or "")[-12:] != data.get("h"):
        return None
    return u


@bp.route("/mot-de-passe-oublie", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").lower().strip()
        u = User.query.filter_by(email=email).first()
        if u and u.is_active:
            lien = url_for("auth.reset_password", jeton=_jeton_pour(u), _external=True)
            send(u, t("Réinitialiser votre mot de passe"),
                 t("Bonjour {name},", name=u.first_name or "") + "\n\n"
                 + t("Vous avez demandé à changer votre mot de passe TalentConnect. Ouvrez ce lien pour en choisir un nouveau (valable une heure) :") + "\n\n"
                 + lien + "\n\n"
                 + t("Si vous n'êtes pas à l'origine de cette demande, ignorez simplement cet e-mail."),
                 kind="reset")
            # En local, sans serveur mail, on affiche le lien pour pouvoir tester
            if current_app.debug:
                flash(lien, "info")
        else:
            current_app.logger.warning("Mot de passe oublié : aucun compte actif pour l'adresse saisie")
        # Même message dans tous les cas : on ne révèle pas si l'adresse existe
        flash(t("Si un compte existe avec cette adresse, un lien vient de vous être envoyé."), "success")
        return redirect(url_for("auth.forgot_password"))
    return render_template("authentification/mot_de_passe_oublie.html")


@bp.route("/reinitialiser/<jeton>", methods=["GET", "POST"])
def reset_password(jeton):
    u = _utilisateur_du_jeton(jeton)
    if not u:
        flash(t("Ce lien n'est plus valable. Faites une nouvelle demande."), "danger")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        pw = request.form.get("password", "")
        if len(pw) < 8:
            flash(t("Le mot de passe doit contenir au moins 8 caractères."), "danger")
        elif pw != request.form.get("password_confirm", ""):
            flash(t("Les deux mots de passe ne correspondent pas."), "danger")
        else:
            u.set_password(pw)
            db.session.commit()
            flash(t("Mot de passe modifié. Vous pouvez vous connecter."), "success")
            return redirect(url_for("auth.login"))
    return render_template("authentification/reinitialiser.html", jeton=jeton)
