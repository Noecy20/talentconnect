"""Commandes : flask init-db | flask seed-demo | flask create-admin | flask translate <lang>"""
import json
import os
import random
import re
from datetime import datetime, timedelta

import click

from .extensions import db


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Crée les tables, le compte admin et les formules par défaut."""
        from flask_migrate import upgrade
        upgrade(directory=os.path.join(os.path.dirname(app.root_path), "migrations"))
        _bootstrap(app)
        click.echo("✓ Base initialisée.")

    @app.cli.command("create-admin")
    @click.argument("email")
    @click.argument("password")
    def create_admin(email, password):
        from .modeles import User
        u = User.query.filter_by(email=email.lower()).first() or User(email=email.lower(), role="admin", first_name="Admin")
        u.role = "admin"
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"✓ Admin {email} prêt.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Remplit la base avec des données de démonstration réalistes."""
        from flask_migrate import upgrade
        upgrade(directory=os.path.join(os.path.dirname(app.root_path), "migrations"))
        _bootstrap(app)
        _seed(app)
        click.echo("✓ Données de démo créées. Mot de passe de tous les comptes démo : Demo1234!")

    @app.cli.command("send-reminders")
    def send_reminders():
        """Envoie (par e-mail et dans l'app) les relances du jour. À planifier chaque matin (cron Render)."""
        from datetime import date
        from .modeles import TrackedApplication, User, FINAL_STAGES
        from .services import emails
        due = TrackedApplication.query.filter(TrackedApplication.next_followup <= date.today(),
                                              TrackedApplication.archived.is_(False)).all()
        by_user = {}
        for x in due:
            if x.stage not in FINAL_STAGES:
                by_user.setdefault(x.user_id, []).append(x)
        for uid, items in by_user.items():
            u = db.session.get(User, uid)
            lines = "\n".join(f"• {x.title} — {x.company} (relance prévue le {x.next_followup:%d/%m})" for x in items)
            emails.send(u, f"{len(items)} relance(s) à faire aujourd'hui",
                        f"Bonjour {u.first_name},\n\nVoici les candidatures à relancer :\n{lines}\n\n"
                        f"Un message court et poli suffit : rappelez le poste, votre motivation et votre disponibilité.",
                        kind="system", sync=True)
        click.echo(f"Relances envoyées à {len(by_user)} candidat(s).")

    @app.cli.command("supprimer-offres-demo")
    @click.option("--oui", is_flag=True, help="Ne pas demander de confirmation.")
    def supprimer_offres_demo(oui):
        """Supprime définitivement les offres de démonstration (aussi possible depuis l'espace admin)."""
        from .services import donnees_demo
        offres = donnees_demo.offres_demo()
        if not offres:
            click.echo("Aucune offre de démonstration trouvée.")
            return
        click.echo(f"{len(offres)} offre(s) de démo vont être supprimées :")
        for j in offres:
            click.echo(f"  - {j.title} ({j.company.name})")
        if not oui and not click.confirm("Suppression définitive, impossible à annuler. Continuer ?"):
            click.echo("Rien n'a été supprimé.")
            return
        n, c = donnees_demo.supprimer_offres_demo()
        click.echo(f"✓ {n} offre(s) de démo et {c} candidature(s) liée(s) supprimées.")

    @app.cli.command("ia-test")
    def ia_test():
        """Vérifie l'IA générative : fournisseur, modèles gratuits disponibles, et une vraie réponse."""
        from .ia import llm
        if not llm.enabled():
            click.echo("Aucune clé IA : ajoutez OPENROUTER_API_KEY dans .env.")
            return
        click.echo(f"Fournisseur : {llm.fournisseur()}")
        modeles = llm.etat()["modeles"]
        click.echo(f"{len(modeles)} modèle(s) dans la file, les 8 premiers :")
        for m in modeles[:8]:
            click.echo(f"  - {m}")
        reponse = llm.generate("Tu réponds en français, en une phrase.", "Dis bonjour à une candidate qui cherche un emploi.", 300)
        etat = llm.etat()
        click.echo(f"Réponse de {etat['dernier_modele']} : {reponse}" if reponse else "Aucun modèle n'a répondu.")
        for m, s in etat["au_repos"].items():
            click.echo(f"  au repos {s}s : {m}")

    @app.cli.command("translate")
    @click.argument("lang")
    def translate(lang):
        """Extrait les textes de l'app et traduit les manquants avec l'IA générative (clé requise)."""
        from .ia import llm
        strings = extract_strings(app)
        path = os.path.join(app.root_path, "traductions", f"{lang}.json")
        data = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
        missing = [s for s in strings if s not in data]
        click.echo(f"{len(strings)} textes, {len(missing)} à traduire en {lang}.")
        if not llm.enabled():
            click.echo("⚠ Aucune clé IA (OPENROUTER_API_KEY ou ANTHROPIC_API_KEY) : rien n'est traduit.")
            return
        for i in range(0, len(missing), 60):
            chunk = missing[i:i + 60]
            out = llm.generate(f"Translate each French UI string to language code '{lang}'. Keep {{placeholders}} unchanged. "
                               "Answer ONLY with a JSON object mapping each source string to its translation.",
                               json.dumps(chunk, ensure_ascii=False), max_tokens=8000)
            try:
                data.update(json.loads(out[out.index("{"):out.rindex("}") + 1]))
            except Exception:
                click.echo("Lot ignoré (réponse illisible).")
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
        click.echo(f"✓ {path}")


def extract_strings(app):
    pat = re.compile(r"""\bt\(\s*(['"])((?:\\.|(?!\1).)*)\1""")
    found = set()
    for root, _, files in os.walk(app.root_path):
        for fn in files:
            if fn.endswith((".html", ".py")):
                txt = open(os.path.join(root, fn), encoding="utf-8").read()
                for m in pat.finditer(txt):
                    found.add(m.group(2).replace("\\'", "'"))
    from .ia import orientation
    from . import EDU_LABELS, CONTRACT_LABELS, SENIORITY_LABELS
    for typ in orientation.TYPES.values():
        found.update([typ["name"], typ["desc"]])
    found.update(q for _, q in orientation.QUESTIONS)
    found.update(orientation.SUBJECTS)
    for f in orientation.FIELDS:
        found.add(f["field"])
        found.update(f["jobs"])
    for d in (EDU_LABELS, CONTRACT_LABELS, SENIORITY_LABELS):
        found.update(d.values())
    return sorted(found)


def _bootstrap(app):
    from .modeles import User, Plan, Setting
    if not User.query.filter_by(role="admin").first():
        u = User(email=app.config["ADMIN_EMAIL"].lower(), role="admin", first_name="Admin", last_name="TalentConnect")
        u.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(u)
    if not Plan.query.first():
        db.session.add_all([
            Plan(role="candidate", name="Formule unique", price=1000, currency="XOF", duration_days=30, highlighted=True,
                 features=["Offres personnalisées et score de compatibilité", "Chance d'être appelé", "Candidatures et lettres de motivation",
                           "Parrainages", "Orientation RIASEC", "Suivi des candidatures", "Assistant IA personnel",
                           "Marché de l'emploi"]),
            Plan(role="recruiter", name="Formule unique", price=225000, currency="XOF", duration_days=365, highlighted=True,
                 features=["Offres illimitées", "Pipeline de recrutement", "Tri IA et réponses groupées", "Recherche de talents",
                           "Vivier de talents", "Modèles de messages", "Assistant IA entreprise"]),
        ])
    for k, v in Setting.DEFAULTS.items():
        if db.session.get(Setting, k) is None:
            db.session.add(Setting(key=k, value=v))
    db.session.commit()


def _slug(*parts):
    import unicodedata
    out = ".".join(unicodedata.normalize("NFKD", p).encode("ascii", "ignore").decode().lower() for p in parts)
    return re.sub(r"[^a-z.]", "", out)


def _seed(app):
    from .modeles import (User, Company, Job, Sponsorship, SponsorshipRequest, TalentPool, Payment, Plan)
    from .routes.authentification import create_user
    from .ia import scores
    from .services import recrutement
    random.seed(7)
    if User.query.filter_by(email="aicha.kone@demo.tc").first():
        click.echo("Données de démo déjà présentes.")
        return
    PW = "Demo1234!"

    # --- entreprises & recruteurs
    companies = [
        ("Orange Côte d'Ivoire", "Télécoms", "1000+", "CI", "Abidjan", "orange.ci", "Opérateur télécom leader, engagé dans l'innovation numérique en Afrique de l'Ouest.", "Awa", "Traoré"),
        ("Ecobank", "Banque", "1000+", "CI", "Abidjan", "ecobank.com", "Groupe bancaire panafricain présent dans 33 pays.", "Serge", "Kouassi"),
        ("Wave Sénégal", "Fintech", "201-1000", "SN", "Dakar", "wave.com", "Mobile money simple et abordable.", "Mariama", "Diallo"),
        ("Jumia", "E-commerce", "1000+", "CI", "Abidjan", "jumia.ci", "Plateforme e-commerce de référence en Afrique.", "Jean", "Bamba"),
        ("Atelier Lumière", "Design & communication", "11-50", "FR", "Paris", "atelierlumiere.fr", "Agence de design et de communication digitale.", "Claire", "Martin"),
        ("Bolloré Logistics", "Logistique", "1000+", "CI", "Abidjan", "bollore-logistics.com", "Leader de la logistique et du transport international.", "Ibrahim", "Ouattara"),
    ]
    recs = []
    for name, sector, size, cc, city, web, desc, fn, ln in companies:
        u = create_user(f"{_slug(fn, ln)}@demo.tc", PW, "recruiter", fn, ln, cc, city, "fr", name)
        db.session.flush()
        co = u.recruiter.company
        co.sector, co.size, co.website, co.description, co.verified = sector, size, web, desc, True
        co.registration_number = f"RCCM-{cc}-{random.randint(10000, 99999)}"
        u.recruiter.position = "Responsable recrutement"
        u.recruiter.work_email, u.recruiter.work_email_verified = f"{_slug(fn, ln)}@{web}", True
        u.recruiter.verification_status, u.recruiter.verification_method = "verified", "email_domain"
        u.recruiter.verified_at = datetime.utcnow()
        u.grant_access(90)
        recs.append(u)
    db.session.commit()

    jobs_spec = [
        (0, "Data Analyst", "Data / Intelligence artificielle", "cdi", "bac5", 2, ["SQL", "Python", "Power BI", "Excel"], ["Esprit d'analyse", "Communication"], "Abidjan", 600000, 900000),
        (0, "Développeur Full Stack", "Informatique / Développement", "cdi", "bac3", 3, ["JavaScript", "React", "Python", "Django", "Git"], ["Travail d'équipe", "Autonomie"], "Abidjan", 700000, 1100000),
        (0, "Stagiaire Marketing digital", "Commerce / Marketing", "internship", "bac3", 0, ["Réseaux sociaux", "Canva", "Rédaction web"], ["Créativité"], "Abidjan", 150000, 200000),
        (1, "Analyste financier", "Finance / Comptabilité", "cdi", "bac5", 3, ["Excel", "Modélisation financière", "Analyse financière", "SAP"], ["Rigueur", "Esprit d'analyse"], "Abidjan", 900000, 1400000),
        (1, "Conseiller clientèle", "Banque / Assurance", "cdd", "bac2", 1, ["Relation client", "Vente", "Excel"], ["Sens du service", "Communication"], "Abidjan", 350000, 450000),
        (1, "Comptable junior", "Finance / Comptabilité", "cdi", "bac3", 1, ["Comptabilité", "Sage", "Excel", "Fiscalité"], ["Rigueur", "Organisation"], "Bouaké", 400000, 550000),
        (2, "Product Manager", "Management / Entrepreneuriat", "cdi", "bac5", 4, ["Gestion de produit", "Agile", "SQL", "UX"], ["Leadership", "Communication"], "Dakar", 1200000, 1800000),
        (2, "Ingénieur Backend", "Informatique / Développement", "cdi", "bac5", 3, ["Python", "PostgreSQL", "Docker", "API REST"], ["Autonomie", "Résolution de problèmes"], "Dakar", 1000000, 1500000),
        (2, "Agent support client", "Administration / Secrétariat", "cdd", "bac", 0, ["Relation client", "Wolof", "Français"], ["Empathie", "Gestion du stress"], "Dakar", 200000, 280000),
        (3, "Responsable logistique e-commerce", "Logistique / Transport", "cdi", "bac4", 4, ["Supply chain", "Excel", "Gestion des stocks", "ERP"], ["Organisation", "Leadership"], "Abidjan", 800000, 1100000),
        (3, "Community Manager", "Journalisme / Communication", "cdi", "bac3", 2, ["Réseaux sociaux", "Rédaction web", "Canva", "Meta Ads"], ["Créativité", "Communication"], "Abidjan", 350000, 500000),
        (4, "UX/UI Designer", "Design graphique / UX", "cdi", "bac5", 2, ["Figma", "UX", "Design system", "Prototypage"], ["Créativité", "Empathie"], "Paris", 3000, 3800),
        (4, "Graphiste junior", "Design graphique / UX", "alternance", "bac3", 0, ["Illustrator", "Photoshop", "Canva"], ["Créativité", "Rigueur"], "Lyon", 1200, 1500),
        (5, "Déclarant en douane", "Logistique / Transport", "cdi", "bac2", 2, ["Transit", "Douane", "Excel"], ["Rigueur", "Négociation"], "San-Pédro", 400000, 600000),
        (5, "Chef de quai", "Logistique / Transport", "cdd", "bac", 3, ["Gestion des stocks", "Management d'équipe", "Sécurité"], ["Leadership", "Ponctualité"], "Abidjan", 350000, 450000),
        (0, "Technicien réseaux télécoms", "Réseaux / Cybersécurité", "cdi", "bac2", 2, ["Réseaux", "Fibre optique", "Cisco"], ["Autonomie"], "Yamoussoukro", 400000, 600000),
    ]
    jobs = []
    for idx, title, field, contract, edu, exp, skills, soft, city, smin, smax in jobs_spec:
        r = recs[idx]
        co = r.recruiter.company
        cc = co.country_code
        from .geographie import currency_for
        j = Job(company_id=co.id, recruiter_id=r.id, title=title, field=field, contract_type=contract, education_level=edu,
                min_experience=exp, skills=skills, soft_skills=soft, languages=["Anglais"] if exp >= 3 else [],
                country_code=cc, city=city, salary_min=smin, salary_max=smax, currency=currency_for(cc),
                remote=title in ("UX/UI Designer", "Ingénieur Backend"),
                description=f"{co.name} recherche un(e) {title} pour renforcer ses équipes à {city}.\n\n"
                            f"Missions principales :\n• Contribuer aux projets stratégiques de l'équipe\n• Garantir la qualité et le respect des délais\n"
                            f"• Collaborer avec les équipes métiers et techniques\n\nProfil : {', '.join(skills[:3])} ; {exp} an(s) d'expérience minimum.\n\n"
                            f"Avantages : assurance santé, formation continue, environnement stimulant.",
                created_at=datetime.utcnow() - timedelta(days=random.randint(0, 25)))
        db.session.add(j)
        jobs.append(j)
    db.session.commit()

    # --- parrains
    sponsors_spec = [
        ("Kouadio", "N'Guessan", "Directeur financier", "Ecobank", "ecobank.com", "director", 15, "bac5", 25),
        ("Fatou", "Sow", "Head of Engineering", "Wave Sénégal", "wave.com", "senior_manager", 11, "bac5", 18),
        ("Marc", "Yao", "Manager Data", "Orange Côte d'Ivoire", "orange.ci", "manager", 8, "bac5", 6),
    ]
    sponsors = []
    for fn, ln, pos, org, web, sen, yrs, edu, team in sponsors_spec:
        u = create_user(f"{_slug(fn, ln)}@demo.tc", PW, "sponsor", fn, ln, "CI", "Abidjan", "fr")
        db.session.flush()
        sp = u.sponsor
        sp.position, sp.organization, sp.organization_website = pos, org, web
        sp.professional_email = f"{_slug(fn, ln)}@{web}"
        sp.linkedin = f"https://linkedin.com/in/{_slug(fn, ln).replace('.', '-')}"
        sp.seniority, sp.years_experience, sp.education_level, sp.team_size = sen, yrs, edu, team
        sp.bio = f"{pos} chez {org}, {yrs} ans d'expérience. J'accompagne les jeunes talents dans leur parcours professionnel."
        scores.decide_sponsor(sp, u)
        sp.status, sp.level = "approved", sp.level or scores.sponsor_level(sp.eligibility_score)
        sp.reputation = random.choice([55, 62, 70])
        sponsors.append(u)
    db.session.commit()

    # --- candidats
    cands_spec = [
        ("Aïcha", "Koné", "Data Analyst passionnée par la BI", "Data / Intelligence artificielle", "bac5", 3, ["SQL", "Python", "Power BI", "Excel", "Tableau", "Statistiques"], ["Esprit d'analyse", "Communication", "Rigueur"], "CI", "Abidjan", True),
        ("Koffi", "Assi", "Développeur web full stack", "Informatique / Développement", "bac3", 4, ["JavaScript", "React", "Node.js", "Python", "Git", "Docker"], ["Travail d'équipe", "Autonomie"], "CI", "Abidjan", False),
        ("Mariam", "Diabaté", "Comptable rigoureuse", "Finance / Comptabilité", "bac3", 2, ["Comptabilité", "Sage", "Excel", "Fiscalité"], ["Rigueur", "Organisation"], "CI", "Bouaké", False),
        ("Yao", "Brou", "Analyste financier junior", "Finance / Comptabilité", "bac5", 2, ["Excel", "Analyse financière", "Modélisation financière", "Power BI"], ["Esprit d'analyse"], "CI", "Abidjan", True),
        ("Ama", "Touré", "Community manager créative", "Journalisme / Communication", "bac3", 1, ["Réseaux sociaux", "Canva", "Rédaction web"], ["Créativité", "Communication"], "CI", "Abidjan", False),
        ("Moussa", "Ndiaye", "Ingénieur backend Python", "Informatique / Développement", "bac5", 5, ["Python", "Django", "PostgreSQL", "Docker", "API REST", "AWS"], ["Résolution de problèmes", "Leadership"], "SN", "Dakar", True),
        ("Fanta", "Keïta", "Chargée de clientèle", "Banque / Assurance", "bac2", 1, ["Relation client", "Vente"], ["Sens du service", "Empathie"], "CI", "Abidjan", False),
        ("Eric", "Zadi", "Logisticien", "Logistique / Transport", "bac4", 5, ["Supply chain", "Gestion des stocks", "Excel", "ERP", "Transit"], ["Organisation", "Leadership"], "CI", "Abidjan", False),
        ("Léa", "Dubois", "UX designer", "Design graphique / UX", "bac5", 3, ["Figma", "UX", "Prototypage", "Design system", "User research"], ["Empathie", "Créativité"], "FR", "Paris", True),
        ("Paul", "N'Dri", "Technicien réseaux", "Réseaux / Cybersécurité", "bac2", 3, ["Réseaux", "Cisco", "Fibre optique", "Linux"], ["Autonomie", "Ponctualité"], "CI", "Yamoussoukro", False),
        ("Aminata", "Fall", "Product owner", "Management / Entrepreneuriat", "bac5", 4, ["Agile", "Gestion de produit", "UX", "Jira"], ["Leadership", "Communication"], "SN", "Dakar", True),
        ("Ibrahim", "Cissé", "Étudiant en marketing", "Commerce / Marketing", "bac3", 0, ["Réseaux sociaux", "Canva", "Excel"], ["Créativité", "Adaptabilité"], "CI", "Abidjan", False),
    ]
    cands = []
    for fn, ln, head, field, edu, yrs, skills, soft, cc, city, intl in cands_spec:
        u = create_user(f"{_slug(fn, ln)}@demo.tc", PW, "candidate", fn, ln, cc, city, "fr")
        db.session.flush()
        cp = u.candidate
        cp.headline, cp.field, cp.education_level, cp.years_experience = head, field, edu, yrs
        cp.skills, cp.soft_skills = skills, soft
        cp.languages = [{"name": "Français", "level": "C2"}, {"name": "Anglais", "level": random.choice(["B1", "B2", "C1"])}]
        cp.summary = f"{head} avec {yrs} an(s) d'expérience. Motivé(e) par les projets à impact, je cherche à rejoindre une équipe ambitieuse."
        cp.desired_position = head.split(" ")[0] + " " + head.split(" ")[1] if " " in head else head
        cp.desired_contracts = ["cdi", "cdd"]
        cp.open_to_international = intl
        cp.linkedin = f"linkedin.com/in/{_slug(fn, ln).replace('.', '-')}"
        u.created_at = datetime.utcnow() - timedelta(days=random.randint(0, 28))
        if random.random() < 0.6:
            u.grant_access(30)
        cands.append(u)
    db.session.commit()
    # Accès garanti pour le compte de démonstration principal
    cands[0].grant_access(90)

    # --- parrainages
    pairs = [(0, 2, "J'étais son manager direct", "2021 – 2024", "Orange Côte d'Ivoire"),
             (0, 0, "Elle a réalisé une mission d'audit data pour ma direction", "2023", "Ecobank"),
             (3, 0, "Analyste dans mon équipe", "2022 – 2024", "Ecobank"),
             (5, 1, "Ingénieur dans mon équipe backend", "2020 – 2024", "Wave Sénégal"),
             (10, 1, "Product owner sur notre app mobile", "2021 – 2023", "Wave Sénégal"),
             (1, 2, "Développeur sur nos outils internes", "2022", "Orange Côte d'Ivoire")]
    for ci, si, rel, period, org in pairs:
        c, s = cands[ci], sponsors[si]
        req = SponsorshipRequest(candidate_id=c.id, invitee_name=s.full_name, invitee_email=s.email, relation=rel, status="completed")
        db.session.add(req)
        db.session.flush()
        db.session.add(Sponsorship(sponsor_id=s.id, candidate_id=c.id, request_id=req.id, relation=rel, period=period, organization=org,
                                   skill_ratings={k: random.choice([4, 5]) for k in c.candidate.skills[:3]},
                                   soft_ratings={k: random.choice([4, 5]) for k in c.candidate.soft_skills[:2]},
                                   recommendation=f"{c.first_name} est un(e) professionnel(le) fiable et talentueux(se). "
                                                  f"Je l'ai vu(e) progresser rapidement et livrer des résultats concrets. Je le/la recommande sans réserve.",
                                   created_at=datetime.utcnow() - timedelta(days=random.randint(1, 20))))
    db.session.add(SponsorshipRequest(candidate_id=cands[0].id, invitee_name="Directeur stage", invitee_email="", relation="Mon maître de stage", status="sent"))
    db.session.commit()

    # --- candidatures (sans envoi d'e-mail réel)
    app.config["MAIL_USERNAME"] = ""
    for c in cands:
        ranked = sorted(jobs, key=lambda j: -scores.match(c, j)[0])[:3]
        for j in ranked:
            a, _ = recrutement.apply(c, j, "Madame, Monsieur, je souhaite vivement rejoindre votre équipe…")
            a.created_at = datetime.utcnow() - timedelta(days=random.randint(0, 20))
    db.session.commit()
    # quelques décisions déjà prises
    from .modeles import Application
    apps = Application.query.all()
    for a in apps[:6]:
        a.status = random.choice(["interview", "shortlisted", "second_chance"])
        a.decided_at = a.created_at + timedelta(days=random.randint(1, 4))
        if a.status == "second_chance":
            a.feedback = scores.refusal_feedback(a)
            db.session.add(TalentPool(company_id=a.job.company_id, candidate_id=a.candidate_id, source_job_id=a.job_id, note=a.ai_reason or ""))
    db.session.commit()

    # --- suivi des candidatures (JAT) : synchronisation + exemples externes
    from .modeles import MobilityProject, CVVersion, TrackedApplication
    from .services import suivi as tsvc
    for a in Application.query.all():
        tsvc.sync_application(a)
    db.session.commit()
    aicha = cands[0]
    p_abj = MobilityProject(user_id=aicha.id, name="Abidjan", country_code="CI", city="Abidjan", target_role="Data Analyst", color="#D86730")
    p_qc = MobilityProject(user_id=aicha.id, name="Québec 2027", country_code="CA", city="Québec", target_role="Analyste BI", color="#2B6CB0")
    db.session.add_all([p_abj, p_qc])
    db.session.flush()
    v1 = CVVersion(user_id=aicha.id, name="CV Data Analyst — Abidjan", data={})
    v2 = CVVersion(user_id=aicha.id, name="CV Analyste BI — format canadien", data={"template": "ca_classique"})
    db.session.add_all([v1, v2])
    db.session.flush()
    for tr in TrackedApplication.query.filter_by(user_id=aicha.id).all():
        tr.project_id = p_abj.id
    today = datetime.utcnow().date()
    ext = [
        ("Analyste BI", "Desjardins", "Lévis", "CA", "LinkedIn", "sent", 12, p_qc, v2, "Marie Tremblay", "Conseillère en acquisition de talents"),
        ("Data Analyst junior", "Ville de Québec", "Québec", "CA", "Guichet-Emplois", "interview", 20, p_qc, v2, "Julie Gagnon", "RH"),
        ("Analyste de données", "Intact Assurance", "Québec", "CA", "Indeed", "to_apply", 0, p_qc, None, "", ""),
        ("Business Analyst", "MTN Côte d'Ivoire", "Abidjan", "CI", "Emploi.ci", "waiting", 9, p_abj, v1, "Koné Ibrahim", "Talent Acquisition"),
        ("Data Engineer", "Société Générale CI", "Abidjan", "CI", "Site carrière", "identified", 0, p_abj, None, "", ""),
        ("Analyste reporting", "SIB", "Abidjan", "CI", "LinkedIn", "refused", 30, p_abj, v1, "", ""),
    ]
    for title, company, city, cc, source, stage, ago, proj, ver, cname, crole in ext:
        tr = TrackedApplication(user_id=aicha.id, title=title, company=company, city=city, country_code=cc, source=source,
                                stage="identified", project_id=proj.id, cv_version_id=ver.id if ver else None,
                                contact_name=cname, contact_role=crole, url="https://example.com/offre",
                                deadline=today + timedelta(days=random.randint(2, 20)) if stage in ("identified", "to_apply") else None,
                                created_at=datetime.utcnow() - timedelta(days=ago + 3))
        db.session.add(tr)
        db.session.flush()
        tsvc.add_event(tr, "stage", "Ajoutée au suivi", at=datetime.utcnow() - timedelta(days=ago + 3))
        if stage != "identified":
            tsvc.set_stage(tr, stage)
            if tr.applied_at:
                tr.applied_at = today - timedelta(days=ago)
                tr.next_followup = tr.applied_at + timedelta(days=7) if stage in ("sent", "waiting") else tr.next_followup
        if stage == "interview":
            tsvc.add_event(tr, "call", "Appel de Julie Gagnon : entretien Teams prévu jeudi 10 h (heure de Québec).")
    db.session.commit()

    # --- paiements
    plan_c = Plan.query.filter_by(role="candidate", active=True).first()
    plan_r = Plan.query.filter_by(role="recruiter", active=True).first()
    for u in [c for c in cands if c.access_granted][:5]:
        db.session.add(Payment(user_id=u.id, plan_id=plan_c.id, amount=plan_c.price, currency="XOF", method=random.choice(["wave", "orange_money", "mtn_momo"]),
                               reference=f"TX{random.randint(100000, 999999)}", status="confirmed", validated_at=datetime.utcnow()))
    for r in recs:
        db.session.add(Payment(user_id=r.id, plan_id=plan_r.id, amount=plan_r.price, currency="XOF", method="bank",
                               reference=f"VIR{random.randint(1000, 9999)}", status="confirmed", validated_at=datetime.utcnow()))
    for u in [c for c in cands if not c.access_granted][:2]:
        db.session.add(Payment(user_id=u.id, plan_id=plan_c.id, amount=plan_c.price, currency="XOF", method="wave",
                               reference=f"WV{random.randint(100000, 999999)}", status="pending"))
    db.session.commit()
