from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import Message
from ..i18n import t
from ..services import mailer

bp = Blueprint("messages", __name__)


@bp.route("/")
@login_required
def inbox():
    box = request.args.get("box", "in")
    q = Message.query
    if box == "out":
        q = q.filter_by(sender_id=current_user.id)
    else:
        q = q.filter_by(recipient_id=current_user.id)
    if request.args.get("app"):
        q = q.filter_by(application_id=request.args.get("app", type=int))
    kind = request.args.get("kind", "")
    if kind:
        q = q.filter_by(kind=kind)
    msgs = q.order_by(Message.created_at.desc()).limit(200).all()
    return render_template("messages/inbox.html", msgs=msgs, box=box, kind=kind)


@bp.route("/<int:mid>", methods=["GET", "POST"])
@login_required
def view(mid):
    m = db.get_or_404(Message, mid)
    if current_user.id not in (m.sender_id, m.recipient_id) and current_user.role != "admin":
        abort(403)
    if m.recipient_id == current_user.id and not m.read_at:
        m.read_at = datetime.utcnow()
        db.session.commit()
    if request.method == "POST":
        other = m.sender if m.recipient_id == current_user.id else m.recipient
        if not other:
            abort(400)
        body = request.form.get("body", "").strip()
        if body:
            subj = m.subject if m.subject.lower().startswith("re:") else "Re: " + m.subject
            mailer.send(other, subj, body, kind="custom", sender=current_user, application=m.application)
            flash(t("Réponse envoyée."), "success")
        return redirect(url_for("messages.inbox", box="out"))
    return render_template("messages/view.html", m=m)
