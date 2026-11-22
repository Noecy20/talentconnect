"""Entraîne le modèle « probabilité d'être contacté » sur des données réelles multi-sources.

Données (ml/donnees/), toutes publiques (CC0 ou usage libre) :
  1. bertrand_mullainathan_2004.csv  — Bertrand & Mullainathan (2004), AER. 4 870 CV.
     https://www.openintro.org/data/index.php?data=resume
  2. phillips_2019_commute_dc.tsv    — Phillips (2019), « Do Low-Wage Employers Discriminate Against
     Applicants with Long Commutes? », Journal of Human Resources. 2 260 candidatures.
     Harvard Dataverse doi:10.7910/DVN/GLE7OM
  3. karachi_it_resume_audit.tsv     — « Resume Audit Data_IT Sector », Karachi (Pakistan). 2 032 candidatures.
     Harvard Dataverse doi:10.7910/DVN/DOM4OS
  5. behaghel_crepon_lebarbanchon_2015.csv — Behaghel, Crépon & Le Barbanchon (2015), AEJ: Applied.
     1 471 candidatures réelles de demandeurs d'emploi en France (Pôle emploi). openICPSR projet 113612.
     Sert à entraîner un second modèle, propre au contexte français (variables différentes).
  4. time_to_degree_2024.tsv         — « Time to Baccalaureate Degree in the Labor Market: Evidence from
     a Field Experiment ». 7 245 candidatures de jeunes diplômés. Harvard Dataverse doi:10.7910/DVN/5QYIR2

Usage :
    pip install -r requirements-ml.txt
    python ml/entrainer_modele_rappel.py

Étapes :
  1. harmonisation des 4 études dans un même jeu de variables (valeurs absentes laissées vides) ;
  2. exclusion des variables sensibles (origine, genre, âge, classe sociale, prénom) ;
  3. comparaison de deux modèles en validation croisée stratifiée (5 plis) ;
  4. évaluation sur un jeu de test (20 %) jamais vu, par étude et globalement ;
  5. test de généralisation « une étude laissée de côté » (entraîné sur 3 études, testé sur la 4e) ;
  6. ré-entraînement final sur toutes les données -> app/ia/modele_rappel.joblib ;
  7. rapport chiffré dans ml/rapport/rapport_entrainement.json.
"""
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.ia.modele_rappel import BASE_FEATURES, FEATURES, FR_FEATURES, MODEL_PATH, SOURCES
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold

DATA = os.path.join(ROOT, "ml", "donnees")
REPORT = os.path.join(ROOT, "ml", "rapport")
SEED = 42
NAN = np.nan

REFERENCES = {
    "bertrand_mullainathan_2004": "Bertrand, M. & Mullainathan, S. (2004). Are Emily and Greg More Employable than "
                                  "Lakisha and Jamal? American Economic Review, 94(4), 991-1013.",
    "phillips_2019": "Phillips, D. C. (2019). Do Low-Wage Employers Discriminate Against Applicants with Long "
                     "Commutes? Journal of Human Resources. Données : Harvard Dataverse, doi:10.7910/DVN/GLE7OM.",
    "karachi_it": "Resume Audit Data_IT Sector (Karachi, Pakistan). Harvard Dataverse, doi:10.7910/DVN/DOM4OS.",
    "time_to_degree": "Time to Baccalaureate Degree in the Labor Market: Evidence from a Field Experiment. "
                      "Harvard Dataverse, doi:10.7910/DVN/5QYIR2.",
}


def _req_years(v):
    m = re.match(r"\s*(\d+(?:\.\d+)?)", str(v))
    if m:
        return float(m.group(1))
    return 1.0 if str(v).strip().lower() in ("some", "yes") else 0.0


def _empty(n):
    return {k: np.full(n, NAN) for k in BASE_FEATURES}


# --------------------------------------------------------------------------- chargement par étude
def load_bertrand():
    d = pd.read_csv(os.path.join(DATA, "bertrand_mullainathan_2004.csv"))
    f = _empty(len(d))
    yrs = d.years_experience.astype(float).clip(upper=35)
    req = d.job_req_min_experience.apply(_req_years)
    f.update({
        "years_experience": yrs.values, "college_degree": d.college_degree.values.astype(float),
        "years_college": d.years_college.clip(0, 4).values.astype(float),
        "computer_skills": d.computer_skills.values.astype(float), "special_skills": d.special_skills.values.astype(float),
        "resume_quality": (d.resume_quality == "high").astype(float).values,
        "req_experience": req.values, "meets_experience": (yrs >= req).astype(float).values,
        "req_education": d.job_req_education.values.astype(float), "req_computer": d.job_req_computer.values.astype(float),
        "req_communication": d.job_req_communication.values.astype(float),
        "req_organization": d.job_req_organization.values.astype(float),
    })
    groups = {"origine (race)": d.race.values, "genre": d.gender.values}
    return pd.DataFrame(f), d.received_callback.values.astype(int), groups


def load_phillips():
    d = pd.read_csv(os.path.join(DATA, "phillips_2019_commute_dc.tsv"), sep="\t")
    f = _empty(len(d))
    f.update({"years_experience": d.work_experience.clip(upper=35).values,
              "distance_km": (d.distance * 1.609).values})          # distance publiée en miles
    groups = {"origine (race)": d.race.values, "genre": d.sex.values}
    return pd.DataFrame(f), d.any_response.values.astype(int), groups


def load_karachi():
    d = pd.read_csv(os.path.join(DATA, "karachi_it_resume_audit.tsv"), sep="\t")
    f = _empty(len(d))
    edu = d.minimumeducation.astype(str).str.lower()
    f.update({
        "req_experience": d.experiencerequirednoofyears.apply(_req_years).values,
        "req_education": edu.str.contains("bachelor|master").astype(float).values,
        "req_computer": np.ones(len(d)),                               # offres du secteur informatique
        "distance_km": pd.to_numeric(d.Distance, errors="coerce").values,
    })
    groups = {"genre": d.gender.values, "classe sociale": d.residential_status.values}
    return pd.DataFrame(f), d.callback1.values.astype(int), groups


def load_time_to_degree():
    d = pd.read_csv(os.path.join(DATA, "time_to_degree_2024.tsv"), sep="\t")
    f = _empty(len(d))
    f.update({"college_degree": np.ones(len(d)), "years_college": np.full(len(d), 4.0)})   # tous diplômés (licence)
    groups = {"genre": np.where(d.woman == 1, "femme", "homme"), "origine (race)": np.where(d.black == 1, "noir", "blanc")}
    return pd.DataFrame(f), d.PositiveResponse.values.astype(int), groups


LOADERS = {"bertrand_mullainathan_2004": load_bertrand, "phillips_2019": load_phillips,
           "karachi_it": load_karachi, "time_to_degree": load_time_to_degree}


def build():
    Xs, ys, srcs, groups = [], [], [], []
    for s in SOURCES:
        X, y, g = LOADERS[s]()
        for s2 in SOURCES:
            X[f"src_{s2}"] = 1.0 if s2 == s else 0.0
        Xs.append(X[FEATURES]); ys.append(y); srcs += [s] * len(y)
        groups.append((s, g, len(y)))
    return pd.concat(Xs, ignore_index=True), np.concatenate(ys), np.array(srcs), groups


def candidates():
    return {
        "Régression logistique": make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                                               LogisticRegression(max_iter=3000, C=0.5)),
        "Gradient boosting (histogrammes)": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05,
                                                                           max_iter=250, l2_regularization=1.0,
                                                                           min_samples_leaf=40, random_state=SEED),
    }


def metrics(y, p):
    return {"auc_roc": round(float(roc_auc_score(y, p)), 4),
            "average_precision": round(float(average_precision_score(y, p)), 4),
            "brier": round(float(brier_score_loss(y, p)), 4), "log_loss": round(float(log_loss(y, p)), 4)}


def within_auc(y, p, src):
    """AUC moyenne à l'intérieur de chaque étude (le vrai pouvoir de classement, hors effet « contexte »)."""
    vals = {s: roc_auc_score(y[src == s], p[src == s]) for s in SOURCES if len(set(y[src == s])) > 1}
    return round(float(np.mean(list(vals.values()))), 4), {k: round(float(v), 4) for k, v in vals.items()}


def main():
    os.makedirs(REPORT, exist_ok=True)
    X, y, src, groups = build()
    print(f"Données : {len(y)} candidatures réelles, {len(SOURCES)} études, taux de réponse positive {y.mean():.2%}")
    for s in SOURCES:
        print(f"   {s:28s} n={int((src == s).sum()):5d}  taux={y[src == s].mean():.2%}")

    strat = np.array([f"{a}_{b}" for a, b in zip(src, y)])
    idx = np.arange(len(y))
    tr, te = train_test_split(idx, test_size=0.2, stratify=strat, random_state=SEED)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)

    results = {}
    for name, model in candidates().items():
        p = cross_val_predict(model, X.values[tr], y[tr], cv=cv.split(X.values[tr], strat[tr]), method="predict_proba")[:, 1]
        w, per = within_auc(y[tr], p, src[tr])
        results[name] = {"global": metrics(y[tr], p), "auc_moyenne_par_etude": w, "auc_par_etude": per}
        print(f"{name:34s} VC : AUC globale {results[name]['global']['auc_roc']}, AUC moyenne par étude {w} {per}")
    best = max(results, key=lambda n: results[n]["auc_moyenne_par_etude"])

    model = candidates()[best].fit(X.values[tr], y[tr])
    p_te = model.predict_proba(X.values[te])[:, 1]
    w_te, per_te = within_auc(y[te], p_te, src[te])
    test = {"global": metrics(y[te], p_te), "auc_moyenne_par_etude": w_te, "auc_par_etude": per_te,
            "brier_reference_sans_modele": round(float(brier_score_loss(y[te], np.full(len(te), y[tr].mean()))), 4)}
    print(f"Retenu : {best} -> test : {test}")

    # Généralisation : une étude laissée de côté
    loso = {}
    for s in SOURCES:
        m = candidates()[best]
        Xtr = X[src != s].drop(columns=[f"src_{s}"]).assign(**{f"src_{s}": 0.0})[FEATURES]
        empty = [c for c in FEATURES if Xtr[c].isna().all()]      # variable jamais mesurée sans cette étude
        Xtr = Xtr.fillna({c: 0.0 for c in empty})
        m.fit(Xtr.values, y[src != s])
        others = [s2 for s2 in SOURCES if s2 != s]
        ps = []
        for o in others:   # contexte inconnu : moyenne sur les autres contextes
            Xo = X[src == s].copy()
            for s2 in SOURCES:
                Xo[f"src_{s2}"] = 1.0 if s2 == o else 0.0
            Xo = Xo.fillna({c: 0.0 for c in empty})
            ps.append(m.predict_proba(Xo[FEATURES].values)[:, 1])
        p = np.mean(ps, axis=0)
        loso[s] = round(float(roc_auc_score(y[src == s], p)), 4) if len(set(y[src == s])) > 1 else None
    print("Une étude laissée de côté (AUC) :", loso)

    # Équité : taux réels vs taux prédits par groupe (variables sensibles non utilisées)
    fairness = {}
    te_set = set(te.tolist())
    offset = 0
    for s, g, n in groups:
        rows = np.arange(offset, offset + n)
        mask = np.array([r in te_set for r in rows])
        sel = rows[mask]
        pmap = dict(zip(te.tolist(), p_te.tolist()))
        for gname, vals in g.items():
            v = np.asarray(vals)[mask]
            fairness.setdefault(s, {})[gname] = {
                str(k): {"taux_reel": round(float(y[sel][v == k].mean()), 4),
                         "taux_predit": round(float(np.mean([pmap[i] for i in sel[v == k]])), 4), "n": int((v == k).sum())}
                for k in sorted(set(map(str, v))) if (v == k).sum() > 0}
        offset += n

    final = candidates()[best].fit(X.values, y)
    importance = {}
    if best == "Régression logistique":
        coefs = final.named_steps["logisticregression"].coef_[0]
        names = list(FEATURES) + [f"{FEATURES[i]}_absent" for i in final.named_steps["simpleimputer"].indicator_.features_]
        importance = {n: round(float(c), 4) for n, c in zip(names, coefs)}
    else:
        from sklearn.inspection import permutation_importance
        r = permutation_importance(final, X.values[te], y[te], scoring="roc_auc", n_repeats=5, random_state=SEED)
        importance = {f: round(float(v), 4) for f, v in zip(FEATURES, r.importances_mean)}

    report = {
        "date_entrainement": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sources": {s: {"reference": REFERENCES[s], "candidatures": int((src == s).sum()),
                        "taux_reponse_positive": round(float(y[src == s].mean()), 4)} for s in SOURCES},
        "observations": int(len(y)), "taux_moyen": round(float(y.mean()), 4),
        "entrainement": int(len(tr)), "test": int(len(te)),
        "variables": FEATURES,
        "variables_exclues": ["prénom", "origine (race)", "genre", "âge", "classe sociale / quartier"],
        "comparaison_validation_croisee": results, "modele_retenu": best, "test_final": test,
        "generalisation_etude_laissee_de_cote": loso, "importance_des_variables": importance, "equite": fairness,
    }
    # Modèle déployé : on compare, sur les mêmes CV de test de Bertrand & Mullainathan (la seule étude qui mesure
    # les compétences et les exigences de l'offre), le modèle multi-sources et un modèle mono-source.
    bm = src == "bertrand_mullainathan_2004"
    tr_b, te_b = tr[bm[tr]], te[bm[te]]
    cols = [c for c in BASE_FEATURES if c != "distance_km"]
    mono = candidates()["Régression logistique"].fit(X[cols].values[tr_b], y[tr_b])
    auc_mono = round(float(roc_auc_score(y[te_b], mono.predict_proba(X[cols].values[te_b])[:, 1])), 4)
    auc_multi = per_te.get("bertrand_mullainathan_2004")
    p_mono = mono.predict_proba(X[cols].values[te_b])[:, 1]
    bm_groups = groups[0][1]          # Bertrand & Mullainathan est la première étude chargée (index 0..n-1)
    equite_mono = {g: {str(k): {"taux_reel": round(float(y[te_b][np.asarray(v)[te_b] == k].mean()), 4),
                                "taux_predit": round(float(p_mono[np.asarray(v)[te_b] == k].mean()), 4),
                                "n": int((np.asarray(v)[te_b] == k).sum())}
                       for k in sorted(set(np.asarray(v)[te_b]))} for g, v in bm_groups.items()}
    if auc_mono >= auc_multi:
        deployed = {"model": candidates()["Régression logistique"].fit(X[cols].values[bm], y[bm]), "features": cols,
                    "sources": ["bertrand_mullainathan_2004"], "name": "Régression logistique (Bertrand & Mullainathan)",
                    "base_rate": float(y[bm].mean())}
    else:
        deployed = {"model": final, "features": FEATURES, "sources": SOURCES, "name": best + " (multi-sources)",
                    "base_rate": float(y.mean())}
    report["modele_deploye"] = {"nom": deployed["name"], "auc_test_bertrand_mono_source": auc_mono,
                                "auc_test_bertrand_multi_sources": auc_multi,
                                "equite_modele_etats_unis": equite_mono,
                                "raison": "Le modèle déployé est celui qui classe le mieux les candidats sur les variables "
                                          "que TalentConnect mesure réellement (compétences, expérience, études, "
                                          "exigences de l'offre)."}
    deployed.update({"metrics": test, "trained_on": list(REFERENCES.values()), "context": "usa"})
    print(f"Modèle États-Unis : {deployed['name']} (AUC Bertrand mono {auc_mono} / multi {auc_multi})")

    # Modèle France (Behaghel, Crépon & Le Barbanchon, 2015)
    fr_model, report["modele_france"] = train_france()
    bundle = {"models": [deployed, fr_model], "base_rate": (deployed["base_rate"] + fr_model["base_rate"]) / 2,
              "name": "Moyenne des modèles États-Unis et France"}
    joblib.dump(bundle, MODEL_PATH)
    report["modele_deploye"]["combinaison"] = ("La probabilité affichée est la moyenne du modèle États-Unis et du modèle "
                                               "France, chacun validé sur ses propres données.")
    json.dump(report, open(os.path.join(REPORT, "rapport_entrainement.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"✓ Modèle : {MODEL_PATH}\n✓ Rapport : {os.path.join(REPORT, 'rapport_entrainement.json')}")


# --------------------------------------------------------------------------- modèle France
FRANCE_REF = ("Behaghel, L., Crépon, B. & Le Barbanchon, T. (2015). Unintended Effects of Anonymous Résumés. "
              "American Economic Journal: Applied Economics, 7(3), 1-27. Données : openICPSR, projet 113612.")


def load_france():
    d = pd.read_csv(os.path.join(DATA, "behaghel_crepon_lebarbanchon_2015.csv"))
    coded = d.codage_cv == 1          # le CV a été évalué par les chercheurs (sinon valeur absente)
    X = pd.DataFrame({
        "fr_education": d.dip_bepcap * 1 + d.dip_bac * 2 + d.dip_bac2 * 3 + d.dip_bac3p * 4,
        "fr_years_experience": d.duree_expro_offre.clip(upper=10),
        "fr_overqualified": d.CV_qualif_sup.where(coded),
        "fr_underqualified": d.CV_qualif_inf.where(coded),
        "fr_adequate_experience": d.CV_experience_3p.where(coded),
        "fr_english": d.langue_anglais, "fr_other_language": d.langue_autres,
        "fr_job_executive": d.cadre, "fr_job_intermediate": d.profint,
        "fr_permanent_contract": d.CDI, "fr_large_firm": d.effent_200plus,
        "fr_resume_good": d.CV_note_7p, "fr_anonymous": d.CVA,
    })[FR_FEATURES].astype(float)
    age = np.where(d.a26m == 1, "moins de 26 ans", np.where(d.a50p == 1, "50 ans et plus", "26-49 ans"))
    groups = {"genre": np.where(d.FEMME == 1, "femme", "homme"),
              "origine immigrée": np.where(d.ORIGINE_IM_12 == 1, "oui", "non"),
              "quartier prioritaire": np.where(d.ZUS_CUCS == 1, "oui", "non"), "âge": age}
    return X, d.ENTRETIEN.astype(int).values, d.ID_OFFRE.values, groups


def train_france():
    X, y, offer, groups = load_france()
    print(f"France : {len(y)} candidatures réelles, {len(set(offer))} offres, taux d'entretien {y.mean():.2%}")
    # Les candidats d'une même offre restent ensemble (entraînement OU test) pour éviter toute fuite.
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(X, y, offer))
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    def fr_candidates():   # échantillon plus petit : régularisation plus forte
        c = candidates()
        c["Régression logistique"].set_params(logisticregression__C=0.05)
        return c

    res = {}
    for name, model in fr_candidates().items():
        p = cross_val_predict(model, X.values[tr], y[tr], cv=cv, groups=offer[tr], method="predict_proba")[:, 1]
        res[name] = metrics(y[tr], p)
        print(f"   {name:34s} VC groupée par offre : {res[name]}")
    best = max(res, key=lambda n: res[n]["auc_roc"])
    m = fr_candidates()[best].fit(X.values[tr], y[tr])
    p_te = m.predict_proba(X.values[te])[:, 1]
    test = metrics(y[te], p_te)
    # Le jeu de test (≈ 300 candidatures) est petit : on ajoute une estimation plus stable,
    # 10 validations croisées groupées par offre répétées sur toutes les données.
    aucs, gains = [], []
    for rep_seed in range(10):
        p = cross_val_predict(fr_candidates()[best], X.values, y, groups=offer, method="predict_proba",
                              cv=StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=rep_seed))[:, 1]
        aucs.append(roc_auc_score(y, p))
        gains.append(brier_score_loss(y, np.full(len(y), y.mean())) - brier_score_loss(y, p))
    repeated = {"auc_moyenne": round(float(np.mean(aucs)), 4), "auc_ecart_type": round(float(np.std(aucs)), 4),
                "gain_brier_moyen_vs_sans_modele": round(float(np.mean(gains)), 5)}
    print(f"   VC répétée (10 x 5 plis) : {repeated}")
    test["brier_reference_sans_modele"] = round(float(brier_score_loss(y[te], np.full(len(te), y[tr].mean()))), 4)
    print(f"   Retenu : {best} -> test : {test}")
    fairness = {g: {k: {"taux_reel": round(float(y[te][np.asarray(v)[te] == k].mean()), 4),
                        "taux_predit": round(float(p_te[np.asarray(v)[te] == k].mean()), 4),
                        "n": int((np.asarray(v)[te] == k).sum())}
                    for k in sorted(set(np.asarray(v)[te]))} for g, v in groups.items()}
    final = fr_candidates()[best].fit(X.values, y)
    importance = {}
    if best == "Régression logistique":
        coefs = final.named_steps["logisticregression"].coef_[0]
        names = list(FR_FEATURES) + [f"{FR_FEATURES[i]}_absent" for i in final.named_steps["simpleimputer"].indicator_.features_]
        importance = {n: round(float(c), 4) for n, c in zip(names, coefs)}
    rep = {"reference": FRANCE_REF, "candidatures": int(len(y)), "offres": int(len(set(offer))),
           "taux_entretien": round(float(y.mean()), 4), "entrainement": int(len(tr)), "test": int(len(te)),
           "variables": FR_FEATURES,
           "variables_exclues": ["genre", "âge", "origine immigrée", "quartier prioritaire", "prénom à consonance musulmane"],
           "comparaison_validation_croisee": res, "modele_retenu": best, "test_final": test,
           "validation_croisee_repetee": repeated, "importance_des_variables": importance, "equite": fairness}
    bundle = {"model": final, "features": FR_FEATURES, "sources": None, "name": f"{best} (France)",
              "base_rate": float(y.mean()), "metrics": test, "trained_on": [FRANCE_REF], "context": "france"}
    return bundle, rep


if __name__ == "__main__":
    main()
