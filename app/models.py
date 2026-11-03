"""Modèles de données TalentConnect (PostgreSQL via SQLAlchemy)."""
import secrets
from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db, login_manager


def now():
    return datetime.utcnow()


ROLES = ("candidate", "recruiter", "sponsor", "admin")

EDUCATION_LEVELS = [
    ("none", 0), ("bepc", 1), ("bac", 2), ("bac2", 3), ("bac3", 4),
    ("bac4", 5), ("bac5", 6), ("doctorate", 7),
]
EDU_RANK = dict(EDUCATION_LEVELS)

CONTRACT_TYPES = ["cdi", "cdd", "internship", "freelance", "alternance", "interim", "volunteer"]

APPLICATION_STATUSES = ["received", "shortlisted", "second_chance", "interview", "offer", "hired", "rejected"]


# --------------------------------------------------------------------------- Utilisateurs
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="candidate", index=True)
    first_name = db.Column(db.String(120), default="")
    last_name = db.Column(db.String(120), default="")
    phone = db.Column(db.String(50), default="")
    country_code = db.Column(db.String(2), default="CI")
    city = db.Column(db.String(120), default="")
    language = db.Column(db.String(8), default="fr")
    avatar = db.Column(db.String(255))
    is_active_account = db.Column(db.Boolean, default=True)
    # Accès payant : géré par l'admin (manuel) ou par un paiement validé
    access_granted = db.Column(db.Boolean, default=False)
    access_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now, index=True)
    last_seen = db.Column(db.DateTime, default=now)

    candidate = db.relationship("CandidateProfile", backref="user", uselist=False, cascade="all, delete-orphan")
    recruiter = db.relationship("RecruiterProfile", backref="user", uselist=False, cascade="all, delete-orphan")
    sponsor = db.relationship("SponsorProfile", backref="user", uselist=False, cascade="all, delete-orphan")
    assistant = db.relationship("Assistant", backref="owner", uselist=False, cascade="all, delete-orphan")

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def full_name(self):
        n = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return n or self.email.split("@")[0]

    @property
    def initials(self):
        parts = [p for p in [self.first_name, self.last_name] if p]
        return "".join(p[0] for p in parts).upper() or self.email[0].upper()

    @property
    def has_access(self):
        """Admin et parrains : toujours. Sinon il faut un accès accordé et non expiré."""
        if self.role in ("admin", "sponsor"):
            return True
        if not self.access_granted:
            return False
        return self.access_until is None or self.access_until >= now()

    def grant_access(self, days=None):
        self.access_granted = True
        if days:
            base = self.access_until if self.access_until and self.access_until > now() else now()
            self.access_until = base + timedelta(days=days)
        else:
            self.access_until = None

    @property
    def is_active(self):
        return bool(self.is_active_account)


@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))


# --------------------------------------------------------------------------- Candidat
class CandidateProfile(db.Model):
    __tablename__ = "candidate_profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    headline = db.Column(db.String(200), default="")
    summary = db.Column(db.Text, default="")
    field = db.Column(db.String(120), default="", index=True)          # filière
    education_level = db.Column(db.String(20), default="bac")
    years_experience = db.Column(db.Float, default=0)
    skills = db.Column(db.JSON, default=list)                          # ["Python", "Excel"]
    soft_skills = db.Column(db.JSON, default=list)
    languages = db.Column(db.JSON, default=list)                       # [{"name":"Anglais","level":"B2"}]
    desired_position = db.Column(db.String(160), default="")
    desired_contracts = db.Column(db.JSON, default=list)
    desired_cities = db.Column(db.JSON, default=list)
    open_to_international = db.Column(db.Boolean, default=False)
    salary_expectation = db.Column(db.Integer)
    linkedin = db.Column(db.String(255), default="")
    cv_data = db.Column(db.JSON)                                       # état du CV Builder (CVFlash)
    riasec = db.Column(db.JSON)                                        # résultat orientation
    visible_to_recruiters = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    @property
    def edu_rank(self):
        return EDU_RANK.get(self.education_level or "none", 0)


# --------------------------------------------------------------------------- Entreprise / recruteur
class Company(db.Model):
    __tablename__ = "companies"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    sector = db.Column(db.String(120), default="")
    size = db.Column(db.String(40), default="")
    country_code = db.Column(db.String(2), default="CI")
    city = db.Column(db.String(120), default="")
    website = db.Column(db.String(255), default="")
    description = db.Column(db.Text, default="")
    registration_number = db.Column(db.String(120), default="")  # RCCM ou équivalent
    logo = db.Column(db.String(255))
    verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now)

    recruiters = db.relationship("RecruiterProfile", backref="company")
    jobs = db.relationship("Job", backref="company", lazy="dynamic")


class RecruiterProfile(db.Model):
    __tablename__ = "recruiter_profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"))
    position = db.Column(db.String(160), default="")
    # Preuve d'appartenance à l'entreprise
    work_email = db.Column(db.String(255), default="")
    work_email_verified = db.Column(db.Boolean, default=False)
    email_code = db.Column(db.String(12))
    email_code_sent_at = db.Column(db.DateTime)
    linkedin = db.Column(db.String(255), default="")
    proof_type = db.Column(db.String(40))          # attestation|badge|contrat|mandat
    proof_file = db.Column(db.String(255))
    proof_uploaded_at = db.Column(db.DateTime)
    verification_status = db.Column(db.String(20), default="unverified")  # unverified|pending|verified|rejected
    verification_method = db.Column(db.String(30))  # email_domain|document|admin
    verification_note = db.Column(db.String(255), default="")
    verified_at = db.Column(db.DateTime)

    @property
    def is_verified(self):
        return self.verification_status == "verified"


# --------------------------------------------------------------------------- Parrainage
class SponsorProfile(db.Model):
    __tablename__ = "sponsor_profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    kind = db.Column(db.String(20), default="individual")  # individual | company
    position = db.Column(db.String(160), default="")
    organization = db.Column(db.String(200), default="")
    organization_website = db.Column(db.String(255), default="")
    professional_email = db.Column(db.String(255), default="")
    linkedin = db.Column(db.String(255), default="")
    seniority = db.Column(db.String(30), default="employee")  # employee|manager|senior_manager|director|executive
    years_experience = db.Column(db.Integer, default=0)
    education_level = db.Column(db.String(20), default="bac")
    team_size = db.Column(db.Integer, default=0)
    registration_number = db.Column(db.String(120), default="")  # entreprise parrain
    bio = db.Column(db.Text, default="")
    eligibility_score = db.Column(db.Integer, default=0)
    eligibility_breakdown = db.Column(db.JSON)
    status = db.Column(db.String(20), default="draft")  # draft|pending_review|approved|rejected
    level = db.Column(db.String(10))                     # bronze|silver|gold
    reputation = db.Column(db.Float, default=50.0)       # 0..100, évolue selon les résultats
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now)

    @property
    def is_approved(self):
        return self.status == "approved"


class SponsorshipRequest(db.Model):
    """Lien envoyé par un candidat à un manager / une entreprise."""
    __tablename__ = "sponsorship_requests"
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(24))
    invitee_name = db.Column(db.String(200), default="")
    invitee_email = db.Column(db.String(255), default="")
    relation = db.Column(db.String(200), default="")
    message = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="sent")  # sent|opened|completed|declined
    created_at = db.Column(db.DateTime, default=now)

    candidate = db.relationship("User", foreign_keys=[candidate_id])


class Sponsorship(db.Model):
    """Recommandation structurée d'un parrain validé pour un candidat."""
    __tablename__ = "sponsorships"
    id = db.Column(db.Integer, primary_key=True)
    sponsor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    request_id = db.Column(db.Integer, db.ForeignKey("sponsorship_requests.id"))
    relation = db.Column(db.String(200), default="")      # ex : "J'étais son manager direct"
    period = db.Column(db.String(120), default="")        # ex : "2021 – 2023"
    organization = db.Column(db.String(200), default="")
    skill_ratings = db.Column(db.JSON, default=dict)      # {"Excel": 5}
    soft_ratings = db.Column(db.JSON, default=dict)
    recommendation = db.Column(db.Text, default="")
    would_rehire = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(20), default="active")   # active|pending|revoked|flagged
    created_at = db.Column(db.DateTime, default=now)

    sponsor = db.relationship("User", foreign_keys=[sponsor_id])
    candidate = db.relationship("User", foreign_keys=[candidate_id])


# --------------------------------------------------------------------------- Offres & candidatures
class Job(db.Model):
    __tablename__ = "jobs"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    recruiter_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    title = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, default="")
    field = db.Column(db.String(120), default="", index=True)
    contract_type = db.Column(db.String(20), default="cdi")
    education_level = db.Column(db.String(20), default="bac")
    min_experience = db.Column(db.Float, default=0)
    skills = db.Column(db.JSON, default=list)
    soft_skills = db.Column(db.JSON, default=list)
    languages = db.Column(db.JSON, default=list)
    country_code = db.Column(db.String(2), default="CI", index=True)
    city = db.Column(db.String(120), default="", index=True)
    remote = db.Column(db.Boolean, default=False)
    salary_min = db.Column(db.Integer)
    salary_max = db.Column(db.Integer)
    currency = db.Column(db.String(3), default="XOF")
    status = db.Column(db.String(20), default="open")  # open|closed|draft
    deadline = db.Column(db.Date)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=now, index=True)

    recruiter = db.relationship("User")
    applications = db.relationship("Application", backref="job", lazy="dynamic", cascade="all, delete-orphan")


class Application(db.Model):
    __tablename__ = "applications"
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False, index=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    cover_letter = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="received", index=True)
    match_score = db.Column(db.Integer, default=0)
    call_probability = db.Column(db.Integer, default=0)
    match_breakdown = db.Column(db.JSON)
    ai_group = db.Column(db.String(20))       # interview|second_chance|rejected
    ai_reason = db.Column(db.Text)
    feedback = db.Column(db.JSON)             # retour constructif en cas de refus
    ack_sent_at = db.Column(db.DateTime)
    decided_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now, index=True)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    candidate = db.relationship("User")
    __table_args__ = (db.UniqueConstraint("job_id", "candidate_id", name="uq_app_job_candidate"),)


class TalentPool(db.Model):
    """Vivier « Seconde chance » : candidats à reproposer sur les prochaines offres."""
    __tablename__ = "talent_pool"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    source_job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"))
    note = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=now)

    candidate = db.relationship("User")
    source_job = db.relationship("Job")


# --------------------------------------------------------------------------- Messages
class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    recipient_email = db.Column(db.String(255))
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"))
    kind = db.Column(db.String(30), default="custom")  # ack|interview|second_chance|rejection|sponsorship|custom|system
    subject = db.Column(db.String(255), default="")
    body = db.Column(db.Text, default="")
    email_status = db.Column(db.String(20), default="pending")  # pending|sent|failed|skipped
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now, index=True)

    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])
    application = db.relationship("Application")


class MessageTemplate(db.Model):
    __tablename__ = "message_templates"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"))  # None = modèle global
    kind = db.Column(db.String(30), nullable=False)
    language = db.Column(db.String(8), default="fr")
    subject = db.Column(db.String(255), default="")
    body = db.Column(db.Text, default="")


# --------------------------------------------------------------------------- Paiements
class Plan(db.Model):
    __tablename__ = "plans"
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)  # candidate|recruiter
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(3), default="XOF")
    duration_days = db.Column(db.Integer, default=30)  # 0 = illimité
    features = db.Column(db.JSON, default=list)
    active = db.Column(db.Boolean, default=True)
    highlighted = db.Column(db.Boolean, default=False)


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id"))
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), default="XOF")
    method = db.Column(db.String(30), default="mobile_money")  # wave|orange_money|mtn_momo|moov|card|bank|cash|manual
    reference = db.Column(db.String(120), default="")
    note = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="pending", index=True)  # pending|confirmed|rejected
    validated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    validated_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now, index=True)

    user = db.relationship("User", foreign_keys=[user_id])
    plan = db.relationship("Plan")


# --------------------------------------------------------------------------- Assistant (RAG)
class Assistant(db.Model):
    """Chatbot personnel : chaque utilisateur le nourrit avec ses propres informations."""
    __tablename__ = "assistants"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    name = db.Column(db.String(120), default="Mon assistant")
    persona = db.Column(db.Text, default="")  # ton, consignes
    public = db.Column(db.Boolean, default=True)  # interrogeable par les recruteurs / candidats
    include_profile = db.Column(db.Boolean, default=True)
    welcome = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=now)

    documents = db.relationship("KnowledgeDoc", backref="assistant", cascade="all, delete-orphan", lazy="dynamic")


class KnowledgeDoc(db.Model):
    __tablename__ = "knowledge_docs"
    id = db.Column(db.Integer, primary_key=True)
    assistant_id = db.Column(db.Integer, db.ForeignKey("assistants.id"), nullable=False, index=True)
    title = db.Column(db.String(200), default="")
    content = db.Column(db.Text, default="")
    source = db.Column(db.String(30), default="text")  # text|faq|file|profile
    created_at = db.Column(db.DateTime, default=now)


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    id = db.Column(db.Integer, primary_key=True)
    assistant_id = db.Column(db.Integer, db.ForeignKey("assistants.id"), nullable=False, index=True)
    asker_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    question = db.Column(db.Text)
    answer = db.Column(db.Text)
    sources = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=now)

    asker = db.relationship("User")


# --------------------------------------------------------------------------- Paramètres
class Setting(db.Model):
    __tablename__ = "settings"
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.JSON)

    DEFAULTS = {
        "sponsor_auto_approve": 75,
        "sponsor_min_score": 60,
        "sponsor_max_per_year": 10,
        "triage_interview": 70,
        "triage_second_chance": 45,
        "match_weights": {"skills": 35, "field": 15, "experience": 15, "education": 10,
                          "location": 10, "soft_skills": 10, "languages": 5},
        "payment_instructions": "Wave / Orange Money / MTN MoMo : +225 00 00 00 00 00 (TalentConnect). "
                                "Indiquez la référence de la transaction ci-dessous ; l'admin valide sous 24 h.",
    }

    @classmethod
    def get(cls, key):
        row = db.session.get(cls, key)
        if row is None:
            return cls.DEFAULTS.get(key)
        return row.value

    @classmethod
    def set(cls, key, value):
        row = db.session.get(cls, key)
        if row is None:
            row = cls(key=key, value=value)
            db.session.add(row)
        else:
            row.value = value


# --------------------------------------------------------------------------- Suivi des candidatures (JAT)
TRACKER_STAGES = [
    ("identified", "Offre identifiée"), ("to_analyze", "À analyser"), ("to_apply", "À postuler"),
    ("prepared", "Candidature préparée"), ("sent", "Candidature envoyée"), ("waiting", "En attente"),
    ("interview", "Entretien"), ("test", "Test technique"), ("offer", "Offre reçue"),
    ("accepted", "Acceptée"), ("refused", "Refusée"),
]
STAGE_KEYS = [k for k, _ in TRACKER_STAGES]
SENT_STAGES = {"sent", "waiting", "interview", "test", "offer", "accepted", "refused"}
FINAL_STAGES = {"accepted", "refused"}


class MobilityProject(db.Model):
    """Projet de mobilité professionnelle / géographique (ex. Abidjan, Québec)."""
    __tablename__ = "mobility_projects"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    country_code = db.Column(db.String(2), default="CI")
    city = db.Column(db.String(120), default="")
    target_role = db.Column(db.String(160), default="")
    color = db.Column(db.String(9), default="#D86730")
    notes = db.Column(db.Text, default="")
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=now)


class CVVersion(db.Model):
    """Version personnalisée du CV (instantané du CV Builder)."""
    __tablename__ = "cv_versions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    data = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=now)


class TrackedApplication(db.Model):
    """Une opportunité suivie par le candidat, sur TalentConnect ou ailleurs (LinkedIn, Indeed, site carrière…)."""
    __tablename__ = "tracked_applications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("mobility_projects.id"), index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"))
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), unique=True)
    title = db.Column(db.String(200), nullable=False)
    company = db.Column(db.String(200), default="")
    city = db.Column(db.String(120), default="")
    country_code = db.Column(db.String(2), default="")
    salary = db.Column(db.String(120), default="")
    contract = db.Column(db.String(30), default="")
    url = db.Column(db.String(1000), default="")
    source = db.Column(db.String(60), default="")
    description = db.Column(db.Text, default="")
    stage = db.Column(db.String(20), default="identified", index=True)
    priority = db.Column(db.Integer, default=2)           # 1 haute, 2 normale, 3 basse
    applied_at = db.Column(db.Date)
    deadline = db.Column(db.Date)
    next_followup = db.Column(db.Date, index=True)
    contact_name = db.Column(db.String(160), default="")
    contact_role = db.Column(db.String(160), default="")
    contact_email = db.Column(db.String(255), default="")
    contact_phone = db.Column(db.String(60), default="")
    cv_version_id = db.Column(db.Integer, db.ForeignKey("cv_versions.id"))
    cv_file = db.Column(db.String(255))
    cover_letter = db.Column(db.Text, default="")
    notes = db.Column(db.Text, default="")
    archived = db.Column(db.Boolean, default=False)
    stage_changed_at = db.Column(db.DateTime, default=now)
    created_at = db.Column(db.DateTime, default=now, index=True)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    project = db.relationship("MobilityProject")
    job = db.relationship("Job")
    application = db.relationship("Application")
    cv_version = db.relationship("CVVersion")
    events = db.relationship("TrackerEvent", backref="tracker", cascade="all, delete-orphan",
                             order_by="TrackerEvent.at.desc()", lazy="dynamic")

    @property
    def stage_label(self):
        return dict(TRACKER_STAGES).get(self.stage, self.stage)

    @property
    def is_sent(self):
        return self.stage in SENT_STAGES

    @property
    def followup_due(self):
        from datetime import date
        return bool(self.next_followup and self.next_followup <= date.today() and self.stage not in FINAL_STAGES)


class TrackerEvent(db.Model):
    """Historique : changement d'étape, échange avec le recruteur, relance, entretien…"""
    __tablename__ = "tracker_events"
    id = db.Column(db.Integer, primary_key=True)
    tracker_id = db.Column(db.Integer, db.ForeignKey("tracked_applications.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), default="note")  # stage|note|email|call|meeting|interview|followup
    content = db.Column(db.Text, default="")
    at = db.Column(db.DateTime, default=now)
    created_at = db.Column(db.DateTime, default=now)
