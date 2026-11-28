# Tableau de bord Power BI de TalentConnect

Le rapport compte trois pages :

| Page | Question à laquelle elle répond | Fichiers |
|---|---|---|
| 1. L'emploi dans le monde | Quels sont les problèmes de l'emploi, pays par pays ? | `monde_*.csv` |
| 2. Activité de TalentConnect | Comment la plateforme est-elle utilisée, jour après jour ? | `activite_*.csv` + fichiers détaillés |
| 3. Recrutement et IA (existante) | Sur quelles données le modèle a-t-il appris, est-il équitable ? | `etudes_entrainement.csv`, `equite_modeles.csv` |

## 1. Récupérer les données

Deux façons de faire :

- **Lien direct (recommandé)** : sur le site, *Administration > Power BI* donne un lien secret par fichier.
  Dans Power BI Desktop : *Accueil > Obtenir des données > Web*, coller le lien, puis *Charger*.
  Ensuite, *Accueil > Actualiser* récupère les chiffres du jour, sans rien télécharger.
- **Fichiers** : bouton *Tout télécharger (ZIP)* sur la même page, ou sur l'ordinateur :
  `python ml/exporter_powerbi.py` (écrit les fichiers dans le dossier `powerbi/`).
  Dans Power BI : *Obtenir des données > Texte/CSV*.

À l'import : délimiteur **Point-virgule**, origine du fichier **65001 : Unicode (UTF-8)**.

Aucun fichier ne contient de nom, d'e-mail ou de téléphone : chaque personne est un numéro.

## 2. Page « L'emploi dans le monde »

Source : Banque mondiale, *World Development Indicators* (estimations de l'Organisation
internationale du travail, ILOSTAT), tous les pays, de 2010 à aujourd'hui.

| Colonne | Indicateur | Pourquoi c'est un problème de l'emploi |
|---|---|---|
| `chomage` | Taux de chômage (%) | personnes qui cherchent un emploi sans en trouver |
| `chomage_jeunes` | Chômage des 15-24 ans (%) | l'entrée des jeunes sur le marché du travail |
| `neet` | Jeunes sans emploi ni formation (%) | jeunes « décrochés », ni en études, ni en emploi |
| `chomage_diplomes` | Chômage des diplômés du supérieur (%) | « j'ai fini mes études mais je ne trouve pas de travail » |
| `emploi_vulnerable` | Emploi vulnérable (%) | emplois informels, sans contrat ni protection |
| `participation` / `participation_femmes` | Participation au marché du travail (%) | personnes en âge de travailler qui n'y accèdent pas |
| `chomage_femmes`, `chomage_jeunes_femmes` | Chômage des femmes (%) | inégalités femmes / hommes |

### Modèle

- `monde_derniere_valeur` : une ligne par pays avec la dernière valeur connue de chaque indicateur
  (et l'année correspondante, colonne `…_annee`) : idéale pour la carte et les classements.
- `monde_indicateurs` : toutes les années (format long) : pour les courbes d'évolution.
- `monde_pays` : région, niveau de revenu. Relation `monde_pays[code_iso3]` 1 → * `monde_indicateurs[code_iso3]`
  et 1 → 1 `monde_derniere_valeur[code_iso3]`.
- `type` vaut « Pays » ou « Ensemble régional » (Monde, Afrique subsaharienne, Union européenne…) :
  filtrer `type = Pays` sur la carte, garder les ensembles pour comparer.

### Visuels proposés

1. **Segment** (filtre) : région, niveau de revenu ; segment « Indicateur » sur `monde_indicateurs[indicateur]`.
2. **Carte choroplèthe** (*Carte remplie*) : emplacement = `pays` (catégorie de données *Pays/Région*),
   couleur = `chomage_jeunes` (dégradé). Info-bulle : chômage, NEET, emploi vulnérable.
3. **Cartes** (chiffres clés) : Monde, Afrique subsaharienne, Côte d'Ivoire, pour le chômage des jeunes,
   le chômage des diplômés et l'emploi vulnérable.
4. **Histogramme groupé** « Top 15 du chômage des jeunes » (filtre *N premiers* = 15).
5. **Graphique en courbes** : `monde_indicateurs`, axe = `annee`, valeur = `valeur`,
   légende = `pays`, filtré sur Côte d'Ivoire, Sénégal, France, Monde.
6. **Nuage de points** : X = `emploi_vulnerable`, Y = `chomage_jeunes`, taille = `neet`, légende = `region`.
   Il montre que là où le chômage paraît bas, l'emploi est souvent informel.

Mesures DAX utiles :

```DAX
Chômage des jeunes (Monde) =
CALCULATE ( MAX ( monde_derniere_valeur[chomage_jeunes] ), monde_derniere_valeur[code_iso3] = "WLD" )

Écart femmes - ensemble (pts) =
AVERAGE ( monde_derniere_valeur[chomage_femmes] ) - AVERAGE ( monde_derniere_valeur[chomage] )

Valeur moyenne = AVERAGE ( monde_indicateurs[valeur] )
```

## 3. Page « Activité de TalentConnect »

### Modèle

- `activite_quotidienne` : une ligne par jour (aucun jour manquant) : inscriptions par rôle, offres publiées,
  candidatures, entretiens, embauches, messages, paiements validés, montant encaissé, utilisateurs cumulés.
- `activite_evenements` : un événement par ligne (date, type, rôle, pays) : pour filtrer par pays ou par rôle.
- `activite_chiffres_cles` : une seule ligne avec les totaux du jour de l'export.
- Fichiers détaillés : `utilisateurs`, `offres`, `candidatures`, `paiements`, `parrainages`, `candidats`,
  `suivi_candidatures`, `competences_demandees`.
- Créer une table **Calendrier** : `Calendrier = CALENDARAUTO()` puis relier
  `Calendrier[Date]` 1 → * `activite_quotidienne[date]` et `activite_evenements[date]`.

### Visuels proposés

1. **Cartes** : utilisateurs, actifs sur 30 jours, offres ouvertes, candidatures, entretiens,
   taux d'accusé de réception (`activite_chiffres_cles`).
2. **Courbe** : `utilisateurs_cumules` par date (croissance de la plateforme).
3. **Histogramme empilé** par semaine : inscriptions candidats / recruteurs / parrains.
4. **Entonnoir** : candidatures → entretiens → embauches (somme des colonnes de `activite_quotidienne`).
5. **Anneau** : répartition des événements par rôle (`activite_evenements[role]`).
6. **Carte** (bulles) : `activite_evenements[pays]`, taille = nombre d'événements.
7. **Histogramme** : top des compétences demandées (`competences_demandees`).
8. **Courbe** : `montant_encaisse` cumulé (revenus des formules).
9. Segments : période (Calendrier), rôle, pays.

Mesures DAX utiles :

```DAX
Candidatures = SUM ( activite_quotidienne[candidatures] )
Entretiens = SUM ( activite_quotidienne[entretiens] )
Taux d'entretien = DIVIDE ( [Entretiens], [Candidatures] )
Inscriptions = SUM ( activite_quotidienne[inscriptions_candidats] )
             + SUM ( activite_quotidienne[inscriptions_recruteurs] )
             + SUM ( activite_quotidienne[inscriptions_parrains] )
Inscriptions 7 derniers jours =
CALCULATE ( [Inscriptions], DATESINPERIOD ( Calendrier[Date], MAX ( Calendrier[Date] ), -7, DAY ) )
Chiffre d'affaires cumulé =
CALCULATE ( SUM ( activite_quotidienne[montant_encaisse] ),
            FILTER ( ALL ( Calendrier ), Calendrier[Date] <= MAX ( Calendrier[Date] ) ) )
```

Les chiffres de la version de démonstration servent à illustrer le fonctionnement du tableau
de bord ; ils deviendront significatifs avec l'utilisation réelle de la plateforme.
