"""Exporte les données du tableau de bord Power BI au format CSV.

Usage :
    python ml/exporter_powerbi.py              # activité de la base + emploi dans le monde
    python ml/exporter_powerbi.py --sans-monde # sans télécharger les indicateurs mondiaux

Les fichiers sont écrits dans le dossier powerbi/ (séparateur « ; », UTF-8 avec BOM).
Ils sont anonymisés : aucun nom, e-mail ni téléphone (chaque personne est un numéro).

Page « L'emploi dans le monde » : monde_pays, monde_indicateurs, monde_derniere_valeur,
monde_definitions (Banque mondiale / OIT, téléchargés automatiquement).
Page « Activité de TalentConnect » : activite_quotidienne, activite_evenements,
activite_chiffres_cles + les fichiers détaillés (utilisateurs, offres, candidatures…).
Pages déjà existantes : etudes_entrainement, equite_modeles (modèles d'IA).

Astuce : sur le site en ligne, l'administrateur peut aussi télécharger ces fichiers
(Administration > Power BI) ou relier Power BI directement au site par un lien secret.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "powerbi")


def ecrire(nom, contenu):
    with open(os.path.join(OUT, nom), "wb") as f:
        f.write(contenu)


def main():
    from app import create_app
    from app.services import powerbi
    os.makedirs(OUT, exist_ok=True)
    avec_monde = "--sans-monde" not in sys.argv
    app = create_app()
    with app.app_context():
        print(f"Export vers {OUT}")
        sorties = powerbi.fichiers_activite()
        if avec_monde:
            print("Téléchargement des indicateurs de l'emploi (Banque mondiale / OIT)…")
            try:
                sorties.update(powerbi.fichiers_monde(forcer=True))
            except Exception as exc:
                print(f"  ⚠ Indicateurs mondiaux non téléchargés ({exc}) : les anciens fichiers monde_*.csv sont gardés.")
        sorties.update(powerbi.fichiers_modeles())
        for nom, (entete, lignes) in sorted(sorties.items()):
            ecrire(nom, powerbi.en_csv(entete, lignes))
            print(f"  {nom:30s} {len(lignes):7d} lignes")
    print("✓ Terminé. Dans Power BI : Accueil > Actualiser (ou Obtenir des données > Texte/CSV, délimiteur point-virgule).")


if __name__ == "__main__":
    main()
