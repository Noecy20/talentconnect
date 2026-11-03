import os
from datetime import datetime

from flask import Flask, g, render_template, request
from flask_login import current_user

from config import Config
from .extensions import db, migrate, login_manager, csrf
from . import geo
from .i18n import t, get_locale, available_languages


EDU_LABELS = {"none": "Sans diplôme", "bepc": "BEPC / Brevet", "bac": "Bac", "bac2": "Bac+2 (BTS, DUT)",
              "bac3": "Bac+3 (Licence)", "bac4": "Bac+4 (Maîtrise)", "bac5": "Bac+5 (Master, Ingénieur)", "doctorate": "Doctorat"}
CONTRACT_LABELS = {"cdi": "CDI", "cdd": "CDD", "internship": "Stage", "freelance": "Freelance", "alternance": "Alternance",
                   "interim": "Intérim", "volunteer": "Bénévolat / Volontariat"}
SENIORITY_LABELS = {"employee": "Employé / Cadre", "manager": "Manager", "senior_manager": "Manager senior",
                    "director": "Directeur", "executive": "Dirigeant (DG, PDG, fondateur)"}


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .blueprints.main import bp as main_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.candidate import bp as candidate_bp
    from .blueprints.recruiter import bp as recruiter_bp
    from .blueprints.sponsor import bp as sponsor_bp
    from .blueprints.admin import bp as admin_bp
    from .blueprints.billing import bp as billing_bp
    from .blueprints.assistant import bp as assistant_bp
    from .blueprints.messages import bp as messages_bp
    from .blueprints.api import bp as api_bp
    from .blueprints.tracker import bp as tracker_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(candidate_bp, url_prefix="/candidat")
    app.register_blueprint(recruiter_bp, url_prefix="/recruteur")
    app.register_blueprint(sponsor_bp, url_prefix="/parrain")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(billing_bp, url_prefix="/abonnement")
    app.register_blueprint(assistant_bp, url_prefix="/assistant")
    app.register_blueprint(messages_bp, url_prefix="/messages")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(tracker_bp, url_prefix="/candidat/suivi")

    @app.before_request
    def _set_lang():
        g.lang = get_locale()
        if current_user.is_authenticated:
            if not current_user.last_seen or (datetime.utcnow() - current_user.last_seen).seconds > 300:
                current_user.last_seen = datetime.utcnow()
                db.session.commit()

    @app.context_processor
    def _inject():
        from .models import Message
        unread = 0
        if current_user.is_authenticated:
            unread = Message.query.filter_by(recipient_id=current_user.id, read_at=None).count()
        lang = getattr(g, "lang", "fr")
        return dict(
            t=t, lang=lang, languages=available_languages(),
            lang_dir=available_languages().get(lang, {}).get("dir", "ltr"),
            countries=lambda: geo.countries(lang),
            country_name=lambda c: geo.country_name(c, lang),
            money=lambda a, c="XOF": geo.money(a, c, lang),
            currency_for=geo.currency_for,
            unread_count=unread, now=datetime.utcnow(),
            ai_enabled=bool(app.config.get("ANTHROPIC_API_KEY")),
            edu_label=lambda c: t(EDU_LABELS.get(c, c or "")),
            contract_label=lambda c: t(CONTRACT_LABELS.get(c, c or "")),
            seniority_label=lambda c: t(SENIORITY_LABELS.get(c, c or "")),
            EDU_LABELS=EDU_LABELS, CONTRACT_LABELS=CONTRACT_LABELS, SENIORITY_LABELS=SENIORITY_LABELS,
        )

    @app.template_filter("datefr")
    def _datefmt(d, fmt="medium"):
        if not d:
            return ""
        from babel.dates import format_date, format_datetime
        try:
            if fmt == "time":
                return format_datetime(d, "d MMM, HH:mm", locale=g.lang)
            return format_date(d, format=fmt, locale=g.lang)
        except Exception:
            return d.strftime("%d/%m/%Y")

    @app.template_filter("nb")
    def _nb(v):
        try:
            return ("%.1f" % float(v)).rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return v

    @app.template_filter("js")
    def _js(value):
        """Chaîne JS sûre à l'intérieur d'un attribut HTML (Alpine, onclick…)."""
        from markupsafe import Markup
        import json
        out = json.dumps(str(value)).replace("&", "&amp;").replace('"', "&quot;").replace("<", "\\u003c").replace("'", "&#39;")
        return Markup(out)

    @app.template_filter("ago")
    def _ago(d):
        if not d:
            return ""
        s = (datetime.utcnow() - d).total_seconds()
        if s < 60:
            return t("à l'instant")
        if s < 3600:
            return t("il y a {n} min", n=int(s // 60))
        if s < 86400:
            return t("il y a {n} h", n=int(s // 3600))
        return t("il y a {n} j", n=int(s // 86400))

    @app.errorhandler(403)
    def _403(e):
        return render_template("errors.html", code=403, message=t("Accès refusé.")), 403

    @app.errorhandler(404)
    def _404(e):
        return render_template("errors.html", code=404, message=t("Page introuvable.")), 404

    from .cli import register_cli
    register_cli(app)

    return app
