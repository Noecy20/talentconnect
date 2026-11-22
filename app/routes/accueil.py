from collections import Counter

from flask import Blueprint, render_template, redirect, url_for, request, session, g, abort
from flask_login import current_user, login_required
from sqlalchemy import func

from ..extensions import db
from ..modeles import User, Job, Company, SponsorProfile, Application, CONTRACT_TYPES
from .. import CONTRACT_LABELS
from ..generateur_cv import build_page
from ..langues import available_languages
from ..services import offres_externes
from ..outils import access_required, send_stored
from .. import geographie

bp = Blueprint("main", __name__)


@bp.route("/sante")
def health():
    """Page légère pour le service de surveillance (UptimeRobot) : garde le site éveillé."""
    return "ok", 200, {"Content-Type": "text/plain"}


@bp.route("/")
def index():
    stats = dict(
        candidates=User.query.filter_by(role="candidate").count(),
        companies=Company.query.count(),
        sponsors=SponsorProfile.query.filter_by(status="approved").count(),
        jobs=Job.query.filter_by(status="open").count(),
    )
    derniers = Job.query.filter_by(status="open").order_by(Job.created_at.desc()).limit(6).all()
    return render_template("accueil/index.html", stats=stats, derniers=derniers)


# Façons de regrouper la liste des offres (menu « Regrouper par » de la recherche)
REGROUPEMENTS = {"entreprise": "Entreprise", "ville": "Ville", "contrat": "Type de contrat", "filiere": "Filière"}


@bp.route("/offres")
def offers():
    """Toutes les offres au même endroit : celles publiées sur TalentConnect,
    puis celles récupérées sur les sites d'emploi partenaires (API officielles).
    La recherche se filtre (contrat, télétravail, date) et se regroupe, à la manière d'Odoo."""
    a = request.args
    f = dict(q=a.get("q", "").strip(), ville=a.get("ville", "").strip(), source=a.get("source", "toutes"),
             contrat=a.getlist("contrat"), teletravail=a.get("teletravail") == "1",
             recentes=a.get("recentes") == "1", groupe=a.get("groupe", ""))
    if f["groupe"] not in REGROUPEMENTS:
        f["groupe"] = ""

    # 1. Offres TalentConnect
    internes = []
    if f["source"] != "externes":
        req = Job.query.filter_by(status="open").join(Company)
        if f["q"]:
            req = req.filter(db.or_(Job.title.ilike(f"%{f['q']}%"), Job.description.ilike(f"%{f['q']}%"),
                                    Company.name.ilike(f"%{f['q']}%"), Job.field.ilike(f"%{f['q']}%")))
        if f["ville"]:
            req = req.filter(Job.city.ilike(f"%{f['ville']}%"))
        if f["contrat"]:
            req = req.filter(Job.contract_type.in_(f["contrat"]))
        if f["teletravail"]:
            req = req.filter(Job.remote.is_(True))
        if f["recentes"]:
            from datetime import datetime, timedelta
            req = req.filter(Job.created_at >= datetime.utcnow() - timedelta(days=7))
        internes = req.order_by(Job.created_at.desc()).limit(90).all()

    # 2. Offres des sites partenaires (seulement sur une recherche précise)
    externes, erreurs = [], []
    if f["q"] and f["source"] != "talentconnect":
        externes, erreurs = offres_externes.search(f["q"], f["ville"])
        if f["teletravail"]:
            externes = [r for r in externes if "remote" in (r.get("city") or "").lower()
                        or "télétravail" in (r.get("city") or "").lower() or r.get("source") in ("Remotive", "Jobicy")]

    # 3. Une seule liste, pour pouvoir regrouper les deux origines ensemble
    offres = [dict(type="tc", job=j, entreprise=j.company.name, ville=j.city or "—",
                   contrat=CONTRACT_LABELS.get(j.contract_type, j.contract_type or "—"), filiere=j.field or "—")
              for j in internes]
    offres += [dict(type="ext", r=r, entreprise=r.get("company") or "—", ville=r.get("city") or "—",
                    contrat=r.get("contract") or "—", filiere="—") for r in externes]

    groupes = []
    if f["groupe"]:
        par = {}
        for o in offres:
            par.setdefault(o[f["groupe"]], []).append(o)
        groupes = sorted(par.items(), key=lambda kv: (kv[0] == "—", -len(kv[1]), kv[0].lower()))

    return render_template("accueil/offres.html", offres=offres, groupes=groupes, erreurs=erreurs, f=f,
                           nb_internes=len(internes), nb_externes=len(externes),
                           sources=offres_externes.providers(), regroupements=REGROUPEMENTS,
                           contrats=CONTRACT_TYPES)


@bp.route("/entreprise/<int:cid>/logo")
def company_logo(cid):
    """Logo envoyé par l'entreprise (affiché sur ses offres)."""
    co = db.session.get(Company, cid)
    if not co or not co.logo:
        abort(404)
    return send_stored(co.logo, "logos")


@bp.route("/langue/<code>")
def set_language(code):
    if code in available_languages():
        session["lang"] = code
        if current_user.is_authenticated:
            current_user.language = code
            db.session.commit()
    nxt = request.args.get("next") or url_for("main.index")
    if not nxt.startswith("/"):
        nxt = url_for("main.index")
    return redirect(nxt.rstrip("?"))


@bp.route("/tableau-de-bord")
@login_required
def dashboard():
    return redirect(url_for({
        "candidate": "candidate.dashboard", "recruiter": "recruiter.dashboard",
        "sponsor": "sponsor.dashboard", "admin": "admin.dashboard",
    }[current_user.role]))


@bp.route("/cv")
def cv_free():
    """CV Builder public et gratuit (comme CVFlash)."""
    if current_user.is_authenticated and current_user.role == "candidate":
        return redirect(url_for("candidate.cv_builder"))
    return render_template("accueil/cv_gratuit.html")


@bp.route("/cv/cadre")
def cv_frame():
    return build_page(None, logged_in=False)


@bp.route("/marche")
@login_required
@access_required
def market():
    """Carte et statistiques des métiers qui recrutent (par pays, ville, filière)."""
    country = request.args.get("country") or (current_user.country_code or "CI")
    jobs = Job.query.filter_by(status="open", country_code=country).all()
    by_city = Counter(j.city for j in jobs if j.city)
    by_field = Counter(j.field for j in jobs if j.field)
    skills = Counter(s for j in jobs for s in (j.skills or []))
    points = []
    for city, n in by_city.items():
        c = geographie.city_coords(country, city)
        if c:
            points.append({"city": city, "n": n, "lat": c[0], "lng": c[1]})
    world = db.session.query(Job.country_code, func.count(Job.id)).filter(Job.status == "open").group_by(Job.country_code).all()
    return render_template("accueil/marche.html", country=country, total=len(jobs),
                           by_city=by_city.most_common(10), by_field=by_field.most_common(10),
                           skills=skills.most_common(20), points=points,
                           world=sorted(world, key=lambda x: -x[1]))
