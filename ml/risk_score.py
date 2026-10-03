"""Analytical flood-risk score (data-derived weights) vs ML probability, same split/rows."""
import sys, json
from pathlib import Path
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from scipy.optimize import minimize
from sklearn.metrics import roc_auc_score, average_precision_score

P = Path("data/processed")
FIT_END, TUNE, TEST, SHIFT = 2012, (2013, 2015), (2016, 2020), (2021, 2023)
MED_Q, HIGH_Q = 0.90, 0.98                      # judgement percentiles (tune years)
NAMES = ["rain", "river", "history", "geography", "weather"]

cols = ["district_id", "state", "date", "year", "ml_usable", "label_status", "flood_onset",
        "rain_3d_mm", "humidity_pct", "discharge_ratio_to_median", "onsets_prev_3y", "elev_mean_m"]
df = pd.read_parquet(P / "features_model", columns=cols)
df["year"] = df["year"].astype(int)
df["district_id"] = df["district_id"].astype(str)
pred = pd.read_parquet(P / "ml_predictions.parquet", columns=["district_id", "date", "ml_prob"])
df = df.merge(pred, on=["district_id", "date"], how="left")
df["date"] = pd.to_datetime(df["date"])
print(f"rows {len(df):,}")

fitm = (df.year <= FIT_END) & df.ml_usable


def pct_score(values, ref):
    ref = np.sort(ref[~np.isnan(ref)])
    v = values.astype(float)
    out = np.full(len(v), np.nan)
    ok = ~np.isnan(v)
    lo = np.searchsorted(ref, v[ok], side="left")
    hi = np.searchsorted(ref, v[ok], side="right")
    out[ok] = 100 * (lo + hi) / 2 / len(ref)          # mid-rank percentile (handles many ties)
    return out


def comp(col, sign=1.0):
    x = sign * df[col].values.astype(float)
    return pct_score(x, x[fitm.values])


C = np.column_stack([comp("rain_3d_mm"), comp("discharge_ratio_to_median"), comp("onsets_prev_3y"),
                     comp("elev_mean_m", -1.0), comp("humidity_pct")])


def fit_weights(X, y, l2=1e-3):
    n, k = X.shape

    def f(t):
        w, b = t[:k], t[k]
        z = X @ w + b
        p = 1 / (1 + np.exp(-z))
        loss = np.mean(np.logaddexp(0, z) - y * z) + l2 * np.sum(w ** 2)
        return loss, np.append(X.T @ (p - y) / n + 2 * l2 * w, np.mean(p - y))
    r = minimize(f, np.zeros(k + 1), jac=True, method="L-BFGS-B", bounds=[(0, None)] * k + [(None, None)])
    w = r.x[:k]
    return w / w.sum()


y = df["flood_onset"].values
fit_idx = fitm.values
four = [0, 2, 3, 4]
ok4 = fit_idx & ~np.isnan(C[:, four]).any(axis=1)
ok5 = ok4 & ~np.isnan(C[:, 1])
w4 = fit_weights(C[ok4][:, four] / 100, y[ok4])
w5 = fit_weights(C[ok5] / 100, y[ok5])
print(f"\nweights fitted on {ok4.sum():,} rows (4-component) and {ok5.sum():,} rows (5-component, river districts)")
w4_pad = np.zeros(5); w4_pad[four] = w4
print("5-component weights (river districts):", {n: round(float(v), 3) for n, v in zip(NAMES, w5)})
print("4-component weights (no river data)  :", {n: round(float(v), 3) for n, v in zip(NAMES, w4_pad)})

has_river = ~np.isnan(C[:, 1])
W = np.where(has_river[:, None], w5[None, :], w4_pad[None, :])
avail = ~np.isnan(C)
den = (W * avail).sum(axis=1)
score = np.where(den > 0, np.nansum(C * W, axis=1) / np.where(den > 0, den, 1), np.nan)
df["risk_score"] = score.astype("float32")
for i, n in enumerate(NAMES):
    df[f"c_{n}"] = C[:, i].astype("float32")

usable = df.ml_usable & df.risk_score.notna() & df.ml_prob.notna()
tune = usable & df.year.between(*TUNE)
test = usable & df.year.between(*TEST)
shift = usable & df.year.between(*SHIFT)
cuts_score = [float(df.loc[tune, "risk_score"].quantile(q)) for q in (MED_Q, HIGH_Q)]
cuts_ml = [float(df.loc[tune, "ml_prob"].quantile(q)) for q in (MED_Q, HIGH_Q)]
print(f"\nclass cut-offs from tune years: score MEDIUM>={cuts_score[0]:.1f}, HIGH>={cuts_score[1]:.1f} | "
      f"ML prob MEDIUM>={cuts_ml[0]:.4f}, HIGH>={cuts_ml[1]:.4f}")


def sc(d, col):
    return dict(roc_auc=round(roc_auc_score(d.flood_onset, d[col]), 4),
                pr_auc=round(average_precision_score(d.flood_onset, d[col]), 4),
                prevalence=round(float(d.flood_onset.mean()), 4))


print("\n--- Same rows, two ways of scoring ---")
for nm, m in [("TEST 2016-2020", test), ("SHIFT 2021-2023", shift)]:
    d = df[m]
    print(nm, "| analytical score:", sc(d, "risk_score"), "| ML probability:", sc(d, "ml_prob"))


def klass(v, cuts):
    return np.where(v >= cuts[1], "HIGH", np.where(v >= cuts[0], "MEDIUM", "LOW"))


df["risk_class"] = klass(df.risk_score.values, cuts_score)
df["ml_class"] = klass(df.ml_prob.fillna(0).values, cuts_ml)


def table(d, col, title):
    prev = d.flood_onset.mean()
    g = d.groupby(col).agg(days=("flood_onset", "size"), onsets=("flood_onset", "sum")).reindex(["LOW", "MEDIUM", "HIGH"])
    g["pct_of_days"] = (100 * g.days / g.days.sum()).round(1)
    g["onset_rate_pct"] = (100 * g.onsets / g.days).round(2)
    g["lift_vs_base"] = ((g.onsets / g.days) / prev).round(1)
    g["pct_of_onsets"] = (100 * g.onsets / g.onsets.sum()).round(1)
    print(f"\n{title}  (base onset rate {100*prev:.2f}%)")
    print(g.to_string())


for nm, m in [("TEST 2016-2020", test), ("SHIFT 2021-2023", shift)]:
    table(df[m], "risk_class", f"{nm}: classes from ANALYTICAL SCORE")
    table(df[m], "ml_class", f"{nm}: classes from ML PROBABILITY")

print("\n--- Case studies (qualitative; many of these days were excluded from the test metrics) ---")
for title, mask in [("Kerala 8-20 Aug 2018 (state-wide, max over districts)",
                     (df.state == "Kerala") & df.date.between("2018-08-08", "2018-08-20")),
                    ("Mumbai 24-29 Jul 2005",
                     (df.district_id == "maharashtra__mumbai") & df.date.between("2005-07-24", "2005-07-29"))]:
    g = df[mask].groupby("date").agg(max_score=("risk_score", "max"), max_ml_prob=("ml_prob", "max"),
                                     districts_high=("risk_class", lambda s: int((s == "HIGH").sum())),
                                     max_rain_3d=("rain_3d_mm", "max"),
                                     label=("label_status", lambda s: ",".join(sorted(set(s)))))
    print("\n" + title); print(g.round(3).to_string())

out = df[["district_id", "date", "risk_score", "risk_class", "ml_prob", "ml_class", "c_rain", "c_river",
          "c_history", "c_geography", "c_weather"]]
out.to_parquet(P / "risk_daily.parquet", index=False)
json.dump(dict(weights_5=dict(zip(NAMES, map(float, w5))), weights_4=dict(zip(NAMES, map(float, w4_pad))),
               cuts_score=cuts_score, cuts_ml=cuts_ml, percentiles=[MED_Q, HIGH_Q]),
          open(P / "risk_config.json", "w"), indent=2)
print("\nsaved risk_daily.parquet and risk_config.json")
