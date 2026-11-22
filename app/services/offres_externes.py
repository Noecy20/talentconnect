"""Offres d'emploi externes en temps réel.

Sites ivoiriens lus directement (pages publiques de recherche, désactivables avec OFFRES_LOCALES=0) :
  - Emploi.ci : sa page de recherche (robots.txt : « search=yes », « Allow: / »).
  - Educarriere.ci : la liste des dernières offres de sa page d'accueil.

Fournisseurs gratuits, sans clé (toujours actifs, désactivables avec OFFRES_SANS_CLE=0) :
  - Remotive, Arbeitnow, Jobicy : offres en télétravail et internationales.

Fournisseurs avec clé (activés si la clé correspondante est dans .env) :
  - JSearch (RapidAPI / OpenWeb Ninja) : agrège Google for Jobs, donc des annonces
    publiées sur LinkedIn, Indeed, Glassdoor, sites carrière…   -> JSEARCH_API_KEY
  - Adzuna : France, Canada, Royaume-Uni, États-Unis…             -> ADZUNA_APP_ID + ADZUNA_APP_KEY
  - Jooble : très large couverture internationale                  -> JOOBLE_API_KEY
Vérifiez les conditions et quotas de chaque fournisseur avant la mise en production."""
import json
import time
import urllib.parse
import urllib.request

from flask import current_app

ADZUNA_COUNTRIES = {"GB", "US", "FR", "CA", "DE", "AU", "AT", "BE", "BR", "CH", "ES", "IN", "IT", "MX", "NL", "NZ",
                    "PL", "SG", "ZA"}


def providers():
    c = current_app.config
    out = []
    if str(c.get("OFFRES_LOCALES", "1")) != "0":
        out += ["Emploi.ci", "Educarriere"]
    if c.get("JSEARCH_API_KEY"):
        out.append("JSearch")
    if c.get("ADZUNA_APP_ID") and c.get("ADZUNA_APP_KEY"):
        out.append("Adzuna")
    if c.get("JOOBLE_API_KEY"):
        out.append("Jooble")
    if str(c.get("OFFRES_SANS_CLE", "1")) != "0":
        out += ["Remotive", "Arbeitnow", "Jobicy"]
    return out


# Sources qui ne publient que des offres en Côte d'Ivoire
SOURCES_LOCALES = {"Emploi.ci": "CI", "Educarriere": "CI"}
# Sources de télétravail international : utiles seulement pour une recherche précise de métier
SOURCES_DISTANTES = {"Remotive", "Arbeitnow", "Jobicy"}


def _get(url, headers=None, data=None, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "TalentConnect/1.0", **(headers or {})},
                                 data=json.dumps(data).encode() if data is not None else None,
                                 method="POST" if data is not None else "GET")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _jsearch(q, where, country, days):
    """JSearch : les offres de Google for Jobs (LinkedIn, Indeed, Glassdoor, Welcome to the Jungle,
    sites carrière…). Clé à prendre sur openwebninja.com (gratuit : 200 recherches / mois)
    ou sur RapidAPI : mettre alors JSEARCH_FOURNISSEUR=rapidapi."""
    lieu = where or (_NOMS_PAYS.get((country or "").upper(), "") if country else "")
    params = {"query": f"{q} {('à ' + lieu) if lieu else ''}".strip(), "num_pages": 1}
    if country:
        params["country"] = country.lower()
        params["language"] = "fr" if country.upper() in _PAYS_FRANCOPHONES else "en"
    if days:
        params["date_posted"] = {1: "today", 3: "3days", 7: "week", 30: "month"}.get(days, "all")
    cle = current_app.config["JSEARCH_API_KEY"]
    if str(current_app.config.get("JSEARCH_FOURNISSEUR", "")).lower() == "rapidapi":
        res = _get("https://jsearch.p.rapidapi.com/search?" + urllib.parse.urlencode(params),
                   headers={"X-RapidAPI-Key": cle, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"})
    else:
        res = _get("https://api.openwebninja.com/jsearch/search-v2?" + urllib.parse.urlencode(params),
                   headers={"x-api-key": cle})
    # Selon la version de l'API, la liste est dans data ou dans data.jobs
    data = res.get("data") or []
    if isinstance(data, dict):
        data = data.get("jobs") or data.get("data") or []
    out = []
    for j in data:
        sal = j.get("job_salary_string") or ""
        if not sal and (j.get("job_min_salary") or j.get("job_max_salary")):
            sal = f"{j.get('job_min_salary') or ''} – {j.get('job_max_salary') or ''} {j.get('job_salary_currency') or ''}".strip(" –")
        out.append({"title": j.get("job_title"), "company": j.get("employer_name") or "", "city": j.get("job_city") or j.get("job_location") or "",
                    "country_code": (j.get("job_country") or "")[:2], "url": j.get("job_apply_link") or j.get("job_google_link"),
                    "contract": (j.get("job_employment_type") or "").lower(), "salary": sal,
                    "posted": (j.get("job_posted_at_datetime_utc") or "")[:10], "logo": j.get("employer_logo") or "",
                    "source": j.get("job_publisher") or "JSearch", "description": (j.get("job_description") or "")[:1500]})
    return out


_PAYS_FRANCOPHONES = {"CI", "SN", "FR", "BE", "CH", "CM", "BJ", "TG", "BF", "ML", "NE", "GA", "CG", "CD", "GN", "MA", "TN", "DZ", "MG", "RW", "HT"}
_NOMS_PAYS = {"CI": "Côte d'Ivoire", "SN": "Sénégal", "FR": "France", "CA": "Canada", "BE": "Belgique", "CH": "Suisse",
              "CM": "Cameroun", "BJ": "Bénin", "TG": "Togo", "BF": "Burkina Faso", "ML": "Mali", "MA": "Maroc", "GA": "Gabon"}


def _adzuna(q, where, country, days):
    cc = (country or "FR").upper()
    if cc not in ADZUNA_COUNTRIES:
        return []
    params = {"app_id": current_app.config["ADZUNA_APP_ID"], "app_key": current_app.config["ADZUNA_APP_KEY"],
              "what": q, "results_per_page": 20, "content-type": "application/json"}
    if where:
        params["where"] = where
    if days:
        params["max_days_old"] = days
    res = _get(f"https://api.adzuna.com/v1/api/jobs/{cc.lower()}/search/1?" + urllib.parse.urlencode(params))
    out = []
    for j in res.get("results", []) or []:
        sal = ""
        if j.get("salary_min"):
            sal = f"{int(j['salary_min'])} – {int(j.get('salary_max') or j['salary_min'])}"
        out.append({"title": j.get("title"), "company": (j.get("company") or {}).get("display_name", ""),
                    "city": (j.get("location") or {}).get("display_name", ""), "country_code": cc,
                    "url": j.get("redirect_url"), "contract": j.get("contract_type") or "", "salary": sal,
                    "posted": (j.get("created") or "")[:10], "source": "Adzuna", "description": (j.get("description") or "")[:1500]})
    return out


def _jooble(q, where, country, days):
    res = _get(f"https://jooble.org/api/{current_app.config['JOOBLE_API_KEY']}", data={"keywords": q, "location": where or ""})
    out = []
    for j in res.get("jobs", []) or []:
        out.append({"title": j.get("title"), "company": j.get("company") or "", "city": j.get("location") or "",
                    "country_code": (country or "")[:2], "url": j.get("link"), "contract": (j.get("type") or "").lower(),
                    "salary": j.get("salary") or "", "posted": (j.get("updated") or "")[:10], "source": j.get("source") or "Jooble",
                    "description": (j.get("snippet") or "")[:1500]})
    return out


# ---------------------------------------------------------------- sites ivoiriens (pages publiques)
UA_NAVIGATEUR = "Mozilla/5.0 (compatible; TalentConnect/1.0; +https://talentconnect-eu.onrender.com)"


def _page(url, timeout=8):
    """Télécharge une page HTML publique et renvoie un objet BeautifulSoup."""
    from bs4 import BeautifulSoup
    req = urllib.request.Request(url, headers={"User-Agent": UA_NAVIGATEUR, "Accept-Language": "fr-FR,fr;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return BeautifulSoup(r.read().decode("utf-8", "replace"), "html.parser")


def _norm(texte):
    """Minuscules sans accents, pour comparer des mots (« Comptabilité » ~ « comptabilite »)."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (texte or "").lower()) if unicodedata.category(c) != "Mn")


def _mots(q):
    """Mots utiles d'une recherche (on ignore les petits mots et la recherche par défaut)."""
    if _norm(q) == _norm(current_app.config.get("OFFRES_RECHERCHE_DEFAUT", "emploi")):
        return []
    vides = {"de", "du", "des", "la", "le", "les", "en", "et", "a", "au", "un", "une", "pour"}
    return [m for m in _norm(q).replace("/", " ").replace("-", " ").split() if len(m) > 1 and m not in vides]


def _correspond(texte, mots):
    """Vrai si chaque mot (ou son début : « comptab ») apparaît dans le texte."""
    t = _norm(texte)
    return all(m in t or (len(m) > 5 and m[:5] in t) for m in mots)


def _hors_ci(country):
    return bool(country) and country.upper() != "CI"


def _emploi_ci(q, where, country, days):
    if _hors_ci(country):
        return []
    mots = _mots(q)
    base = "https://www.emploi.ci/recherche-jobs-cote-ivoire"
    if mots:
        base += "/" + urllib.parse.quote(" ".join(mots))
    soupe = _page(base)
    out = []
    for carte in soupe.select(".card-job"):
        lien = carte.select_one("h3 a")
        if not lien:
            continue
        infos = {}
        for li in carte.select("li"):
            txt = " ".join(li.get_text(" ", strip=True).split())
            if ":" in txt:
                k, v = txt.split(":", 1)
                infos[_norm(k).strip()] = v.strip()
        date = carte.select_one("time")
        jour = (date.get_text(strip=True) if date else "").split(".")
        posted = f"{jour[2]}-{jour[1]}-{jour[0]}" if len(jour) == 3 else ""
        img = carte.select_one("picture img") or carte.select_one("img")
        logo = (img.get("data-src") or img.get("src") or "") if img else ""
        entreprise = carte.select_one(".card-job-company")
        url = carte.get("data-href") or urllib.parse.urljoin("https://www.emploi.ci", lien.get("href", ""))
        out.append({"title": (lien.get("title") or lien.get_text(strip=True)).strip(),
                    "company": entreprise.get_text(strip=True) if entreprise else "",
                    "city": infos.get("region de", "Côte d'Ivoire"), "country_code": "CI", "url": url,
                    "contract": infos.get("contrat propose", ""), "salary": "", "posted": posted,
                    "logo": logo if logo.startswith("http") and "default-logo" not in logo else "", "source": "Emploi.ci",
                    "description": " · ".join(v for k, v in infos.items() if k.startswith(("competences", "niveau")))[:1500]})
    return _filtre_ville(out, where)


def _educarriere(q, where, country, days):
    if _hors_ci(country):
        return []
    import re

    def date(texte, mot):
        m = re.search(mot + r"[^0-9]*(\d{2})/(\d{2})/(\d{4})", texte)
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""

    soupe = _page("https://emploi.educarriere.ci/")
    mots = _mots(q)
    brutes = []
    # 1. Les cartes complètes (logo, entreprise, type, date de publication)
    for carte in soupe.select(".ej-card"):
        lien = carte.select_one("a.ej-poste")
        if not lien:
            continue
        texte = carte.get_text(" ", strip=True)
        img = carte.select_one("img.ej-logo")
        societe = carte.select_one(".ej-societe")
        tag = carte.select_one(".ej-tag")
        brutes.append({"url": lien.get("href", ""), "title": lien.get_text(strip=True),
                       "company": societe.get_text(" ", strip=True) if societe else (img.get("alt", "") if img else ""),
                       "logo": img.get("src", "") if img else "", "contract": tag.get_text(strip=True) if tag else "",
                       "posted": date(texte, "Publi"), "deadline": date(texte, "Expire")})
    # 2. Les autres listes de la page (titre, logo dont l'attribut alt est le nom de l'entreprise, date limite)
    for a in soupe.select('a[href*="/offre-"]'):
        morceaux = a.get_text("|", strip=True).split("|")
        if len(morceaux) < 2:
            continue
        img = a.select_one("img")
        brutes.append({"url": a.get("href", ""), "title": morceaux[0],
                       "company": (img.get("alt") if img else "") or morceaux[1], "logo": "", "contract": "",
                       "posted": "", "deadline": date(a.get_text(" "), "Limite")})
    out, vus = [], set()
    for o in brutes:
        url = urllib.parse.urljoin("https://emploi.educarriere.ci/", o["url"])
        if url in vus or not o["title"] or (mots and not _correspond(f"{o['title']} {o['company']}", mots)):
            continue
        vus.add(url)
        if o["company"].lower().startswith(("limite", "expire")):
            o["company"] = ""
        d = o.pop("deadline")
        out.append({**o, "url": url, "city": "Côte d'Ivoire", "country_code": "CI", "salary": "",
                    "logo": o["logo"] if o["logo"].startswith("http") and "icone_fcbk" not in o["logo"] else "",
                    "contract": "" if o["contract"].lower() == "emploi" else o["contract"],
                    "source": "Educarriere", "description": f"Date limite : {d}" if d else ""})
    # Educarriere n'indique pas la ville : la grande majorité des offres sont à Abidjan
    if where and "abidjan" not in _norm(where):
        out = [o for o in out if _norm(where) in _norm(o["title"])]
    return out


def _filtre_ville(offres, where):
    if not where:
        return offres
    v = _norm(where)
    return [o for o in offres if v in _norm(f"{o['city']} {o['title']}")]


# ---------------------------------------------------------------- sources sans clé
def _remotive(q, where, country, days):
    res = _get("https://remotive.com/api/remote-jobs?" + urllib.parse.urlencode({"search": q, "limit": 30}))
    return [{"title": j.get("title"), "company": j.get("company_name") or "",
             "city": j.get("candidate_required_location") or "Télétravail", "country_code": "",
             "url": j.get("url"), "contract": (j.get("job_type") or "").replace("_", " "),
             "salary": j.get("salary") or "", "posted": (j.get("publication_date") or "")[:10],
             "source": "Remotive", "logo": j.get("company_logo") or "", "description": _sans_html(j.get("description"))}
            for j in res.get("jobs", []) or []]


def _arbeitnow(q, where, country, days):
    # Pas de recherche côté API : on filtre nous-mêmes la première page
    res = _get("https://www.arbeitnow.com/api/job-board-api")
    mots = q.lower().split()
    out = []
    for j in res.get("data", []) or []:
        texte = f"{j.get('title', '')} {' '.join(j.get('tags') or [])}".lower()
        if mots and not all(m in texte for m in mots):
            continue
        posted = time.strftime("%Y-%m-%d", time.gmtime(j["created_at"])) if j.get("created_at") else ""
        out.append({"title": j.get("title"), "company": j.get("company_name") or "", "city": j.get("location") or "",
                    "country_code": "", "url": j.get("url"), "contract": ", ".join(j.get("job_types") or []),
                    "salary": "", "posted": posted, "source": "Arbeitnow", "description": _sans_html(j.get("description"))})
    return out


def _jobicy(q, where, country, days):
    params = {"count": 30}
    if q:
        params["tag"] = q
    res = _get("https://jobicy.com/api/v2/remote-jobs?" + urllib.parse.urlencode(params))
    out = []
    for j in res.get("jobs", []) or []:
        sal = ""
        if j.get("annualSalaryMin"):
            sal = f"{j['annualSalaryMin']} – {j.get('annualSalaryMax') or ''} {j.get('salaryCurrency') or ''}".strip(" –")
        out.append({"title": j.get("jobTitle"), "company": j.get("companyName") or "", "city": j.get("jobGeo") or "Télétravail",
                    "country_code": "", "url": j.get("url"), "contract": ", ".join(j.get("jobType") or []),
                    "salary": sal, "posted": (j.get("pubDate") or "")[:10], "source": "Jobicy", "logo": j.get("companyLogo") or "",
                    "description": _sans_html(j.get("jobExcerpt"))})
    return out


def _sans_html(texte):
    """Retire les balises d'une description et la raccourcit."""
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", texte or "")).strip()[:1500]


# Cache en mémoire : la même recherche n'interroge pas les API plus d'une fois toutes les 6 heures.
# Indispensable avec les plans gratuits (JSearch : 200 recherches par mois).
_CACHE = {}
DUREE_CACHE = 6 * 3600


def search(q, where="", country="", days=0):
    """Interroge tous les fournisseurs configurés. Renvoie (offres, erreurs)."""
    q = (q or "").strip()
    if not q:
        return [], []
    cle = (q.lower().strip(), where.lower().strip(), country, days, tuple(providers()))
    if cle in _CACHE and time.time() - _CACHE[cle][0] < DUREE_CACHE:
        return _CACHE[cle][1]
    resultat = _chercher(q, where, country, days)
    if resultat[0] or not resultat[1]:   # on ne garde pas en mémoire une panne des sources
        _CACHE[cle] = (time.time(), resultat)
    return resultat


def _chercher(q, where, country, days):
    funcs = {"Emploi.ci": _emploi_ci, "Educarriere": _educarriere, "JSearch": _jsearch, "Adzuna": _adzuna,
             "Jooble": _jooble, "Remotive": _remotive, "Arbeitnow": _arbeitnow, "Jobicy": _jobicy}
    mots = _mots(q)
    # Le télétravail international n'a pas sa place pour une ville ou pour « les dernières offres »
    noms = [n for n in providers() if n not in SOURCES_DISTANTES or (mots and not where)]
    # Les sources sont interrogées en même temps : la page attend la plus lente, pas la somme
    from concurrent.futures import ThreadPoolExecutor
    app = current_app._get_current_object()

    def appel(name):
        with app.app_context():
            try:
                return name, funcs[name](q, where, country, days), None
            except Exception as exc:
                return name, [], f"{name} : {exc}"

    results, errors = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, offres, erreur in pool.map(appel, noms):
            for o in offres:
                o["_rang"] = 0 if name in SOURCES_LOCALES else (2 if name in SOURCES_DISTANTES else 1)
                # Offres d'un autre pays (JSearch peut en renvoyer malgré le filtre) : écartées
                cc = (o.get("country_code") or "").upper()
                if country and cc and cc != country.upper():
                    continue
                # Télétravail : seulement si l'intitulé parle vraiment du métier cherché
                if name in SOURCES_DISTANTES and not _correspond(o.get("title") or "", mots[:1]):
                    continue
                results.append(o)
            if erreur:
                errors.append(erreur)
    results.sort(key=lambda o: o.pop("_rang"))   # tri stable : sites ivoiriens d'abord
    seen, uniq = set(), []
    for r in results:
        key = (_norm(r.get("title")).strip(), _norm(r.get("company")).strip())
        if r.get("title") and key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq, errors
