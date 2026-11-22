"""Offres de démonstration (créées par « flask seed-demo ») : les retrouver et les supprimer.

Une offre est « de démo » si elle a été publiée par un recruteur dont l'adresse finit par @demo.tc.
La suppression est définitive et emporte ce qui dépend de ces offres : candidatures, entrées
de vivier. Les messages et le suivi des candidats sont conservés, simplement détachés.
Les comptes de démo eux-mêmes ne sont pas touchés."""
from ..extensions import db
from ..modeles import Job, Application, Message, TalentPool, TrackedApplication, User


def offres_demo():
    recruteurs = [u.id for u in User.query.filter(User.email.like("%@demo.tc"), User.role == "recruiter")]
    return Job.query.filter(Job.recruiter_id.in_(recruteurs)).all() if recruteurs else []


def supprimer_offres_demo():
    """Supprime les offres de démo. Renvoie (nombre d'offres, nombre de candidatures) supprimées."""
    ids = [j.id for j in offres_demo()]
    if not ids:
        return 0, 0
    candidatures = [a.id for a in Application.query.filter(Application.job_id.in_(ids))]
    # On détache d'abord ce qui pointe vers ces offres et candidatures
    if candidatures:
        Message.query.filter(Message.application_id.in_(candidatures)).update({"application_id": None}, synchronize_session=False)
        TrackedApplication.query.filter(TrackedApplication.application_id.in_(candidatures)).update(
            {"application_id": None}, synchronize_session=False)
    TrackedApplication.query.filter(TrackedApplication.job_id.in_(ids)).update({"job_id": None}, synchronize_session=False)
    TalentPool.query.filter(TalentPool.source_job_id.in_(ids)).delete(synchronize_session=False)
    Application.query.filter(Application.job_id.in_(ids)).delete(synchronize_session=False)
    Job.query.filter(Job.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return len(ids), len(candidatures)
