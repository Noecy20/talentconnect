from collections import Counter

from flask import Blueprint, render_template, redirect, url_for, request, session, g
from flask_login import current_user, login_required
from sqlalchemy import func

from ..extensions import db
from ..models import User, Job, Company, SponsorProfile, Application
from ..cvbuilder import build_page
from ..i18n import available_languages
from ..utils import access_required
from .. import geo

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    stats = dict(
        candidates=User.query.filter_by(role="candidate").count(),
        companies=Company.query.count(),
        sponsors=SponsorProfile.query.filter_by(status="approved").count(),
        jobs=Job.query.filter_by(status="open").count(),
    )
    return render_template("main/index.html", stats=stats)


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
        c = geo.city_coords(country, city)
        if c:
            points.append({"city": city, "n": n, "lat": c[0], "lng": c[1]})
    world = db.session.query(Job.country_code, func.count(Job.id)).filter(Job.status == "open").group_by(Job.country_code).all()
    return render_template("main/market.html", country=country, total=len(jobs),
                           by_city=by_city.most_common(10), by_field=by_field.most_common(10),
                           skills=skills.most_common(20), points=points,
                           world=sorted(world, key=lambda x: -x[1]))
