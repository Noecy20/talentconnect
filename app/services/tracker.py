"""Suivi des candidatures (JAT) : synchronisation avec les candidatures TalentConnect,
statistiques, relances et import d'une offre depuis un lien."""
import ipaddress
import json
import re
import socket
import urllib.request
from datetime import date, datetime, timedelta
from html import unescape
from urllib.parse import urlparse

from ..extensions import db
from ..models import (TrackedApplication, TrackerEvent, STAGE_KEYS, SENT_STAGES, FINAL_STAGES, TRACKER_STAGES)

FOLLOWUP_DAYS = 7

# Statut d'une candidature TalentConnect -> étape du suivi
APP_TO_STAGE = {"received": "sent", "shortlisted": "waiting", "second_chance": "waiting", "interview": "interview",
                "offer": "offer", "hired": "accepted", "rejected": "refused"}


def add_event(tr, kind, content, at=None):
    db.session.add(TrackerEvent(tracker_id=tr.id, kind=kind, content=content, at=at or datetime.utcnow()))


def set_stage(tr, stage, note=None):
    if stage not in STAGE_KEYS or stage == tr.stage:
        return False
    old = tr.stage
    tr.stage = stage
    tr.stage_changed_at = datetime.utcnow()
    if stage in SENT_STAGES and not tr.applied_at:
        tr.applied_at = date.today()
    if stage in ("sent", "waiting") and not tr.next_followup:
        tr.next_followup = (tr.applied_at or date.today()) + timedelta(days=FOLLOWUP_DAYS)
    if stage in FINAL_STAGES or stage in ("interview", "test", "offer"):
        tr.next_followup = None if stage in FINAL_STAGES else tr.next_followup
    labels = dict(TRACKER_STAGES)
    add_event(tr, "stage", note or f"{labels.get(old, old)} → {labels.get(stage, stage)}")
    return True


def from_application(app):
    """Crée ou met à jour la fiche de suivi liée à une candidature TalentConnect."""
    tr = TrackedApplication.query.filter_by(application_id=app.id).first()
    if tr is None:
        tr = TrackedApplication.query.filter_by(user_id=app.candidate_id, job_id=app.job_id, application_id=None).first()
    job = app.job
    if tr is None:
        tr = TrackedApplication(user_id=app.candidate_id, title=job.title, stage="identified", source="TalentConnect")
        db.session.add(tr)
    tr.application_id, tr.job_id = app.id, job.id
    tr.company, tr.city, tr.country_code = job.company.name, job.city, job.country_code
    tr.contract, tr.source = job.contract_type, "TalentConnect"
    if job.salary_max:
        tr.salary = f"{job.salary_min or ''} – {job.salary_max} {job.currency}".strip(" –")
    if job.recruiter:
        tr.contact_name = tr.contact_name or job.recruiter.full_name
        tr.contact_role = tr.contact_role or (job.recruiter.recruiter.position if job.recruiter.recruiter else "")
    if app.cover_letter and not tr.cover_letter:
        tr.cover_letter = app.cover_letter
    db.session.flush()
    target = APP_TO_STAGE.get(app.status, "sent")
    if STAGE_KEYS.index(target) > STAGE_KEYS.index(tr.stage) or target in FINAL_STAGES:
        set_stage(tr, target)
    return tr


def sync_application(app):
    try:
        from_application(app)
    except Exception:  # le suivi ne doit jamais bloquer le recrutement
        db.session.rollback()


def stats(trackers):
    sent = [x for x in trackers if x.stage in SENT_STAGES]
    responses = [x for x in sent if x.stage in ("interview", "test", "offer", "accepted", "refused")]
    interviews = [x for x in sent if x.stage in ("interview", "test", "offer", "accepted")]
    offers = [x for x in sent if x.stage in ("offer", "accepted")]
    return {
        "total": len(trackers), "sent": len(sent), "responses": len(responses), "interviews": len(interviews),
        "offers": len(offers), "accepted": sum(1 for x in trackers if x.stage == "accepted"),
        "response_rate": round(len(responses) / len(sent) * 100) if sent else 0,
        "interview_rate": round(len(interviews) / len(sent) * 100) if sent else 0,
        "due": [x for x in trackers if x.followup_due],
        "deadlines": sorted([x for x in trackers if x.deadline and x.deadline >= date.today()
                             and x.stage in ("identified", "to_analyze", "to_apply", "prepared")],
                            key=lambda x: x.deadline)[:5],
    }


# --------------------------------------------------------------------------- import depuis un lien
BLOCKED_IMPORT = ("linkedin.com",)  # conditions d'utilisation : pas de lecture automatique


def _safe_url(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
    except Exception:
        return False
    return True


def source_from_url(url):
    host = (urlparse(url).hostname or "").lower()
    for key, name in [("linkedin", "LinkedIn"), ("indeed", "Indeed"), ("welcometothejungle", "Welcome to the Jungle"),
                      ("emploi.ci", "Emploi.ci"), ("educarriere", "Educarrière"), ("jobboom", "Jobboom"),
                      ("guichetemplois", "Guichet-Emplois"), ("francetravail", "France Travail"), ("glassdoor", "Glassdoor"),
                      ("apec", "APEC"), ("jobartis", "Jobartis")]:
        if key in host:
            return name
    return host.replace("www.", "") if host else ""


def import_from_url(url):
    """Lit l'annonce structurée (schema.org JobPosting, le format de Google for Jobs) d'une page publique."""
    data = {"url": url, "source": source_from_url(url)}
    host = (urlparse(url).hostname or "").lower()
    if any(b in host for b in BLOCKED_IMPORT):
        data["blocked"] = True
        return data
    if not _safe_url(url):
        data["error"] = "url"
        return data
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; TalentConnect/1.0)",
                                                   "Accept-Language": "fr,en;q=0.8"})
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="ignore")
    except Exception:
        data["error"] = "fetch"
        return data
    posting = None
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            obj = json.loads(block.strip())
        except Exception:
            continue
        items = obj if isinstance(obj, list) else obj.get("@graph", [obj]) if isinstance(obj, dict) else []
        for it in items:
            if isinstance(it, dict) and "JobPosting" in str(it.get("@type")):
                posting = it
                break
        if posting:
            break
    if posting:
        org = posting.get("hiringOrganization") or {}
        loc = posting.get("jobLocation") or {}
        loc = loc[0] if isinstance(loc, list) and loc else loc
        addr = (loc.get("address") if isinstance(loc, dict) else {}) or {}
        if isinstance(addr, str):
            addr = {"addressLocality": addr}
        sal = posting.get("baseSalary") or {}
        val = sal.get("value") if isinstance(sal, dict) else None
        salary = ""
        if isinstance(val, dict):
            lo, hi = val.get("minValue"), val.get("maxValue") or val.get("value")
            salary = " – ".join(str(x) for x in (lo, hi) if x) + (f" {sal.get('currency', '')}" if sal.get("currency") else "")
        desc = re.sub(r"<[^>]+>", " ", unescape(posting.get("description") or ""))
        data.update({
            "title": unescape(posting.get("title") or ""),
            "company": unescape(org.get("name", "") if isinstance(org, dict) else str(org)),
            "city": addr.get("addressLocality", ""),
            "country_code": (addr.get("addressCountry") if isinstance(addr.get("addressCountry"), str) else "")[:2].upper(),
            "salary": salary.strip(),
            "contract": str(posting.get("employmentType") or "").lower()[:30],
            "description": re.sub(r"\s+", " ", desc).strip()[:4000],
            "deadline": (posting.get("validThrough") or "")[:10],
        })
    else:
        m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html) or re.search(r"<title>(.*?)</title>", html, re.S)
        if m:
            data["title"] = unescape(m.group(1)).strip()[:200]
        data["partial"] = True
    return data
