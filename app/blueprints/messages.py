"""Messagerie façon boîte de discussion : conversations à gauche, fil de bulles à droite.
Chaque message est aussi envoyé par e-mail (Brevo). Les messages automatiques
(accusés de réception, réponses groupées…) apparaissent dans la conversation
avec l'interlocuteur concerné ; les messages système sont dans « TalentConnect »."""
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import current_user, login_required
from sqlalchemy import or_, and_

from ..extensions import db
from ..models import Message, User, Application, Job
from ..i18n import t
from ..services import mailer

bp = Blueprint("messages", __name__)

SYSTEM = 0  # identifiant de la conversation « TalentConnect » (messages sans expéditeur)


def _thread_query(uid):
    me = current_user.id
    if uid == SYSTEM:
        return Message.query.filter(Message.recipient_id == me, Message.sender_id.is_(None))
    return Message.query.filter(or_(and_(Message.sender_id == me, Message.recipient_id == uid),
                                    and_(Message.sender_id == uid, Message.recipient_id == me)))


def conversations():
    """Liste des conversations, la plus récente en premier."""
    me = current_user.id
    rows = Message.query.filter(or_(Message.sender_id == me, Message.recipient_id == me)) \
        .order_by(Message.created_at.desc()).limit(1500).all()
    convs = {}
    for m in rows:
        if m.sender_id == me:
            if not m.recipient_id:
                continue  # e-mail envoyé à une adresse externe (ex. invitation de parrainage)
            other = m.recipient_id
        else:
            other = m.sender_id or SYSTEM
        c = convs.get(other)
        if c is None:
            c = convs[other] = {"uid": other, "user": m.recipient if m.sender_id == me else m.sender,
                                "last": m, "unread": 0}
        if m.recipient_id == me and not m.read_at:
            c["unread"] += 1
    return list(convs.values())


def can_write_to(user):
    if user is None or user.id == current_user.id:
        return False
    if current_user.role in ("admin", "recruiter") or user.role == "admin":
        return True
    # candidat / parrain : uniquement s'il existe déjà un échange
    return _thread_query(user.id).first() is not None


@bp.route("/")
@login_required
def inbox():
    convs = conversations()
    # Sur ordinateur, on ouvre directement la conversation la plus récente
    if convs and request.args.get("list") != "1":
        return redirect(url_for("messages.thread", uid=convs[0]["uid"], auto=1))
    return render_template("messages/chat.html", convs=convs, other=None, msgs=[], uid=None)


@bp.route("/c/<int:uid>", methods=["GET", "POST"])
@login_required
def thread(uid):
    other = None if uid == SYSTEM else db.session.get(User, uid)
    if uid != SYSTEM and other is None:
        abort(404)
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if not can_write_to(other):
            abort(403)
        if body:
            last = _thread_query(uid).order_by(Message.created_at.desc()).first()
            subject = t("Nouveau message de {name}", name=current_user.full_name)
            if last and last.subject:
                subject = last.subject if last.subject.lower().startswith("re:") else "Re: " + last.subject
            mailer.send(other, subject, body, kind="custom", sender=current_user,
                        application=last.application if last else None)
        if request.headers.get("HX-Request"):
            return _render_bubbles(uid, other)
        return redirect(url_for("messages.thread", uid=uid))
    _mark_read(uid)
    return render_template("messages/chat.html", convs=conversations(), other=other, uid=uid,
                           msgs=_thread_query(uid).order_by(Message.created_at).all(),
                           can_write=can_write_to(other), auto=request.args.get("auto"))


@bp.route("/c/<int:uid>/fil")
@login_required
def thread_partial(uid):
    other = None if uid == SYSTEM else db.session.get(User, uid)
    _mark_read(uid)
    return _render_bubbles(uid, other)


def _render_bubbles(uid, other):
    return render_template("messages/_bubbles.html", msgs=_thread_query(uid).order_by(Message.created_at).all(),
                           other=other)


def _mark_read(uid):
    changed = False
    for m in _thread_query(uid).filter(Message.recipient_id == current_user.id, Message.read_at.is_(None)).all():
        m.read_at = datetime.utcnow()
        changed = True
    if changed:
        db.session.commit()


@bp.route("/<int:mid>")
@login_required
def view(mid):
    """Ancien lien vers un message : redirige vers la conversation correspondante."""
    m = db.get_or_404(Message, mid)
    if current_user.id not in (m.sender_id, m.recipient_id) and current_user.role != "admin":
        abort(403)
    if m.sender_id == current_user.id:
        uid = m.recipient_id or SYSTEM
    else:
        uid = m.sender_id or SYSTEM
    return redirect(url_for("messages.thread", uid=uid, _anchor=f"m{m.id}"))
