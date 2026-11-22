"""Envoi d'e-mails via Brevo (SMTP) + historisation dans l'app.
Chaque message est enregistré dans la table `messages` (visible dans l'app),
puis envoyé par e-mail en arrière-plan. Sans identifiants SMTP, l'e-mail est
marqué « skipped » mais le message reste visible dans l'app."""
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr

from html import escape

from flask import current_app

from ..extensions import db
from ..modeles import Message, MessageTemplate, User


def _smtp_send(cfg, to, subject, text, html):
    name, addr = parseaddr(cfg["MAIL_SENDER"])
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((name, addr))
    msg["To"] = to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=20) as s:
        s.starttls()
        s.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
        s.sendmail(addr, [to], msg.as_string())


def email_html(subject, body, app_url):
    """Gabarit HTML de marque (compatible clients mail : tableaux + styles inline)."""
    paragraphs = "".join(
        f'<p style="margin:0 0 14px;line-height:1.6">{escape(p).replace(chr(10), "<br>")}</p>'
        for p in body.split("\n\n"))
    return f"""<!doctype html><html><body style="margin:0;background:#FAF1E3;font-family:Arial,Helvetica,sans-serif;color:#3B2416">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#FAF1E3;padding:28px 12px"><tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden">
<tr><td style="background:linear-gradient(120deg,#5A2C19,#D86730);background-color:#8A3F22;padding:22px 28px;color:#fff;font-size:20px;font-weight:bold">
Talent<span style="color:#FFD2B5">Connect</span></td></tr>
<tr><td style="padding:28px 28px 8px;font-size:15px"><h2 style="margin:0 0 18px;font-size:19px;color:#5A2C19">{escape(subject)}</h2>{paragraphs}</td></tr>
<tr><td style="padding:8px 28px 28px"><a href="{app_url}" style="display:inline-block;background:#D86730;color:#fff;text-decoration:none;padding:12px 20px;border-radius:10px;font-weight:bold">Ouvrir TalentConnect</a></td></tr>
<tr><td style="padding:16px 28px;background:#F6E9DA;font-size:12px;color:#8B6B57">Connectez les talents aux entreprises · Ce message est aussi disponible dans votre espace.</td></tr>
</table></td></tr></table></body></html>"""


def _worker(app, message_ids):
    with app.app_context():
        cfg = app.config
        for mid in message_ids:
            m = db.session.get(Message, mid)
            if not m:
                continue
            to = m.recipient.email if m.recipient else m.recipient_email
            if not (cfg.get("MAIL_USERNAME") and cfg.get("MAIL_PASSWORD")) or not to:
                m.email_status = "skipped"
                app.logger.info("[mail non envoyé — SMTP non configuré] %s -> %s", m.subject, to)
            else:
                try:
                    html = email_html(m.subject, m.body, cfg["APP_URL"])
                    _smtp_send(cfg, to, m.subject, m.body, html)
                    m.email_status = "sent"
                except Exception as exc:
                    m.email_status = "failed"
                    app.logger.warning("Échec e-mail %s : %s", to, exc)
            db.session.commit()


def dispatch(message_ids, sync=False):
    app = current_app._get_current_object()
    if sync or app.config.get("TESTING"):
        _worker(app, message_ids)
    else:
        threading.Thread(target=_worker, args=(app, list(message_ids)), daemon=True).start()


def send(recipient, subject, body, kind="custom", sender=None, application=None, email=None, defer=False, sync=False):
    """Crée le message dans l'app et déclenche l'e-mail. Renvoie le Message."""
    m = Message(
        sender_id=sender.id if sender else None,
        recipient_id=recipient.id if recipient else None,
        recipient_email=email or (recipient.email if recipient else None),
        application_id=application.id if application else None,
        kind=kind, subject=subject, body=body,
    )
    db.session.add(m)
    db.session.commit()
    if not defer:
        dispatch([m.id], sync=sync)
    return m


# --------------------------------------------------------------------------- modèles de messages
DEFAULT_TEMPLATES = {
    "ack": ("Nous avons bien reçu votre candidature — {job}",
            "Bonjour {candidate},\n\nMerci pour votre candidature au poste « {job} » chez {company}. "
            "Elle a bien été reçue et sera étudiée avec attention. Vous recevrez une réponse quelle que soit l'issue.\n\n"
            "Vous pouvez suivre son avancement à tout moment dans votre espace TalentConnect.\n\nCordialement,\n{recruiter}\n{company}"),
    "interview": ("Invitation à un entretien — {job}",
                  "Bonjour {candidate},\n\nVotre profil a retenu notre attention pour le poste « {job} ». "
                  "Nous souhaitons vous rencontrer en entretien.\n\n{note}\n\nMerci de nous indiquer vos disponibilités en répondant à ce message.\n\n"
                  "Cordialement,\n{recruiter}\n{company}"),
    "second_chance": ("Votre candidature — {job}",
                      "Bonjour {candidate},\n\nMerci pour votre intérêt pour le poste « {job} ». "
                      "Nous ne pouvons pas donner suite pour le moment, mais votre profil a retenu notre attention : "
                      "nous l'ajoutons à notre vivier de talents et vous recontacterons en priorité pour une prochaine opportunité.\n\n"
                      "{feedback}\n\nCordialement,\n{recruiter}\n{company}"),
    "rejected": ("Réponse à votre candidature — {job}",
                  "Bonjour {candidate},\n\nMerci pour le temps consacré à votre candidature au poste « {job} ». "
                  "Après étude, nous ne pouvons malheureusement pas y donner une suite favorable.\n\n"
                  "Pour vous aider dans vos prochaines démarches, voici un retour personnalisé :\n{feedback}\n\n"
                  "Nous vous souhaitons pleine réussite.\n\nCordialement,\n{recruiter}\n{company}"),
}


def get_template(kind, company_id=None):
    tpl = None
    if company_id:
        tpl = MessageTemplate.query.filter_by(kind=kind, company_id=company_id).first()
    if not tpl:
        tpl = MessageTemplate.query.filter_by(kind=kind, company_id=None).first()
    if tpl:
        return tpl.subject, tpl.body
    return DEFAULT_TEMPLATES[kind]


def render_text(text, **ctx):
    class _Safe(dict):
        def __missing__(self, k):
            return ""
    return text.format_map(_Safe(**ctx))


def format_feedback(fb):
    if not fb:
        return ""
    lines = [f"• {r}" for r in fb.get("reasons", [])]
    if fb.get("tips"):
        lines.append("\nNos conseils :")
        lines += [f"→ {tip}" for tip in fb["tips"]]
    return "\n".join(lines)
