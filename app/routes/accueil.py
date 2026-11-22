from collections import Counter

from flask import Blueprint, render_template, redirect, url_for, request, session, g, abort, current_app
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


# Chiffres de la page d'accueil, recalculés au plus toutes les 5 minutes :
# c'est la page la plus visitée, inutile d'interroger la base à chaque visite.
_ACCUEIL = {"quand": 0, "stats": None, "ids": []}


@bp.route("/")
def index():
    import time
    if time.time() - _ACCUEIL["quand"] > 300 or _ACCUEIL["stats"] is None:
        _ACCUEIL.update(quand=time.time(), stats=_chiffres_accueil())
    # Les dernières offres sont chargées à part (offers_preview), pour afficher la page sans attendre les API
    return render_template("accueil/index.html", stats=_ACCUEIL["stats"],
                           nb_sources=len(offres_externes.providers()))


def _chiffres_accueil():
    return dict(
        candidates=User.query.filter_by(role="candidate").count(),
        companies=Company.query.count(),
        sponsors=SponsorProfile.query.filter_by(status="approved").count(),
        jobs=Job.query.filter_by(status="open").count(),
    )


# Façons de regrouper la liste des offres (menu « Regrouper par » de la recherche)
REGROUPEMENTS = {"entreprise": "Entreprise", "ville": "Ville", "contrat": "Type de contrat", "filiere": "Filière"}


# Pays proposés dans la recherche (« Partout » = toutes les sources, sans filtre de pays)
PAYS_RECHERCHE = ["CI", "SN", "CM", "BF", "ML", "BJ", "TG", "GN", "GA", "MA", "FR", "BE", "CA", "CH"]


def recherche_offres(args, candidat=None):
    """Recherche commune à la page publique « Offres d'emploi » et à l'espace candidat :
    offres TalentConnect + offres des autres sites, filtres et regroupements façon Odoo.
    Avec `candidat`, chaque offre reçoit son score de compatibilité et la liste est triée par score."""
    a = args
    defaut_pays = (candidat.country_code if candidat and candidat.country_code else None) \
        or current_app.config.get("DEFAULT_COUNTRY", "CI")
    f = dict(q=a.get("q", "").strip(), ville=a.get("ville", "").strip(), source=a.get("source", "toutes"),
             contrat=a.getlist("contrat"), teletravail=a.get("teletravail") == "1",
             recentes=a.get("recentes") == "1", groupe=a.get("groupe", ""),
             pays=a.get("pays", defaut_pays).upper() if a.get("pays", defaut_pays) != "monde" else "monde",
             tri=a.get("tri", "score" if candidat else "recent"))
    if f["groupe"] not in REGROUPEMENTS:
        f["groupe"] = ""
    pays = "" if f["pays"] == "monde" else f["pays"]

    # 1. Offres TalentConnect
    internes = []
    if f["source"] != "externes":
        req = Job.query.filter_by(status="open").join(Company)
        if f["q"]:
            req = req.filter(db.or_(Job.title.ilike(f"%{f['q']}%"), Job.description.ilike(f"%{f['q']}%"),
                                    Company.name.ilike(f"%{f['q']}%"), Job.field.ilike(f"%{f['q']}%")))
        if f["ville"]:
            req = req.filter(Job.city.ilike(f"%{f['ville']}%"))
        if pays:
            req = req.filter(db.or_(Job.country_code == pays, Job.remote.is_(True)))
        if f["contrat"]:
            req = req.filter(Job.contract_type.in_(f["contrat"]))
        if f["teletravail"]:
            req = req.filter(Job.remote.is_(True))
        if f["recentes"]:
            from datetime import datetime, timedelta
            req = req.filter(Job.created_at >= datetime.utcnow() - timedelta(days=7))
        from sqlalchemy.orm import contains_eager
        internes = req.options(contains_eager(Job.company)).order_by(Job.created_at.desc()).limit(150).all()

    # 2. Offres des autres sites. Sans mot-clé, on montre les dernières offres du pays
    #    (recherche générale « emploi », gardée en mémoire pour ménager les quotas des API).
    externes, erreurs = [], []
    if f["source"] != "talentconnect":
        mot = f["q"] or current_app.config.get("OFFRES_RECHERCHE_DEFAUT", "emploi")
        externes, erreurs = offres_externes.search(mot, f["ville"], pays)
        externes = [dict(r) for r in externes]   # copies : on y ajoute le score sans toucher au cache
        if f["teletravail"]:
            externes = [r for r in externes if "remote" in (r.get("city") or "").lower()
                        or "télétravail" in (r.get("city") or "").lower() or r.get("source") in ("Remotive", "Jobicy")]
        if f["recentes"]:
            from datetime import date, timedelta
            limite = (date.today() - timedelta(days=7)).isoformat()
            externes = [r for r in externes if not r.get("posted") or r["posted"] >= limite]

    # 3. Une seule liste, pour pouvoir trier et regrouper les deux origines ensemble
    offres = [dict(type="tc", job=j, entreprise=j.company.name, ville=j.city or "—",
                   contrat=CONTRACT_LABELS.get(j.contract_type, j.contract_type or "—"), filiere=j.field or "—",
                   date=j.created_at.date().isoformat() if j.created_at else "")
              for j in internes]
    offres += [dict(type="ext", r=r, entreprise=r.get("company") or "—", ville=r.get("city") or "—",
                    contrat=r.get("contract") or "—", filiere="—", date=r.get("posted") or "") for r in externes]

    if candidat is not None:
        from ..ia import scores
        for o in offres:
            if o["type"] == "tc":
                o["score"], _ = scores.match(candidat, o["job"])
                o["prob"] = scores.call_probability(candidat, o["job"], o["score"])
            else:
                o["score"], o["r"]["retrouvees"] = scores.match_externe(candidat, o["r"])
                o["r"]["score"] = o["score"]
        if f["tri"] == "score":
            offres.sort(key=lambda o: -o["score"])
    if f["tri"] == "recent" and (candidat is not None or f["q"]):
        offres.sort(key=lambda o: o["date"] or "", reverse=True)

    groupes = []
    if f["groupe"]:
        par = {}
        for o in offres:
            par.setdefault(o[f["groupe"]], []).append(o)
        groupes = sorted(par.items(), key=lambda kv: (kv[0] == "—", -len(kv[1]), kv[0].lower()))

    return dict(offres=offres, groupes=groupes, erreurs=erreurs, f=f,
                nb_internes=len(internes), nb_externes=len(externes),
                sources=offres_externes.providers(), regroupements=REGROUPEMENTS,
                contrats=CONTRACT_TYPES, pays_recherche=PAYS_RECHERCHE)


@bp.route("/offres")
def offers():
    """Toutes les offres au même endroit. Un candidat connecté retrouve la même recherche
    dans son espace, avec son score de compatibilité (candidate.jobs)."""
    if current_user.is_authenticated and current_user.role == "candidate" and current_user.has_access:
        return redirect(url_for("candidate.jobs", **request.args.to_dict(flat=False)))
    return render_template("accueil/offres.html", point="main.offers", **recherche_offres(request.args))


@bp.route("/offres/apercu")
def offers_preview():
    """Quelques offres pour la page d'accueil, chargées après l'affichage de la page :
    celles de TalentConnect d'abord, complétées par les dernières offres du web."""
    from sqlalchemy.orm import joinedload
    internes = (Job.query.options(joinedload(Job.company)).filter_by(status="open")
                .order_by(Job.created_at.desc()).limit(6).all())
    externes = []
    if len(internes) < 6:
        externes, _ = offres_externes.search(current_app.config.get("OFFRES_RECHERCHE_DEFAUT", "emploi"), "",
                                             current_app.config.get("DEFAULT_COUNTRY", "CI"))
    offres = [dict(type="tc", job=j) for j in internes] + [dict(type="ext", r=r) for r in externes]
    return render_template("accueil/_apercu_offres.html", offres=offres[:6])


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
    if current_user.is_authenticated and current_user.role == "candidate" and current_user.has_access:
        return redirect(url_for("candidate.cv_builder"))
    return render_template("accueil/cv_gratuit.html")


@bp.route("/cv/cadre")
def cv_frame():
    return build_page(None, logged_in=False)


@bp.route("/marche")
@login_required
@access_required
def market():
    """Carte et statistiques des métiers qui recrutent : offres TalentConnect et offres des autres sites."""
    from ..services import marche
    country = (request.args.get("country") or current_user.country_code or "CI").upper()
    return render_template("accueil/marche.html", country=country, m=marche.analyse(country),
                           pays_recherche=PAYS_RECHERCHE)


# --------------------------------------------------------------------------- test de personnalité
@bp.route("/test-personnalite", methods=["GET", "POST"])
def personality_test():
    """Test de personnalité (Ennéagramme) : ouvert à tous, sans inscription.
    Le résultat est gardé dans la session ; pour un candidat, il est aussi enregistré sur son profil."""
    from flask import flash, jsonify
    from ..ia import personnalite as P
    from ..langues import t
    if request.method == "POST":
        reponses = P.reponses_valides(request.form)
        if reponses is None:
            flash(t("Vous devez répondre à toutes les questions pour pouvoir continuer."), "warning")
            return redirect(url_for("main.personality_test"))
        resultat = P.calculer(reponses, request.form.get("genre", "F"))
        session["personnalite"] = {"genre": resultat["genre"], "reponses": resultat["reponses"]}
        if current_user.is_authenticated and current_user.role == "candidate" and current_user.candidate:
            current_user.candidate.personnalite = resultat
            db.session.commit()
        return redirect(url_for("main.personality_result"))
    questions = [{"code": c, "H": P.accorder(txt, "H"), "F": P.accorder(txt, "F")} for c, _, txt in P.ordre()]
    return render_template("personnalite/test.html", questions=questions, par_page=P.PAR_PAGE,
                           echelle=P.ECHELLE, deja=_resultat_personnalite() is not None)


def _resultat_personnalite():
    from ..ia import personnalite as P
    if current_user.is_authenticated and current_user.role == "candidate" and current_user.candidate \
            and current_user.candidate.personnalite:
        return current_user.candidate.personnalite
    s = session.get("personnalite")
    if s and s.get("reponses"):
        return P.calculer(s["reponses"], s.get("genre", "F"))
    return None


@bp.route("/test-personnalite/resultat")
def personality_result():
    from ..ia import personnalite as P
    res = _resultat_personnalite()
    if res is None:
        return redirect(url_for("main.personality_test"))
    if request.args.get("format") == "json":
        from flask import jsonify
        return jsonify({k: res[k] for k in ("genre", "reponses", "scores_pct", "type_dominant", "aile", "code",
                                            "profil_nuance", "fiable")})
    return render_template("personnalite/resultat.html", r=P.rapport(res), types=P.TYPES)
