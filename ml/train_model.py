"""Flood-onset ML experiments with a strict time-based split (no leakage).

fit 2000-2012 | tune threshold 2013-2015 | test 2016-2020 | shift check 2021-2023.
Target: recorded flood onset (IFI). Days flagged ongoing/ambiguous are excluded.
"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, ".")
import numpy as np, pandas as pd, joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve, confusion_matrix
from sklearn.inspection import permutation_importance

P = Path("data/processed")
FIT, TUNE, TEST, SHIFT = (2000, 2012), (2013, 2015), (2016, 2020), (2021, 2023)
t0 = time.time()

RAIN = ["rain_1d_mm", "rain_3d_mm", "rain_7d_mm", "rain_30d_mm", "rain_7d_anomaly_z",
        "rain_30d_anomaly_z", "rain_max_cell_mm", "heavy_cell_frac"]
SEASON = ["month_sin", "month_cos"]
WEATHER = ["temp_c", "humidity_pct", "wind_ms", "pressure_change_1d_kpa", "pressure_change_3d_kpa"]
GEO_HIST = ["elev_mean_m", "relief_m", "elev_std_m", "onsets_prev_3y"]
RIVER = ["discharge_ratio_to_median", "discharge_above_p95", "discharge_change_1d_pct", "discharge_change_3d_pct"]
SETS = {"A rain only": RAIN,
        "B + season": RAIN + SEASON,
        "C + weather": RAIN + SEASON + WEATHER,
        "D + geography/history": RAIN + SEASON + WEATHER + GEO_HIST,
        "E + river (full)": RAIN + SEASON + WEATHER + GEO_HIST + RIVER}
FULL = SETS["E + river (full)"]
NO_RIVER = SETS["D + geography/history"]

raw = [c for c in RAIN + WEATHER + GEO_HIST + RIVER if c not in SEASON]
df = pd.read_parquet(P / "features_model",
                     columns=["district_id", "state", "date", "year", "month", "ml_usable", "flood_onset"] + raw)
df["year"] = df["year"].astype(int)
df["district_id"] = df["district_id"].astype(str)
df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
for c in FULL:
    df[c] = df[c].astype("float32")
tiers = pd.read_csv(P / "river_tiers.csv")[["district_id", "river_tier"]]
df = df.merge(tiers, on="district_id", how="left")
print(f"loaded {len(df):,} rows in {time.time()-t0:.0f}s")


def part(rng, only_usable=True):
    m = df["year"].between(*rng)
    return df[m & df["ml_usable"]] if only_usable else df[m]


tr, tu, te, sh = part(FIT), part(TUNE), part(TEST), part(SHIFT)
for name, d in [("fit", tr), ("tune", tu), ("test", te), ("shift", sh)]:
    print(f"{name:6} rows={len(d):>8,} onsets={int(d.flood_onset.sum()):>5} prevalence={100*d.flood_onset.mean():.3f}%")


def hgb():
    return HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, max_depth=5,
                                          min_samples_leaf=100, l2_regularization=1.0, random_state=42)


def scores(y, p):
    return dict(roc_auc=round(roc_auc_score(y, p), 4), pr_auc=round(average_precision_score(y, p), 4),
                prevalence=round(float(y.mean()), 4))


# ---------------------------------------------------------------- baseline + logistic
print("\n--- Baselines ---")
base = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=2000))
base.fit(tr[["rain_3d_mm"]], tr.flood_onset)
print("baseline  3-day rainfall only (logistic) test:", scores(te.flood_onset, base.predict_proba(te[["rain_3d_mm"]])[:, 1]))

logit = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=3000))
logit.fit(tr[NO_RIVER], tr.flood_onset)
lp_te = logit.predict_proba(te[NO_RIVER])[:, 1]
print("logistic  (no river features)   test:", scores(te.flood_onset, lp_te))
print("logistic  shift check 2021-23   :", scores(sh.flood_onset, logit.predict_proba(sh[NO_RIVER])[:, 1]))
coef = pd.DataFrame({"feature": NO_RIVER, "std_coef": logit.named_steps["logisticregression"].coef_[0]})
coef["abs"] = coef.std_coef.abs()
coef = coef.sort_values("abs", ascending=False).drop(columns="abs")
print("\nLogistic standardised coefficients (larger |value| = stronger linear effect):")
print(coef.round(3).to_string(index=False))

# ---------------------------------------------------------------- ablation with gradient boosting
print("\n--- Ablation: gradient boosting, adding feature groups ---")
rows, models = [], {}
for name, cols in SETS.items():
    m = hgb().fit(tr[cols], tr.flood_onset)
    models[name] = m
    s_te = scores(te.flood_onset, m.predict_proba(te[cols])[:, 1])
    s_sh = scores(sh.flood_onset, m.predict_proba(sh[cols])[:, 1])
    rows.append(dict(feature_set=name, n_features=len(cols), test_roc=s_te["roc_auc"], test_pr=s_te["pr_auc"],
                     shift_roc=s_sh["roc_auc"], shift_pr=s_sh["pr_auc"]))
    print(f"{name:24} test ROC={s_te['roc_auc']:.3f} PR={s_te['pr_auc']:.3f} | shift ROC={s_sh['roc_auc']:.3f} PR={s_sh['pr_auc']:.3f}", flush=True)
abl = pd.DataFrame(rows)
abl.to_csv(P / "ml_ablation.csv", index=False)
print(f"(test prevalence {te.flood_onset.mean():.4f}; shift prevalence {sh.flood_onset.mean():.4f}; "
      "PR-AUC of a random guesser equals prevalence)")

# ---------------------------------------------------------------- does river help where rivers exist?
print("\n--- River districts only (tier minor/major), test period ---")
rv = te[te.river_tier.isin(["minor", "major"])]
mD, mE = models["D + geography/history"], models["E + river (full)"]
print("without river features:", scores(rv.flood_onset, mD.predict_proba(rv[NO_RIVER])[:, 1]))
print("with    river features:", scores(rv.flood_onset, mE.predict_proba(rv[FULL])[:, 1]))

# ---------------------------------------------------------------- final model, threshold, confusion matrices
final, fcols = mE, FULL
p_tu = final.predict_proba(tu[fcols])[:, 1]
prec, rec, thr = precision_recall_curve(tu.flood_onset, p_tu)
f1 = 2 * prec[:-1] * rec[:-1] / np.clip(prec[:-1] + rec[:-1], 1e-9, None)
best_thr = float(thr[np.argmax(f1)])
print(f"\nAlert threshold chosen on TUNE years (max F1): {best_thr:.4f}")


def report(d, label):
    p = final.predict_proba(d[fcols])[:, 1]
    y = d.flood_onset.values
    pred = (p >= best_thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred).ravel()
    top = p >= np.quantile(p, 0.95)
    out = dict(**scores(y, p), threshold=best_thr, tp=int(tp), fp=int(fp), fn=int(fn), tn=int(tn),
               precision=round(tp / max(tp + fp, 1), 4), recall=round(tp / max(tp + fn, 1), 4),
               f1=round(2 * tp / max(2 * tp + fp + fn, 1), 4),
               recall_in_top5pct_days=round(float(y[top].sum() / max(y.sum(), 1)), 4),
               accuracy=round((tp + tn) / len(y), 4))
    print(f"\n{label}: {json.dumps(out)}")
    return out


metrics = {"split": dict(fit=FIT, tune=TUNE, test=TEST, shift=SHIFT),
           "test": report(te, "TEST 2016-2020"), "shift": report(sh, "SHIFT CHECK 2021-2023 (different recording style)")}

# ---------------------------------------------------------------- permutation importance (test sample)
print("\n--- Permutation importance (drop in PR-AUC when a feature is shuffled), test sample ---")
smp = te.sample(n=min(120000, len(te)), random_state=7)
pi = permutation_importance(final, smp[fcols], smp.flood_onset, scoring="average_precision",
                            n_repeats=3, random_state=7, n_jobs=2)
imp = pd.DataFrame({"feature": fcols, "importance": pi.importances_mean, "std": pi.importances_std})
imp = imp.sort_values("importance", ascending=False)
imp.to_csv(P / "ml_importance.csv", index=False)
print(imp.round(4).to_string(index=False))

# ---------------------------------------------------------------- save
coef.to_csv(P / "ml_logistic_coef.csv", index=False)
joblib.dump(dict(model=final, features=fcols, threshold=best_thr), "models/hgb_flood.joblib")
joblib.dump(dict(model=logit, features=NO_RIVER), "models/logit_flood.joblib")
df["ml_prob"] = final.predict_proba(df[fcols])[:, 1].astype("float32")
df["split"] = np.select([df.year.between(*FIT), df.year.between(*TUNE), df.year.between(*TEST)],
                        ["fit", "tune", "test"], default="shift")
df[["district_id", "date", "ml_prob", "split", "ml_usable"]].to_parquet(P / "ml_predictions.parquet", index=False)
json.dump(metrics, open(P / "ml_metrics.json", "w"), indent=2, default=str)
print(f"\nsaved models, predictions and metrics. total {time.time()-t0:.0f}s")
