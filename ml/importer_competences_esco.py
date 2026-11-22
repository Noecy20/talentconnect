"""Importe la taxonomie européenne des compétences ESCO (gratuite, multilingue).

1. Télécharger : https://esco.ec.europa.eu/en/use-esco/download  (format CSV, langue fr / en / es / pt)
2. Lancer :  python ml/importer_competences_esco.py chemin/vers/skills_fr.csv fr
Résultat : app/ia/competences_fr.json, utilisé pour l'autocomplétion des compétences.
"""
import csv
import json
import os
import sys


def main(path, lang):
    names = set()
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            label = (row.get("preferredLabel") or "").strip()
            if label and len(label) <= 60 and row.get("skillType", "").startswith(("skill", "knowledge")):
                names.add(label[0].upper() + label[1:])
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "ia", f"competences_{lang}.json")
    json.dump(sorted(names), open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"✓ {len(names)} compétences -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "fr")
