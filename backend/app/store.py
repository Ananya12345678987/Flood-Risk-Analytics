"""Data access + early-warning logic. Reads small precomputed files; no Spark at runtime."""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

LEVELS = ["NORMAL", "WATCH", "ALERT", "HIGH RISK"]
RIVER = ("minor", "major")
FACTORS = {"rain": "Rainfall", "river": "River discharge (modelled)", "history": "Flood history",
           "geography": "Geography (low elevation)", "weather": "Weather (humidity-driven)"}
DISCLAIMER = ("Risk indication from historical patterns, not a forecast and not an official warning. "
              "Follow IMD / CWC / state disaster-management advisories.")


def clean(df, nd=2):
    """DataFrame -> JSON-safe records (NaN -> None, dates -> ISO strings)."""
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d")
    for c in df.select_dtypes("number").columns:
        df[c] = df[c].round(nd)
    df = df.astype(object)
    return df.where(pd.notna(df), None).to_dict("records")


def levels(d):
    """Warning level 0-3 from the analytical class, the ML class and the river signal."""
    s, m = d["risk_class"], d["ml_class"]
    hi = s == "HIGH"
    cond = [hi & ((m == "HIGH") | (d["discharge_above_p95"] == 1)),
            hi | (m == "HIGH"),
            (s == "MEDIUM") | (m == "MEDIUM")]
    return np.select(cond, [3, 2, 1], default=0).astype("int8")


class Store:
    def __init__(self, data_dir=None):
        self.dir = Path(data_dir or os.environ.get("FLOOD_DATA_DIR", "data/processed"))
        self.error = None
        try:
            self._load()
        except Exception as e:  # missing/corrupt data must not crash the server
            self.error = f"{type(e).__name__}: {e}"

    def _json(self, name):
        p = self.dir / name
        return json.load(open(p)) if p.exists() else None

    def _csv(self, *parts):
        p = self.dir.joinpath(*parts)
        return pd.read_csv(p) if p.exists() else None

    def _load(self):
        s = self.dir / "serving"
        d = pd.read_parquet(s / "daily.parquet")
        d["district_id"] = d["district_id"].astype("category")
        d["state"] = d["state"].astype("category")
        d["lvl"] = levels(d)
        self.d = d
        self.districts = pd.read_csv(self.dir / "districts_pilot.csv")
        self.names = dict(zip(self.districts.district_id, self.districts.district))
        self.meta = json.load(open(s / "meta.json"))
        self.class_stats = self.meta.get("class_stats", {})
        ev = s / "events.parquet"
        self.events = pd.read_parquet(ev) if ev.exists() else None
        self.model = {"metrics": self._json("ml_metrics.json"), "config": self._json("risk_config.json"),
                      "importance": self._csv("ml_importance.csv"), "ablation": self._csv("ml_ablation.csv")}
        self.trend = self._csv("analytics", "rain_trend_district.csv")
        self.clim = self._csv("analytics", "rain_climatology_state.csv")
        self.geo = self._csv("district_elevation.csv")

    # ------------------------------------------------------------------ slicing
    def sel(self, state=None, district=None, start=None, end=None):
        d = self.d
        m = np.ones(len(d), bool)
        if district:
            m &= (d["district_id"] == district).to_numpy()
        elif state:
            m &= (d["state"] == state).to_numpy()
        if start is not None:
            m &= (d["date"] >= pd.Timestamp(start)).to_numpy()
        if end is not None:
            m &= (d["date"] <= pd.Timestamp(end)).to_numpy()
        return d[m]

    def series(self, state, district, start, end, freq="D"):
        d = self.sel(state, district, start, end)
        if d.empty:
            return pd.DataFrame()
        d = d.assign(flag=(d["lvl"] >= 2).astype(int))
        g = d.groupby("date", observed=True)
        out = pd.DataFrame({
            "rain_mm": g["rain_1d_mm"].mean(), "rain_max_mm": g["rain_1d_mm"].max(),
            "temp_c": g["temp_c"].mean(), "humidity_pct": g["humidity_pct"].mean(),
            "pressure_kpa": g["pressure_kpa"].mean(), "wind_ms": g["wind_ms"].mean(),
            "risk_score": g["risk_score"].max(), "level": g["lvl"].max(), "n_flagged": g["flag"].sum()})
        rv = d[d["river_tier"].isin(RIVER)]
        if not rv.empty:
            rg = rv.groupby("date", observed=True)
            out["discharge_m3s"] = rg["discharge_m3s"].median()
            out["river_ratio"] = rg["discharge_ratio_to_median"].median()
        else:
            out["discharge_m3s"] = np.nan
            out["river_ratio"] = np.nan
        out["rain_7d_avg_mm"] = out["rain_mm"].rolling(7, min_periods=1).mean()
        if freq in ("W", "M"):
            agg = {c: "mean" for c in out.columns}
            agg.update(rain_mm="sum", rain_max_mm="max", risk_score="max", level="max", n_flagged="max")
            out = out.resample({"W": "W", "M": "MS"}[freq]).agg(agg)
        return out.reset_index()

    # ------------------------------------------------------------------ warning
    def reasons(self, r):
        ok, out = pd.notna, []
        if ok(r["rain_3d_mm"]) and ok(r["c_rain"]) and r["c_rain"] >= 90:
            out.append(f"3-day rainfall of {r['rain_3d_mm']:.0f} mm is higher than {r['c_rain']:.0f}% of days "
                       f"in this district's 2000-2012 record")
        if ok(r["rain_7d_anomaly_z"]) and r["rain_7d_anomaly_z"] >= 2:
            out.append(f"7-day rainfall is {r['rain_7d_anomaly_z']:.1f} standard deviations above normal for the month")
        if r["river_tier"] in RIVER:
            if ok(r["discharge_above_p95"]) and r["discharge_above_p95"] == 1:
                out.append("modelled river discharge is above this district's own 95th percentile")
            elif ok(r["discharge_ratio_to_median"]) and r["discharge_ratio_to_median"] >= 3:
                out.append(f"modelled river discharge is {r['discharge_ratio_to_median']:.1f}x its median")
            if ok(r["discharge_change_3d_pct"]) and r["discharge_change_3d_pct"] >= 0.5:
                out.append(f"modelled discharge rose {100 * r['discharge_change_3d_pct']:.0f}% over 3 days")
        if ok(r["onsets_prev_3y"]) and r["onsets_prev_3y"] >= 3:
            out.append(f"{r['onsets_prev_3y']:.0f} flood onsets were recorded in this district in the previous 3 years")
        if ok(r["c_geography"]) and r["c_geography"] >= 80 and ok(r["elev_mean_m"]):
            out.append(f"low-lying district (mean elevation {r['elev_mean_m']:.0f} m)")
        if ok(r["ml_class"]) and r["ml_class"] in ("MEDIUM", "HIGH"):
            out.append(f"the ML model places these conditions in its {r['ml_class']} group")
        st = self.class_stats.get("score", {}).get(str(r["risk_class"]))
        if st and r["risk_class"] in ("MEDIUM", "HIGH"):
            out.append(f"historical comparison: days in the {r['risk_class']} class had a recorded flood onset "
                       f"{st['onset_rate_pct']}% of the time in 2013-2020 ({st['lift']}x the average day)")
        return out or ["no indicator is currently elevated"]

    def contributions(self, rows):
        cfg = self.model.get("config")
        if not cfg or rows.empty:
            return None
        keys = list(FACTORS)
        C = rows[[f"c_{k}" for k in keys]].to_numpy(float)
        w5 = np.array([cfg["weights_5"][k] for k in keys])
        w4 = np.array([cfg["weights_4"][k] for k in keys])
        W = np.where(~np.isnan(C[:, [1]]), w5, w4)
        pts = np.nan_to_num(C) * W
        tot = pts.sum(1, keepdims=True)
        share = np.divide(pts, tot, out=np.zeros_like(pts), where=tot > 0).mean(0) * 100
        return [{"key": k, "factor": FACTORS[k], "percent": round(float(v), 1)} for k, v in zip(keys, share)]

    def warning(self, state, district, date):
        d = self.sel(state, district, date, date)
        if d.empty:
            return {"available": False, "message": "No data for this date and region."}
        top = d.sort_values(["lvl", "risk_score"], ascending=False)
        r = top.iloc[0]
        did = str(r["district_id"])
        counts = {LEVELS[i]: int((d["lvl"] == i).sum()) for i in range(4)}
        aff = top[top["lvl"] >= 2].head(15)
        return {"available": True, "date": str(pd.Timestamp(date).date()), "level": LEVELS[int(r["lvl"])],
                "driver_district": self.names.get(did, did), "driver_district_id": did, "state": str(r["state"]),
                "risk_score": None if pd.isna(r["risk_score"]) else round(float(r["risk_score"]), 1),
                "risk_class": None if pd.isna(r["risk_class"]) else str(r["risk_class"]),
                "ml_class": None if pd.isna(r["ml_class"]) else str(r["ml_class"]),
                "reasons": self.reasons(r), "contributions": self.contributions(d),
                "districts_in_scope": len(d), "level_counts": counts,
                "affected": [{"district_id": str(x.district_id), "district": self.names.get(str(x.district_id)),
                              "state": str(x.state), "level": LEVELS[int(x.lvl)],
                              "risk_score": round(float(x.risk_score), 1)} for x in aff.itertuples()],
                "disclaimer": DISCLAIMER}
