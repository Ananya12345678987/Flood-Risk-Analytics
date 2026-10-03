import sys, time
sys.path.insert(0, ".")
import numpy as np, pandas as pd, requests

URL = "https://api.open-meteo.com/v1/elevation"
pil = pd.read_csv("data/processed/districts_pilot.csv")
m = pd.read_csv("data/processed/cell_district.csv")
m = m[m.district_id.isin(set(pil.district_id))][["district_id", "lat", "lon"]].copy()
rep = pil[["district_id", "point_lat", "point_lon"]].rename(columns={"point_lat": "lat", "point_lon": "lon"})
rep["kind"] = "rep"; m["kind"] = "cell"
pts = pd.concat([m, rep], ignore_index=True)
uniq = pts[["lat", "lon"]].round(4).drop_duplicates().reset_index(drop=True)
print("unique points:", len(uniq))

elev = []
for s in range(0, len(uniq), 100):
    b = uniq.iloc[s:s + 100]
    for attempt in range(1, 6):
        try:
            r = requests.get(URL, params=dict(latitude=",".join(map(str, b.lat)),
                             longitude=",".join(map(str, b.lon))), timeout=60)
            r.raise_for_status()
            elev += r.json()["elevation"]; break
        except Exception as e:
            print(f"  batch {s}: attempt {attempt}: {type(e).__name__}", flush=True)
            time.sleep(10 * attempt)
    else:
        sys.exit(f"batch {s} failed - re-run later")
    time.sleep(1)

uniq["elev_m"] = elev
pts["lat"] = pts.lat.round(4); pts["lon"] = pts.lon.round(4)
pts = pts.merge(uniq, on=["lat", "lon"])
cell = pts[pts.kind == "cell"].groupby("district_id").elev_m.agg(
    elev_mean_m="mean", elev_min_m="min", elev_max_m="max", elev_std_m="std", n_samples="count")
cell["relief_m"] = cell.elev_max_m - cell.elev_min_m
repe = pts[pts.kind == "rep"].set_index("district_id").elev_m.rename("elev_rep_point_m")
out = pil[["district_id", "state", "district"]].merge(cell, on="district_id", how="left").merge(repe, on="district_id", how="left")
out = out.round(1)
out.to_csv("data/processed/district_elevation.csv", index=False)
print(out.groupby("state")[["elev_mean_m", "relief_m"]].mean().round(0).to_string())
print("districts without elevation:", int(out.elev_mean_m.isna().sum()))
print(out.sort_values("elev_mean_m").iloc[[0, 1, 2, -3, -2, -1]][["district_id", "elev_mean_m"]].to_string(index=False))
