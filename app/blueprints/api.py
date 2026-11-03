from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..extensions import db
from ..utils import split_list
from .. import geo

bp = Blueprint("api", __name__)


@bp.route("/cities/<code>")
def cities(code):
    return jsonify(geo.cities(code.upper()[:2]))


@bp.route("/cv", methods=["POST"])
@login_required
def save_cv():
    """Reçoit l'état du CV Builder et met à jour le profil du candidat."""
    if current_user.role != "candidate":
        return jsonify(ok=False), 403
    data = request.get_json(silent=True) or {}
    cp = current_user.candidate
    cp.cv_data = data
    sync_profile_from_cv(cp, current_user, data)
    db.session.commit()
    return jsonify(ok=True)


@bp.route("/cv/version", methods=["POST"])
@login_required
def save_cv_version():
    """Enregistre le CV actuel comme version personnalisée (ex. « CV Data — Québec »)."""
    from ..models import CVVersion
    if current_user.role != "candidate":
        return jsonify(ok=False), 403
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()[:160] or "Mon CV"
    v = CVVersion(user_id=current_user.id, name=name, data=payload.get("data") or {})
    db.session.add(v)
    db.session.commit()
    return jsonify(ok=True, id=v.id)


def sync_profile_from_cv(cp, user, data):
    prof = data.get("profile") or {}
    if prof.get("role") and prof["role"] != "Intitulé de poste":
        cp.headline = cp.headline or prof["role"]
    if data.get("summary") and not data["summary"].startswith("Présentez-vous"):
        cp.summary = cp.summary or data["summary"]
    if prof.get("phone") and "00 00" not in prof["phone"]:
        user.phone = user.phone or prof["phone"]
    if prof.get("linkedin") and "votre-profil" not in prof["linkedin"]:
        cp.linkedin = cp.linkedin or prof["linkedin"]
    placeholder = ("compétence ", "outil ", "atout ", "langue")
    skills = []
    for g in data.get("comp") or []:
        if g.get("on", True):
            skills += [s for s in g.get("items", []) if s and not s.lower().startswith(placeholder)]
    if skills:
        cp.skills = split_list((cp.skills or []) + skills)
    soft = [s for s in (data.get("soft") or []) if s and not s.lower().startswith(placeholder)]
    if soft:
        cp.soft_skills = split_list((cp.soft_skills or []) + soft)
    langs = [l for l in (data.get("lang") or []) if l.get("name") and l["name"].lower() != "langue"]
    if langs and not cp.languages:
        cp.languages = [{"name": l["name"], "level": l.get("level", "")} for l in langs]
