# TalentConnect

> **Connectez les talents aux entreprises.** C'est la suite de **CVFlash** : du CV compatible ATS jusqu'à l'embauche, avec la confiance des parrainages.

L'application est écrite en Flask avec PostgreSQL. Elle est multilingue (FR / EN / ES / PT, et extensible), internationale (pays, devises, villes) et utilise un design terracotta.

---

## 1. Lancer le projet sur Windows

**Prérequis :** Python 3.11 ou plus récent, et PostgreSQL (facultatif pour un premier test).

Dans le terminal de VS Code, ouvert dans le dossier TalentConnect :

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python run.py
```

L'app s'ouvre sur **http://localhost:5000**. Les fois suivantes, seules `.\venv\Scripts\Activate.ps1` et `python run.py` sont nécessaires.

Sans `DATABASE_URL`, l'app utilise une base SQLite locale, ce qui suffit pour tester tout de suite.

**Avec PostgreSQL :**

1. Créez la base : `createdb talentconnect` (ou passez par pgAdmin).
2. Dans `.env`, renseignez `DATABASE_URL=postgresql://postgres:VOTRE_MDP@localhost:5432/talentconnect`.
3. Relancez. Les tables sont créées automatiquement : les migrations sont appliquées au démarrage.

**Données de démonstration** (12 candidats, 6 entreprises, 16 offres, des parrainages, des paiements) :

```bat
flask --app run.py seed-demo
```

| Rôle | E-mail | Mot de passe |
|---|---|---|
| Admin | `admin@talentconnect.app` | la valeur de `ADMIN_PASSWORD` dans `.env` (`ChangezMoi123!` par défaut). Pour le changer : `flask --app run.py create-admin admin@talentconnect.app NouveauMotDePasse` |
| Candidate | `aicha.kone@demo.tc` | `Demo1234!` |
| Recruteur | `awa.traore@demo.tc` (Orange CI) | `Demo1234!` |
| Parrain | `kouadio.nguessan@demo.tc` | `Demo1234!` |

---

## 2. Les fonctionnalités

### Candidat

- **CV Builder CVFlash**, gratuit : les modèles d'origine (format français, canadien, ATS) avec export PDF. Le CV se synchronise avec le profil : compétences, langues et résumé sont repris automatiquement.
- **Offres pour moi** : les filtres sont pré-remplis selon le profil (filière, pays). On peut ensuite filtrer par entreprise, ville, poste, filière, contrat et niveau d'études.
- **Score de compatibilité** et **chance d'être appelé**, avec le détail par critère et des conseils pour progresser.
- **Lettre de motivation générée** à partir du profil et de l'offre.
- **Suivi des candidatures** comme un suivi de colis. En cas de refus, un **retour constructif** est fourni.
- **Parrainages** :
  - un lien unique, à partager par e-mail ou WhatsApp ;
  - un **passeport de compétences** (✓n = nombre de parrains qui confirment chaque compétence).
- **Orientation RIASEC** : 30 questions et les matières préférées donnent des filières, des métiers et les offres ouvertes correspondantes.
- **Score d'employabilité** avec des actions concrètes, chacune avec son gain estimé.
- **Carte des métiers qui recrutent** : par pays, ville, filière et compétences demandées.
- **Assistant IA personnel (RAG)** : le candidat l'alimente (textes, FAQ, PDF, profil, CV). Les recruteurs peuvent l'interroger.

### Recruteur

- Fiche entreprise, avec vérification RCCM par l'admin.
- Publication d'offres. **La devise suit le pays.**
- **Accusé de réception automatique** pour chaque candidature.
- **Tri IA** en 3 groupes (entretien, seconde chance, refus), avec la justification pour chaque candidat. Le recruteur ajuste d'un clic, puis **envoie toutes les réponses d'un coup**. Les messages partent par e-mail (Brevo) et restent visibles dans l'app.
- **Pipeline kanban** par glisser-déposer.
- **Recherche de talents** par compétences, soft skills, filière, lieu, niveau d'études, expérience, et avec un filtre « parrainés uniquement ».
- **Fiche candidat** : parrainages détaillés, passeport de compétences, chat avec l'assistant IA du candidat, et signalement d'un parrainage douteux.
- **Vivier « seconde chance »** : ces candidats sont reproposés automatiquement sur les nouvelles offres.
- **Modèles de messages** personnalisables.
- **Taux de réponse public** de l'entreprise, affiché aux candidats.

### Parrain (une personne ou une entreprise entière)

- **Test d'éligibilité** noté sur 100 : niveau du poste, expérience, études, e-mail professionnel au domaine de l'entreprise, LinkedIn, équipe encadrée, etc.
  - À partir de 75 : certifié automatiquement.
  - Entre 60 et 74 : revue par l'admin.
  - En dessous de 60 : refus.
- **Niveaux** Or (85 et plus), Argent (70 et plus) et Bronze.
- **Recommandation structurée** : relation, période, notes de 1 à 5 étoiles par compétence, texte, et « je le réembaucherais ».
- **Réputation** :
  - elle augmente de 5 quand un filleul est embauché ;
  - elle baisse de 10 si un recruteur signale un parrainage douteux.
- Maximum de 10 parrainages par an (réglable).

### Admin

- Tableau de bord : inscrits par rôle, accès payants, revenus, inscriptions sur 30 jours, répartition par pays.
- **Utilisateurs et accès** : donner l'accès (30 j, 90 j, 1 an ou illimité), le retirer, désactiver un compte.
- **Paiements** : valider ou refuser les paiements déclarés (Wave, Orange Money, MTN, Moov, carte, virement), ou enregistrer un paiement manuel. L'accès est activé automatiquement à la validation.
- **Formules et prix** fixés par l'admin, ainsi que les instructions de paiement.
- **Parrains** : revue des dossiers et des signalements. **Entreprises** : vérification.
- **Réglages des modèles** : seuils de parrainage et de tri, pondération du score de compatibilité.

> **Paywall** : tant que l'admin n'a pas donné l'accès (directement ou via un paiement validé), un candidat ou un recruteur ne voit que le CV Builder et son profil. Les parrains et les admins y ont accès gratuitement.

---

### Suivi des candidatures (Job Application Tracking)

Menu **Mon suivi**, côté candidat. Il centralise toute la recherche d'emploi, sur TalentConnect comme ailleurs.

- **Kanban** à 11 étapes (Offre identifiée → À analyser → À postuler → Candidature préparée → Candidature envoyée → En attente → Entretien → Test technique → Offre reçue → Acceptée / Refusée), par glisser-déposer.
- **Vue tableau** : filtres (projet, étape, source, recherche), tri (date, date limite, entreprise…) et **export CSV** (Excel).
- **Ajout d'une offre** de trois façons :
  - par **lien** : l'annonce est lue automatiquement grâce au format standard JobPosting. Pour LinkedIn, le lien est enregistré et on complète à la main ;
  - par **saisie manuelle** ;
  - depuis les **offres externes** (voir plus bas) ou les offres TalentConnect.
- **Synchronisation automatique** : une candidature envoyée sur TalentConnect apparaît dans le suivi, et chaque décision du recruteur fait avancer la carte.
- **Par candidature** : entreprise, poste, lieu, rémunération, contrat, lien, source, date limite, contact RH (nom, fonction, e-mail, téléphone), **version de CV** ou fichier joint, **lettre de motivation** (générable), notes et priorité.
- **Historique des échanges** : notes, e-mails, appels, rendez-vous, entretiens, relances et changements d'étape.
- **Relances** : un rappel est posé automatiquement 7 jours après l'envoi, avec un bouton « J'ai relancé ». La commande `flask --app run.py send-reminders` envoie chaque matin les relances du jour par e-mail ; sur Render, planifiez-la dans un *Cron Job*.
- **Statistiques** : candidatures envoyées, réponses reçues, entretiens obtenus, taux de réponse, offres acceptées.
- **Projets de mobilité** (par exemple Abidjan et Québec 2027), chacun avec ses candidatures, sa couleur et ses statistiques.
- **Versions de CV** : dans le CV Builder, le bouton « Enregistrer comme version » permet d'associer la bonne version à chaque candidature.

### Offres externes en temps réel (sans scraping)

LinkedIn interdit le scraping dans ses conditions d'utilisation et poursuit les sociétés qui le pratiquent. TalentConnect passe donc par des **API officielles**, activées dès que la clé est dans `.env` :

| Fournisseur | Variable(s) | Couverture |
|---|---|---|
| JSearch (RapidAPI) | `JSEARCH_API_KEY` | Google for Jobs : annonces publiées sur LinkedIn, Indeed, Glassdoor, sites carrière… |
| Adzuna | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | France, Canada, Royaume-Uni, États-Unis… |
| Jooble | `JOOBLE_API_KEY` | Très large, international |

Vérifiez les tarifs et quotas de chaque fournisseur avant la mise en production.

### Vérification des recruteurs

Pour publier une offre, un recruteur doit prouver qu'il travaille dans l'entreprise. Deux méthodes sont possibles :

1. **E-mail professionnel** : un code est envoyé à son adresse. Si le domaine correspond au site de l'entreprise, la validation est automatique.
2. **Justificatif** (attestation employeur, badge, contrat, mandat de recrutement), vérifié par l'admin dans *Recruteurs à vérifier*.

Le badge « Recruteur vérifié » s'affiche ensuite sur ses offres. Les recruteurs déjà inscrits avant cette mise à jour apparaissent comme « Non vérifiés » : l'admin peut les valider en un clic.

---

## 3. Les modèles d'intelligence

Tous les modèles sont dans `app/services/`. Ils fonctionnent sans aucun service payant.

| Modèle | Fichier | Principe |
|---|---|---|
| Éligibilité parrain | `scoring.py` | Barème sur 100, seuils réglables par l'admin |
| Compatibilité candidat ↔ offre | `scoring.py` | 7 critères pondérés (compétences, filière, expérience, études, lieu, soft skills, langues). Rapprochement approximatif des compétences (accents, fautes) et bonus pour les compétences confirmées par un parrain |
| Chance d'être appelé | `scoring.py` | Régression logistique sur 5 variables (compatibilité, force des parrainages, complétude du profil, concurrence, taux de réponse de l'entreprise). Elle est **remplacée automatiquement par un modèle entraîné** dès que `instance/models/call_model.joblib` existe |
| Tri des candidatures | `scoring.py` | Seuils + raisons (points forts et manques) |
| Retour constructif | `scoring.py`, `hiring.py` | Règles, rédigées par Claude si une clé API est configurée |
| Orientation | `orientation.py` | Modèle de Holland (RIASEC) + matières. Enrichissable avec O*NET |
| Assistant (RAG) | `rag.py` | TF-IDF multilingue (n-grammes de caractères) + Claude si une clé est configurée, sinon réponse par extraction |

### Entraîner avec de vraies données

```bat
python ml\train_call_model.py                  :: à partir des candidatures de l'app (200 décisions minimum)
python ml\train_call_model.py --csv data.csv   :: + données externes
```

Sources de données gratuites :

- **O*NET** (onetcenter.org) : métiers, compétences et profils RIASEC. Importer avec `python ml\import_onet.py dossier_onet\` : l'orientation propose alors des centaines de métiers.
- **ESCO** (esco.ec.europa.eu) : la taxonomie européenne des compétences en FR, EN, ES et PT. Importer avec `python ml\import_esco_skills.py skills_fr.csv fr`, ce qui ajoute l'autocomplétion des compétences.
- **Kaggle** : « LinkedIn Job Postings », « Resume Dataset », pour l'analyse de marché et les tests du matching.

> Le meilleur modèle viendra de **vos propres données** : chaque décision des recruteurs (entretien ou refus) sert d'exemple d'entraînement.

### Activer l'IA générative (facultatif)

Ajoutez `ANTHROPIC_API_KEY=...` dans `.env`. Cela améliore :

- l'assistant, qui rédige de vraies réponses ;
- les lettres de motivation ;
- les retours de refus ;
- la traduction automatique (`flask translate de` crée l'allemand, par exemple).

---

## 4. E-mails avec Brevo (gratuit)

1. Créez un compte sur brevo.com, puis allez dans **SMTP & API** et ouvrez l'onglet **SMTP**.
2. Copiez le *login* et générez une *clé SMTP*.
3. Dans `.env`, renseignez `MAIL_USERNAME=<login>`, `MAIL_PASSWORD=<clé SMTP>` et `MAIL_SENDER=TalentConnect <adresse@domaine-validé>`.
4. Dans Brevo, validez l'expéditeur (ou le domaine).

Sans configuration, les messages restent visibles dans l'app (« dans l'app ») mais ne partent pas par e-mail.

---

## 5. Langues, pays et devises

- Les textes sont en français dans le code. Chaque langue a son fichier `app/translations/<code>.json`.
- Pour ajouter une langue, créez le fichier (ou lancez `flask translate <code>` avec une clé IA). Elle apparaît automatiquement dans le sélecteur.
- Les **pays** sont traduits automatiquement (Babel). La **devise suit le pays** (CI → F CFA, FR → €, CA → $ CA…). Les **villes** sont proposées selon le pays (GeoNames).

---

## 6. Mise en ligne (pour remplacer cvflash.netlify.app)

Netlify n'héberge que des sites statiques. **Il ne peut pas faire tourner Flask avec PostgreSQL.** Voici la méthode recommandée.

1. Poussez la branche sur GitHub (voir la section 7).
2. Sur **render.com**, cliquez sur *New*, puis *Blueprint*, et choisissez le repo. Le fichier `render.yaml` crée l'app et la base PostgreSQL.
3. Renseignez les variables `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `MAIL_*` et `ANTHROPIC_API_KEY`.
4. **Pour garder le lien CVFlash partagé sur LinkedIn**, CVFlash a été déployé sur Netlify sans repo (glisser-déposer). Redirigez-le ainsi :
   - créez un dossier contenant votre `index.html` CVFlash et un fichier `_redirects` (sans extension) avec cette ligne :

     ```
     /*  https://talentconnect.onrender.com/cv  301
     ```

   - dans Netlify, ouvrez le projet **cvflash**, puis **Deploys**, et glissez-déposez ce dossier.

   Les visiteurs de cvflash.netlify.app arrivent alors directement sur le CV Builder de TalentConnect (gratuit, sans compte). Vous pouvez aussi brancher votre propre nom de domaine sur Render.

---

## 7. Git et GitHub (nouveau repo)

CVFlash n'avait pas de repo GitHub : TalentConnect part donc sur un **nouveau repo** nommé `talentconnect`, avec deux branches :

- `main` ;
- `talentconnect`, la branche de travail.

Double-cliquez sur **`git_branche.bat`**.

- **Si GitHub CLI (`gh`) est installé**, le script crée le repo privé et pousse tout automatiquement.
- **Sinon**, il vous guide :
  1. créez un repo vide sur https://github.com/new, nommé `talentconnect`, **sans** cocher « Add a README » ;
  2. collez son URL dans le script ;
  3. le script pousse les deux branches.

Prérequis : Git, à installer depuis https://git-scm.com.

---

## 8. Structure

```
app/
  __init__.py        fabrique Flask, contexte des templates, filtres
  models.py          tous les modèles SQLAlchemy
  blueprints/        main, auth, candidate, recruiter, sponsor, admin, billing, assistant, messages, api
  services/          scoring, hiring, orientation, rag, llm, mailer
  cvbuilder/         CV Builder CVFlash d'origine + intégration
  templates/         Jinja + Tailwind + HTMX + Alpine.js
  static/            CSS (design system), JS, vendor/ (bibliothèques hors-ligne), logo
  translations/      en.json, es.json, pt.json
  data/              données importées (ESCO, O*NET)
migrations/          migrations Alembic (appliquées au démarrage)
ml/                  entraînement et imports de données
```

Pour modifier le design :

1. Lancez `npm install`, puis `npm run css`. Cela recompile Tailwind après l'ajout de nouvelles classes.
2. Les composants (cartes, boutons, chips…) sont dans `app/static/css/app.css`.

---

## 9. Pistes pour la suite

- Paiement en ligne automatique (CinetPay, FedaPay, Stripe) : les modèles `Payment` et `Plan` sont prêts.
- Répertoire des **écoles** par filière, à brancher sur l'orientation.
- Embeddings vectoriels avec **pgvector** pour l'assistant et la recherche sémantique de talents.
- Pitch vidéo de 60 secondes sur le profil candidat.
- Notifications WhatsApp.
