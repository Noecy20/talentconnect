"""Ce que l'espace connecté affiche sur toutes les pages : le menu latéral,
le bouton « Création rapide » et les petites statistiques du menu profil.

Le menu est décrit une seule fois ici. Le menu latéral et la recherche (Ctrl/⌘ K)
lisent la même liste : ajouter une page au menu = ajouter une ligne ci-dessous.
"""
from flask import request, url_for
from flask_login import current_user

from .langues import t

# Une entrée de menu : (endpoint, icône Lucide, libellé, réservé aux comptes avec accès payant)
MENUS = {
    "candidate": [
        ("Espace candidat", [
            ("candidate.dashboard", "layout-dashboard", "Tableau de bord", False),
            ("candidate.cv_builder", "file-text", "CV Builder", False),
            ("candidate.profile", "user-round", "Mon profil", False),
        ]),
        ("Emploi", [
            ("candidate.jobs", "briefcase", "Offres pour moi", True),
            ("tracker.board", "kanban-square", "Mon suivi", True),
            ("candidate.applications", "send", "Mes candidatures", True),
            ("candidate.sponsorships", "handshake", "Mes parrainages", True),
            ("main.market", "map", "Métiers qui recrutent", True),
        ]),
        ("Évoluer", [
            ("candidate.orientation", "compass", "Orientation", True),
            ("main.personality_test", "brain", "Test de personnalité", False),
            ("assistant.mine", "bot", "Mon assistant IA", True),
        ]),
    ],
    "recruiter": [
        ("Espace recruteur", [
            ("recruiter.dashboard", "layout-dashboard", "Tableau de bord", False),
            ("recruiter.company", "building-2", "Mon entreprise", False),
            ("recruiter.verification", "shield-check", "Vérification", False),
        ]),
        ("Recrutement", [
            ("recruiter.jobs", "briefcase", "Mes offres", True),
            ("recruiter.talents", "search", "Trouver des talents", True),
            ("recruiter.pool", "sparkles", "Vivier seconde chance", True),
            ("recruiter.templates", "mail", "Modèles de messages", True),
            ("main.market", "map", "Marché de l'emploi", True),
            ("assistant.mine", "bot", "Assistant entreprise", True),
        ]),
    ],
    "sponsor": [
        ("Espace parrain", [
            ("sponsor.dashboard", "layout-dashboard", "Tableau de bord", False),
            ("sponsor.eligibility", "shield-check", "Mon éligibilité", False),
            ("assistant.mine", "bot", "Mon assistant IA", False),
        ]),
    ],
    "admin": [
        ("Administration", [
            ("admin.dashboard", "layout-dashboard", "Vue d'ensemble", False),
            ("admin.users", "users", "Utilisateurs & accès", False),
            ("admin.payments", "wallet", "Paiements", False),
            ("admin.plans", "tags", "Formules & prix", False),
            ("admin.sponsors", "shield-check", "Parrains", False),
            ("admin.recruiters", "badge-check", "Recruteurs à vérifier", False),
            ("admin.companies", "building-2", "Entreprises", False),
            ("admin.settings", "sliders-horizontal", "Réglages des modèles", False),
            ("main.market", "map", "Marché de l'emploi", False),
        ]),
    ],
}

# Commun à tous les rôles, en bas du menu
COMMUNICATION = ("Communication", [("messages.inbox", "inbox", "Messages", False)])

# Bouton « Création rapide » : uniquement des pages qui existent déjà
CREATIONS = {
    "candidate": [
        ("tracker.new", "plus-square", "Ajouter une candidature au suivi"),
        ("candidate.cv_builder", "file-plus", "Créer ou modifier mon CV"),
        ("tracker.projects", "plane", "Nouveau projet de mobilité"),
        ("candidate.sponsorships", "handshake", "Demander un parrainage"),
    ],
    "recruiter": [
        ("recruiter.job_new", "briefcase", "Publier une offre"),
        ("recruiter.talents", "user-search", "Rechercher des talents"),
        ("recruiter.templates", "mail-plus", "Nouveau modèle de message"),
    ],
    "sponsor": [
        ("sponsor.eligibility", "shield-check", "Compléter mon éligibilité"),
        ("assistant.mine", "bot", "Configurer mon assistant"),
    ],
    "admin": [
        ("admin.plans", "tags", "Nouvelle formule"),
        ("admin.payments", "wallet", "Valider un paiement"),
        ("admin.recruiters", "badge-check", "Vérifier un recruteur"),
    ],
}

ROLES = {"candidate": "Candidat", "recruiter": "Recruteur", "sponsor": "Parrain", "admin": "Admin"}


def _est_actif(cible, courant):
    """Un lien reste allumé sur sa page et sur les pages qui en dépendent :
    « Mes offres » (recruiter.jobs) reste actif sur recruiter.job_pipeline, etc."""
    if not courant:
        return False
    if courant == cible:
        return True
    bp_cible, _, page_cible = cible.partition(".")
    bp, _, page = courant.partition(".")
    if bp != bp_cible or page_cible == "dashboard":
        return False
    if page_cible in ("board", "inbox"):       # tout le suivi, toute la messagerie
        return True
    return page.startswith(page_cible.rstrip("s"))


def menu():
    """Sections du menu de l'utilisateur connecté, prêtes à afficher."""
    sections = MENUS.get(current_user.role, []) + [COMMUNICATION]
    return [(t(titre), [{"ep": ep, "url": url_for(ep), "icone": icone, "libelle": t(libelle),
                         "verrou": payant and not current_user.has_access,
                         "actif": _est_actif(ep, request.endpoint)}
                        for ep, icone, libelle, payant in liens])
            for titre, liens in sections]


def creations():
    return [(ep, icone, t(libelle)) for ep, icone, libelle in CREATIONS.get(current_user.role, [])]


def role_libelle(role=None):
    return t(ROLES.get(role or current_user.role, ""))


def mini_stats():
    """Trois chiffres affichés en haut du menu profil, propres à chaque rôle."""
    from .modeles import (Application, Job, Payment, RecruiterProfile, Setting, Sponsorship, User)
    u = current_user
    if u.role == "candidate":
        from .ia import scores
        apps = Application.query.filter_by(candidate_id=u.id)
        entretiens = apps.filter(Application.status.in_(("interview", "offer", "hired"))).count()
        return [(apps.count(), t("Candidatures")), (entretiens, t("Entretiens")),
                (f"{round(scores.profile_completeness(u) * 100)} %", t("Profil complété"))]
    if u.role == "recruiter":
        co = u.recruiter.company_id if u.recruiter else None
        offres = Job.query.filter_by(company_id=co, status="open").count()
        a_traiter = Application.query.join(Job).filter(
            Job.company_id == co, Application.status.in_(("received", "shortlisted"))).count()
        return [(offres, t("Offres actives")), (a_traiter, t("À traiter")),
                (Application.query.join(Job).filter(Job.company_id == co).count(), t("Candidatures"))]
    if u.role == "sponsor":
        from .routes.parrain import used_this_year
        sp = u.sponsor
        return [(Sponsorship.query.filter_by(sponsor_id=u.id).count(), t("Filleuls")),
                (f"{used_this_year(u.id)}/{Setting.get('sponsor_max_per_year')}", t("Cette année")),
                (f"{round(sp.reputation) if sp else 0} %", t("Réputation"))]
    return [(User.query.count(), t("Utilisateurs")),
            (Payment.query.filter_by(status="pending").count(), t("Paiements à valider")),
            (RecruiterProfile.query.filter_by(verification_status="pending").count(), t("Recruteurs à vérifier"))]
