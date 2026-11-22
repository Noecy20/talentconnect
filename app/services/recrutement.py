"""Flux de recrutement : candidature, accusé de réception automatique,
tri assisté et envoi groupé des réponses."""
from datetime import datetime

from ..extensions import db
from ..modeles import Application, TalentPool, Sponsorship
from . import emails
from ..ia import scores, llm


def _ctx(app, recruiter=None, note=""):
    job = app.job
    return dict(candidate=app.candidate.full_name, job=job.title, company=job.company.name,
                recruiter=(recruiter.full_name if recruiter else (job.recruiter.full_name if job.recruiter else "")),
                note=note, feedback=emails.format_feedback(app.feedback))


def apply(candidate, job, cover_letter=""):
    existing = Application.query.filter_by(job_id=job.id, candidate_id=candidate.id).first()
    if existing:
        return existing, False
    score, detail = scores.match(candidate, job)
    prob = scores.call_probability(candidate, job, score)
    a = Application(job_id=job.id, candidate_id=candidate.id, cover_letter=cover_letter,
                    match_score=score, match_breakdown=detail, call_probability=prob)
    db.session.add(a)
    db.session.flush()
    a.ai_group, a.ai_reason = scores.triage(a)
    # Accusé de réception automatique : plus jamais de candidature sans réponse
    subj, body = emails.get_template("ack", job.company_id)
    ctx = _ctx(a)
    emails.send(candidate, emails.render_text(subj, **ctx), emails.render_text(body, **ctx),
                kind="ack", sender=job.recruiter, application=a)
    a.ack_sent_at = datetime.utcnow()
    db.session.commit()
    _sync(a)
    return a, True


def refresh_scores(job):
    for a in job.applications.all():
        a.match_score, a.match_breakdown = scores.match(a.candidate, job)
        a.call_probability = scores.call_probability(a.candidate, job, a.match_score)
        a.ai_group, a.ai_reason = scores.triage(a)
    db.session.commit()


STATUS_FOR_GROUP = {"interview": "interview", "second_chance": "second_chance", "rejected": "rejected"}


def decide(applications, group, recruiter, note="", custom_subject=None, custom_body=None):
    """Applique une décision à un lot de candidatures et envoie les messages d'un coup."""
    ids = []
    for a in applications:
        job = a.job
        if group in ("rejected", "second_chance"):
            a.feedback = scores.refusal_feedback(a)
            ai_text = llm.generate(
                "Tu es un recruteur bienveillant. Rédige en 4 à 6 lignes un retour constructif, concret et "
                "encourageant pour un candidat non retenu, à partir des éléments fournis. Pas de formule d'appel.",
                f"Poste : {job.title}\nRaisons : {a.feedback['reasons']}\nConseils : {a.feedback['tips']}",
                max_tokens=300)
            if ai_text:
                a.feedback["text"] = ai_text
        if group == "second_chance":
            if not TalentPool.query.filter_by(company_id=job.company_id, candidate_id=a.candidate_id).first():
                db.session.add(TalentPool(company_id=job.company_id, candidate_id=a.candidate_id,
                                          source_job_id=job.id, note=a.ai_reason or ""))
        a.status = STATUS_FOR_GROUP.get(group, group)
        a.decided_at = datetime.utcnow()
        subj, body = emails.get_template(group, job.company_id)
        if custom_subject:
            subj = custom_subject
        if custom_body:
            body = custom_body
        ctx = _ctx(a, recruiter, note)
        if a.feedback and a.feedback.get("text"):
            ctx["feedback"] = a.feedback["text"]
        m = emails.send(a.candidate, emails.render_text(subj, **ctx), emails.render_text(body, **ctx),
                        kind=group, sender=recruiter, application=a, defer=True)
        ids.append(m.id)
    db.session.commit()
    for a in applications:
        _sync(a)
    emails.dispatch(ids)
    return len(ids)


def mark_hired(application):
    """Embauche : la réputation des parrains du candidat augmente."""
    application.status = "hired"
    application.decided_at = datetime.utcnow()
    for s in Sponsorship.query.filter_by(candidate_id=application.candidate_id, status="active").all():
        scores.update_reputation(s.sponsor_id, +5)
    db.session.commit()
    _sync(application)


def cover_letter(candidate, job):
    """Lettre de motivation adaptée à l'offre (IA si disponible, sinon modèle structuré)."""
    cp = candidate.candidate
    score, d = scores.match(candidate, job)
    found = ", ".join(d.get("skills_found", [])[:4]) or ", ".join((cp.skills or [])[:4])
    soft = ", ".join((cp.soft_skills or [])[:3])
    ai = llm.generate(
        "Tu rédiges des lettres de motivation professionnelles, sincères et concises (180-250 mots), "
        "sans inventer de faits. Langue : celle de l'offre.",
        f"Candidat : {candidate.full_name}, {cp.headline}. Résumé : {cp.summary}. Compétences : {cp.skills}. "
        f"Soft skills : {cp.soft_skills}. Expérience : {cp.years_experience} ans.\n"
        f"Offre : {job.title} chez {job.company.name}. Description : {job.description}. "
        f"Compétences demandées : {job.skills}", max_tokens=700)
    if ai:
        return ai
    return (f"Madame, Monsieur,\n\n"
            f"Votre offre « {job.title} » chez {job.company.name} a retenu toute mon attention. "
            f"{cp.headline or 'Professionnel(le) motivé(e)'}, je dispose de {cp.years_experience:g} an(s) d'expérience"
            f"{' en ' + cp.field if cp.field else ''}.\n\n"
            f"Je maîtrise notamment {found}, des compétences directement utiles pour ce poste. "
            f"{('Mes atouts — ' + soft + ' — me permettent de m’intégrer rapidement et de contribuer aux objectifs de votre équipe.') if soft else ''}\n\n"
            f"{cp.summary or ''}\n\n"
            f"Je serais ravi(e) d'échanger avec vous pour vous présenter ma motivation plus en détail.\n\n"
            f"Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.\n\n{candidate.full_name}")


def cover_letter_for(candidate, title, company, description=""):
    """Lettre de motivation pour une offre externe (LinkedIn, site carrière…)."""
    cp = candidate.candidate
    ai = llm.generate(
        "Tu rédiges des lettres de motivation professionnelles, sincères et concises (180-250 mots), "
        "sans inventer de faits. Langue : celle de l'offre.",
        f"Candidat : {candidate.full_name}, {cp.headline}. Résumé : {cp.summary}. Compétences : {cp.skills}. "
        f"Soft skills : {cp.soft_skills}. Expérience : {cp.years_experience} ans.\n"
        f"Offre : {title} chez {company}. Description : {description[:3000]}", max_tokens=700)
    if ai:
        return ai
    skills = ", ".join((cp.skills or [])[:4])
    soft = ", ".join((cp.soft_skills or [])[:3])
    return (f"Madame, Monsieur,\n\n"
            f"Votre offre « {title} »{' chez ' + company if company else ''} a retenu toute mon attention. "
            f"{cp.headline or 'Professionnel(le) motivé(e)'}, je dispose de {cp.years_experience:g} an(s) d'expérience"
            f"{' en ' + cp.field if cp.field else ''}.\n\n"
            f"{('Je maîtrise notamment ' + skills + '. ') if skills else ''}"
            f"{('Mes atouts — ' + soft + ' — me permettent de m’intégrer rapidement et de contribuer aux objectifs de votre équipe.') if soft else ''}\n\n"
            f"{cp.summary or ''}\n\n"
            f"Je serais ravi(e) d'échanger avec vous pour vous présenter ma motivation plus en détail.\n\n"
            f"Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.\n\n{candidate.full_name}")


def _sync(application):
    """Met à jour le suivi personnel (JAT) du candidat."""
    from . import suivi
    suivi.sync_application(application)
    db.session.commit()
