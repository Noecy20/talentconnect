from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Assistant, KnowledgeDoc, ChatMessage, User
from ..utils import access_required
from ..i18n import t
from ..services import rag

bp = Blueprint("assistant", __name__)


def ensure_assistant(user):
    if not user.assistant:
        a = Assistant(user_id=user.id, name=t("Assistant de {name}", name=user.first_name or user.full_name))
        db.session.add(a)
        db.session.commit()
    return user.assistant


def _paid_or_sponsor():
    return current_user.role in ("sponsor", "admin") or current_user.has_access


@bp.route("/", methods=["GET", "POST"])
@login_required
def mine():
    if not _paid_or_sponsor():
        flash(t("Cette fonctionnalité nécessite un accès actif. Choisissez une formule pour la débloquer."), "warning")
        return redirect(url_for("billing.pricing"))
    a = ensure_assistant(current_user)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "settings":
            a.name = request.form.get("name", a.name).strip() or a.name
            a.persona = request.form.get("persona", "").strip()
            a.welcome = request.form.get("welcome", "").strip()
            a.public = bool(request.form.get("public"))
            a.include_profile = bool(request.form.get("include_profile"))
            flash(t("Assistant mis à jour."), "success")
        elif action == "add":
            content = request.form.get("content", "").strip()
            f = request.files.get("file")
            source = request.form.get("source", "text")
            title = request.form.get("title", "").strip()
            if f and f.filename:
                content = extract_text(f)
                source = "file"
                title = title or f.filename
            if content:
                db.session.add(KnowledgeDoc(assistant_id=a.id, title=title or t("Note"), content=content[:60000], source=source))
                flash(t("Connaissance ajoutée à votre assistant."), "success")
            else:
                flash(t("Rien à ajouter : le contenu est vide ou illisible."), "warning")
        elif action == "delete":
            d = db.session.get(KnowledgeDoc, int(request.form["doc_id"]))
            if d and d.assistant_id == a.id:
                db.session.delete(d)
        db.session.commit()
        return redirect(url_for("assistant.mine"))
    history = ChatMessage.query.filter_by(assistant_id=a.id).order_by(ChatMessage.created_at.desc()).limit(30).all()
    auto_docs = rag.profile_documents(current_user) if a.include_profile else []
    return render_template("assistant/mine.html", a=a, docs=a.documents.order_by(KnowledgeDoc.created_at.desc()).all(),
                           history=history, auto_docs=auto_docs)


def extract_text(f):
    name = f.filename.lower()
    data = f.read()
    if name.endswith(".pdf"):
        try:
            import io
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        except Exception:
            return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="ignore")


@bp.route("/discuter/<int:user_id>", methods=["GET", "POST"])
@login_required
def chat(user_id):
    owner = db.get_or_404(User, user_id)
    a = ensure_assistant(owner)
    is_owner = owner.id == current_user.id
    if not is_owner:
        if not a.public:
            abort(404)
        if not _paid_or_sponsor():
            return redirect(url_for("billing.pricing"))
    history = ChatMessage.query.filter_by(assistant_id=a.id, asker_id=current_user.id).order_by(ChatMessage.created_at).all()
    if request.method == "POST":
        q = request.form.get("question", "").strip()
        if q:
            text, sources = rag.answer(a, q, current_user, history)
            m = ChatMessage(assistant_id=a.id, asker_id=current_user.id, question=q, answer=text, sources=sources)
            db.session.add(m)
            db.session.commit()
            if request.headers.get("HX-Request"):
                return render_template("assistant/_exchange.html", m=m, a=a)
        return redirect(url_for("assistant.chat", user_id=owner.id))
    return render_template("assistant/chat.html", a=a, owner=owner, history=history, is_owner=is_owner)
