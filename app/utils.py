from functools import wraps

from flask import abort, flash, redirect, url_for, request
from flask_login import current_user

from .i18n import t


def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.path))
            if current_user.role not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def access_required(fn):
    """Bloque les fonctionnalités payantes tant que l'admin n'a pas donné l'accès."""
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))
        if not current_user.has_access:
            flash(t("Cette fonctionnalité nécessite un accès actif. Choisissez une formule pour la débloquer."), "warning")
            return redirect(url_for("billing.pricing"))
        return fn(*a, **kw)
    return wrapper


def split_list(value):
    """'Python, Excel ; SQL' -> ['Python', 'Excel', 'SQL'] (sans doublons)."""
    if not value:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = value.replace(";", ",").replace("\n", ",").split(",")
    out, seen = [], set()
    for i in items:
        s = i.strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def to_int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
