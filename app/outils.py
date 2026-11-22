import mimetypes
import os
from functools import wraps

from flask import abort, flash, redirect, url_for, request, Response, send_from_directory, current_app
from flask_login import current_user

from .langues import t


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


def save_upload(storage, owner_id, filename):
    """Enregistre un fichier envoyé dans la base et renvoie sa référence « db:<id> »."""
    from .extensions import db
    from .modeles import StoredFile
    data = storage.read()
    mt = storage.mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    sf = StoredFile(owner_id=owner_id, filename=filename, mimetype=mt, size=len(data), data=data)
    db.session.add(sf)
    db.session.flush()
    return f"db:{sf.id}"


def send_stored(ref, subfolder, as_attachment=False):
    """Renvoie un fichier stocké en base (« db:<id> ») ou, pour les anciens fichiers, sur le disque."""
    if ref and ref.startswith("db:"):
        from .extensions import db
        from .modeles import StoredFile
        sf = db.session.get(StoredFile, int(ref[3:]))
        if not sf:
            abort(404)
        disp = "attachment" if as_attachment else "inline"
        return Response(sf.data, mimetype=sf.mimetype,
                        headers={"Content-Disposition": f'{disp}; filename="{sf.filename}"'})
    return send_from_directory(os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder), ref, as_attachment=as_attachment)
