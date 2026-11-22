"""Importe les métiers O*NET avec leur profil RIASEC pour enrichir l'orientation.

1. Télécharger la base O*NET (texte) : https://www.onetcenter.org/database.html#individual-files
   fichiers nécessaires : "Occupation Data.txt" et "Interests.txt"
2. Lancer :  python ml/importer_onet.py dossier_onet/
Résultat : app/ia/onet_riasec.json  [{"title":..., "code":"IRC", "scores":{...}}]
L'orientation propose alors aussi les métiers O*NET qui correspondent au code du candidat.
"""
import csv
import json
import os
import sys

LETTERS = {"Realistic": "R", "Investigative": "I", "Artistic": "A", "Social": "S", "Enterprising": "E", "Conventional": "C"}


def main(folder):
    titles = {}
    with open(os.path.join(folder, "Occupation Data.txt"), encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            titles[row["O*NET-SOC Code"]] = row["Title"]
    scores = {}
    with open(os.path.join(folder, "Interests.txt"), encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("Scale ID") == "OI" and row["Element Name"] in LETTERS:
                scores.setdefault(row["O*NET-SOC Code"], {})[LETTERS[row["Element Name"]]] = float(row["Data Value"])
    out = []
    for code, sc in scores.items():
        top = "".join(sorted(sc, key=lambda k: -sc[k])[:3])
        out.append({"title": titles.get(code, code), "code": top, "scores": sc})
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "ia", "onet_riasec.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"✓ {len(out)} métiers -> {path}")


if __name__ == "__main__":
    main(sys.argv[1])
