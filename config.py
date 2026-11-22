import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _db_url():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        # Fallback pratique pour un premier lancement sans Postgres
        return "sqlite:///" + os.path.join(BASE_DIR, "instance", "talentconnect.db")
    # Render/Heroku fournissent parfois "postgres://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)  # pilote installé : psycopg2-binary
    return url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-moi-en-production")
    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 Mo par upload
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "instance", "uploads")
    WTF_CSRF_TIME_LIMIT = None

    APP_NAME = "TalentConnect"
    APP_URL = os.getenv("APP_URL", "http://localhost:5000")
    DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "fr")
    DEFAULT_COUNTRY = os.getenv("DEFAULT_COUNTRY", "CI")

    # E-mails (Brevo SMTP : smtp-relay.brevo.com:587)
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp-relay.brevo.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_SENDER = os.getenv("MAIL_SENDER", "TalentConnect <no-reply@talentconnect.app>")
    # Clé API Brevo (xkeysib-…) : envoi par HTTPS, nécessaire sur Render gratuit (ports SMTP bloqués)
    BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")

    # IA générative (optionnelle) : sans clé, l'app utilise ses modèles internes
    # IA générative : OpenRouter d'abord (modèles gratuits, bascule automatique), sinon Claude
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODELES = os.getenv("OPENROUTER_MODELES", "")   # facultatif : modèles préférés, séparés par des virgules
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-5")

    # Offres externes en temps réel via API officielles (facultatif)
    JSEARCH_API_KEY = os.getenv("JSEARCH_API_KEY", "")
    JSEARCH_FOURNISSEUR = os.getenv("JSEARCH_FOURNISSEUR", "openwebninja")  # ou « rapidapi »
    OFFRES_SANS_CLE = os.getenv("OFFRES_SANS_CLE", "1")  # Remotive, Arbeitnow, Jobicy
    ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
    JOOBLE_API_KEY = os.getenv("JOOBLE_API_KEY", "")

    # Compte admin créé au premier lancement
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@talentconnect.app")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin123!")
