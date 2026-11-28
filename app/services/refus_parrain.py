"""Une seule tentative au test d'éligibilité parrain.

Quand une personne est jugée non éligible (refus automatique ou refus de l'administrateur),
on conserve des empreintes de son identité : e-mail du compte, e-mail professionnel, profil
LinkedIn, téléphone, couple « nom + organisation » et identifiant du navigateur. Seul un
hachage SHA-256 est stocké : aucune donnée lisible n'est gardée.

Si elle recrée un compte avec un autre e-mail, il suffit qu'un seul de ces éléments soit
identique pour que la nouvelle demande soit bloquée.
"""
import hashlib
import re
import secrets
import unicodedata

from flask import request

from ..extensions import db
from ..modeles import RefusParrain

COOKIE = "tc_nav"                 # identifiant du navigateur, gardé 2 ans
DUREE_COOKIE = 2 * 365 * 24 * 3600
MESSAGERIES = {"gmail.com", "googlemail.com"}


def _hache(valeur):
    return hashlib.sha256(f"talentconnect|{valeur}".encode("utf-8")).hexdigest()


def _texte(v):
    v = unicodedata.normalize("NFKD", v or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", v).split())


def _email(e):
    """jean.kouassi+test@gmail.com et jeankouassi@gmail.com sont la même boîte."""
    e = (e or "").strip().lower()
    if "@" not in e:
        return ""
    local, domaine = e.rsplit("@", 1)
    local = local.split("+")[0]
    if domaine in MESSAGERIES:
        local, domaine = local.replace(".", ""), "gmail.com"
    return f"{local}@{domaine}" if local else ""


def _linkedin(url):
    m = re.search(r"linkedin\.com/(?:in|company|pub)/([^/?#\s]+)", (url or "").lower())
    return m.group(1).strip("/") if m else ""


def _telephone(t):
    chiffres = re.sub(r"\D", "", t or "")
    return chiffres[-8:] if len(chiffres) >= 8 else ""   # sans l'indicatif pays


def navigateur():
    """Identifiant du navigateur (cookie), créé au besoin."""
    return request.cookies.get(COOKIE) or getattr(request, "_tc_nav", None) or _nouveau_navigateur()


def _nouveau_navigateur():
    request._tc_nav = secrets.token_urlsafe(18)
    return request._tc_nav


def poser_cookie(reponse):
    """À appeler sur la réponse des pages parrain : garde l'identifiant du navigateur."""
    valeur = request.cookies.get(COOKIE) or getattr(request, "_tc_nav", None)
    if valeur and not request.cookies.get(COOKIE):
        reponse.set_cookie(COOKIE, valeur, max_age=DUREE_COOKIE, httponly=True, samesite="Lax",
                           secure=request.is_secure)
    return reponse


def empreintes(user, sp, nav=None):
    """Liste (type, empreinte) qui identifie la personne."""
    brut = []
    for e in (user.email if user else "", sp.professional_email if sp else ""):
        if _email(e):
            brut.append(("email", _email(e)))
    if sp and _linkedin(sp.linkedin):
        brut.append(("linkedin", _linkedin(sp.linkedin)))
    if user and _telephone(getattr(user, "phone", "")):
        brut.append(("telephone", _telephone(user.phone)))
    nom = _texte(f"{user.first_name} {user.last_name}") if user else ""
    org = _texte(sp.organization) if sp else ""
    if nom and org:
        brut.append(("nom_organisation", f"{nom}|{org}"))
    if nav:
        brut.append(("navigateur", nav))
    vus, out = set(), []
    for type_, v in brut:
        h = _hache(f"{type_}:{v}")
        if h not in vus:
            vus.add(h)
            out.append((type_, h))
    return out


def deja_refuse(user, sp, nav=None):
    """Vrai si l'un des éléments d'identité correspond à une personne déjà jugée non éligible."""
    hs = [h for _, h in empreintes(user, sp, nav)]
    return bool(hs) and RefusParrain.query.filter(RefusParrain.empreinte.in_(hs)).first() is not None


def memoriser(user, sp, nav=None):
    """Enregistre les empreintes d'un refus (sans doublon)."""
    for type_, h in empreintes(user, sp, nav):
        if not RefusParrain.query.filter_by(empreinte=h).first():
            db.session.add(RefusParrain(type=type_, empreinte=h, user_id=user.id if user else None))


def oublier(user):
    """L'administrateur valide finalement le dossier : on retire le blocage lié à ce compte."""
    RefusParrain.query.filter_by(user_id=user.id).delete()
