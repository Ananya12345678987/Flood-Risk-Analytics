"""Merge features + risk scores + events into compact files the API loads.
No Spark is needed at serving time: Spark produced these tables, the API only reads them.

Outputs in data/processed/serving/: daily.parquet, events.parquet, meta.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

P = Path("data/processed")
S = P / "serving"
S.mkdir(exist_ok=True)

FEAT = ["district_id", "state", "date", "label_status", "flood_onset", "ml_usable",
        "rain_1d_mm", "rain_3d_mm", "rain_7d_mm", "rain_30d_mm", "rain_7d_anomaly_z",
        "temp_c", "humidity_pct", "pressure_kpa", "wind_ms",
        "discharge_m3s", "discharge_ratio_to_median", "discharge_change_3d_pct",
        "discharge_above_p95", "river_tier", "onsets_prev_3y", "elev_mean_m"]

f = pd.read_parquet(P / "features_model", columns=FEAT)
f["district_id"] = f["district_id"].astype(str)
f["state"] = f["state"].astype(str)
f["date"] = pd.to_datetime(f["date"])

r = pd.read_parquet(P / "risk_daily.parquet")
r["district_id"] = r["district_id"].astype(str)
r["date"] = pd.to_datetime(r["date"])

d = f.merge(r, on=["district_id", "date"], how="left")
d["risk_class"] = d["risk_class"].where(d["risk_score"].notna())      # no score -> no class
num = d.select_dtypes("float64").columns
d[num] = d[num].astype("float32")
d = d.sort_values(["district_id", "date"]).reset_index(drop=True)
d.to_parquet(S / "daily.parquet", index=False)
print("daily.parquet:", f"{len(d):,} rows,", d.district_id.nunique(), "districts")

# historical onset rate per class (2013-2020 usable days): used in warning explanations
u = d[d["ml_usable"] & d["date"].dt.year.between(2013, 2020)]
base = float(u["flood_onset"].mean())


def stats(col):
    g = u.groupby(col)["flood_onset"].agg(["size", "sum"])
    return {str(k): {"days": int(v["size"]), "onsets": int(v["sum"]),
                     "onset_rate_pct": round(100 * v["sum"] / v["size"], 2),
                     "lift": round((v["sum"] / v["size"]) / base, 1)} for k, v in g.iterrows()}


w = d[d["date"].between("2023-06-01", "2023-09-30")]
n_high = (w["risk_class"] == "HIGH").groupby(w["date"]).sum()
as_of = n_high.idxmax() if n_high.max() > 0 else w["date"].max()
meta = {"date_min": str(d["date"].min().date()), "date_max": str(d["date"].max().date()),
        "default_as_of": str(pd.Timestamp(as_of).date()),
        "base_onset_rate_pct": round(100 * base, 3),
        "class_stats": {"score": stats("risk_class"), "ml": stats("ml_class")}}
json.dump(meta, open(S / "meta.json", "w"), indent=2)
print("meta:", json.dumps({k: v for k, v in meta.items() if k != "class_stats"}))

ev = pd.read_parquet(P / "flood_events_district.parquet")
ev = ev[["event_id", "start_date", "end_date", "state", "district", "district_id",
         "cause_class", "n_districts_in_event"]]
ev.to_parquet(S / "events.parquet", index=False)
print("events.parquet:", len(ev), "event-district rows")
