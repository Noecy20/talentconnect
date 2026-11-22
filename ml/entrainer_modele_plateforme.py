"""Entraîne le modèle « chance d'être appelé » à partir des vraies candidatures.

Étiquette : 1 si la candidature a atteint entretien / offre / embauche, 0 si refusée.
Caractéristiques (même ordre que app.ia.scores.call_features) :
    match, sponsorship, completeness, competition, response_rate

Usage :
    python ml/entrainer_modele_plateforme.py                 # données de la base TalentConnect
    python ml/entrainer_modele_plateforme.py --csv extra.csv # + données externes (mêmes colonnes + label)

Le modèle est enregistré dans instance/modeles/modele_plateforme.joblib et utilisé
automatiquement par l'app (redémarrage nécessaire). Tant qu'il n'existe pas,
l'app utilise la formule logistique calibrée à la main.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score

FEATURES = ["match", "sponsorship", "completeness", "competition", "response_rate"]


def from_database():
    from app import create_app
    from app.modeles import Application
    from app.ia.scores import call_features
    app = create_app()
    X, y = [], []
    with app.app_context():
        for a in Application.query.filter(Application.status.in_(["interview", "offer", "hired", "rejected"])).all():
            f = call_features(a.candidate, a.job, a.match_score)
            X.append([f[k] for k in FEATURES])
            y.append(1 if a.status in ("interview", "offer", "hired") else 0)
    return X, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="CSV externe avec colonnes " + ",".join(FEATURES) + ",label")
    ap.add_argument("--min", type=int, default=200, help="nombre minimum d'exemples")
    args = ap.parse_args()
    X, y = from_database()
    if args.csv:
        import csv
        with open(args.csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                X.append([float(row[k]) for k in FEATURES])
                y.append(int(row["label"]))
    print(f"{len(X)} exemples, {sum(y)} positifs")
    if len(X) < args.min or len(set(y)) < 2:
        print(f"⚠ Pas assez de données (minimum {args.min}, deux classes). On garde la formule par défaut.")
        return
    X, y = np.array(X), np.array(y)
    best, best_score = None, -1
    for name, model in [("logistic", LogisticRegression(max_iter=1000)), ("gboost", GradientBoostingClassifier())]:
        score = cross_val_score(model, X, y, cv=5, scoring="roc_auc").mean()
        print(f"{name}: AUC = {score:.3f}")
        if score > best_score:
            best, best_score = model, score
    best.fit(X, y)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance", "modeles")
    os.makedirs(out, exist_ok=True)
    joblib.dump(best, os.path.join(out, "modele_plateforme.joblib"))
    print(f"✓ Modèle enregistré (AUC {best_score:.3f})")


if __name__ == "__main__":
    main()
