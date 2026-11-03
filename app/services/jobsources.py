"""Offres d'emploi externes en temps réel, via des API officielles (pas de scraping).

Fournisseurs (activés si la clé correspondante est dans .env) :
  - JSearch (RapidAPI / OpenWeb Ninja) : agrège Google for Jobs, donc des annonces
    publiées sur LinkedIn, Indeed, Glassdoor, sites carrière…   -> JSEARCH_API_KEY
  - Adzuna : France, Canada, Royaume-Uni, États-Unis…             -> ADZUNA_APP_ID + ADZUNA_APP_KEY
  - Jooble : très large couverture internationale                  -> JOOBLE_API_KEY
Vérifiez les conditions et quotas de chaque fournisseur avant la mise en production."""
import json
import urllib.parse
import urllib.request

from flask import current_app

ADZUNA_COUNTRIES = {"GB", "US", "FR", "CA", "DE", "AU", "AT", "BE", "BR", "CH", "ES", "IN", "IT", "MX", "NL", "NZ",
                    "PL", "SG", "ZA"}


def providers():
    c = current_app.config
    out = []
    if c.get("JSEARCH_API_KEY"):
        out.append("JSearch")
    if c.get("ADZUNA_APP_ID") and c.get("ADZUNA_APP_KEY"):
        out.append("Adzuna")
    if c.get("JOOBLE_API_KEY"):
        out.append("Jooble")
    return out


def _get(url, headers=None, data=None, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "TalentConnect/1.0", **(headers or {})},
                                 data=json.dumps(data).encode() if data is not None else None,
                                 method="POST" if data is not None else "GET")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _jsearch(q, where, country, days):
    query = f"{q} in {where}" if where else q
    params = {"query": query, "page": 1, "num_pages": 1}
    if country:
        params["country"] = country.lower()
    if days:
        params["date_posted"] = {1: "today", 3: "3days", 7: "week", 30: "month"}.get(days, "all")
    res = _get("https://jsearch.p.rapidapi.com/search?" + urllib.parse.urlencode(params),
               headers={"X-RapidAPI-Key": current_app.config["JSEARCH_API_KEY"], "X-RapidAPI-Host": "jsearch.p.rapidapi.com"})
    out = []
    for j in res.get("data", []) or []:
        sal = ""
        if j.get("job_min_salary") or j.get("job_max_salary"):
            sal = f"{j.get('job_min_salary') or ''} – {j.get('job_max_salary') or ''} {j.get('job_salary_currency') or ''}".strip(" –")
        out.append({"title": j.get("job_title"), "company": j.get("employer_name"), "city": j.get("job_city") or "",
                    "country_code": (j.get("job_country") or "")[:2], "url": j.get("job_apply_link") or j.get("job_google_link"),
                    "contract": (j.get("job_employment_type") or "").lower(), "salary": sal,
                    "posted": (j.get("job_posted_at_datetime_utc") or "")[:10],
                    "source": j.get("job_publisher") or "JSearch", "description": (j.get("job_description") or "")[:1500]})
    return out


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


def search(q, where="", country="", days=0):
    """Interroge tous les fournisseurs configurés. Renvoie (offres, erreurs)."""
    funcs = {"JSearch": _jsearch, "Adzuna": _adzuna, "Jooble": _jooble}
    results, errors = [], []
    for name in providers():
        try:
            results += funcs[name](q, where, country, days)
        except Exception as exc:
            errors.append(f"{name} : {exc}")
    seen, uniq = set(), []
    for r in results:
        key = ((r.get("title") or "").lower(), (r.get("company") or "").lower())
        if r.get("title") and key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq, errors
