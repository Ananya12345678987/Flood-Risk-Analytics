import sys, time
from pathlib import Path
sys.path.insert(0, ".")
import pandas as pd, requests

OUT = Path("data/raw/river"); OUT.mkdir(parents=True, exist_ok=True)
URL = "https://flood-api.open-meteo.com/v1/flood"
d = pd.read_csv("data/processed/districts_pilot.csv")


def fetch(lat, lon):
    for attempt in range(1, 6):
        try:
            r = requests.get(URL, params=dict(latitude=lat, longitude=lon, daily="river_discharge",
                             start_date="2000-01-01", end_date="2023-12-31"), timeout=180)
            j = r.json()
            if r.status_code == 429 or (isinstance(j, dict) and j.get("error")):
                reason = str(j.get("reason", r.status_code))[:150]
                print(f"    API said: {reason}", flush=True)
                if "limit" in reason.lower() or r.status_code == 429:
                    time.sleep(60 * attempt); continue
                return None
            return pd.DataFrame({"date": pd.to_datetime(j["daily"]["time"]),
                                 "discharge_m3s": j["daily"]["river_discharge"]})
        except Exception as e:
            print(f"    attempt {attempt}: {type(e).__name__}: {str(e)[:80]}", flush=True)
            time.sleep(5 * attempt)
    return None


failed = []
for i, r in enumerate(d.itertuples(), 1):
    f = OUT / f"{r.district_id}.parquet"
    if f.exists():
        continue
    df = fetch(r.point_lat, r.point_lon)
    if df is None:
        failed.append(r.district_id); print(f"[{i}/{len(d)}] FAILED {r.district_id}", flush=True); continue
    df.insert(0, "district_id", r.district_id)
    df.to_parquet(f, index=False)
    print(f"[{i}/{len(d)}] {r.district_id}: mean={df.discharge_m3s.mean():.1f} m3/s", flush=True)
    time.sleep(1.0)

rows = []
for f in OUT.glob("*.parquet"):
    x = pd.read_parquet(f); s = x.discharge_m3s
    rows.append(dict(district_id=x.district_id.iloc[0], mean_m3s=s.mean(), median_m3s=s.median(),
                     p95_m3s=s.quantile(0.95), max_m3s=s.max(), pct_null=100 * s.isna().mean()))
sm = pd.DataFrame(rows)
if len(sm):
    sm.to_csv("data/processed/river_summary_raw.csv", index=False)
    print(f"\nDone: {len(sm)}/{len(d)} cached. Failed: {failed or 'none'}")
    print("\nDistribution of long-term mean discharge across districts (m3/s):")
    print(sm.mean_m3s.quantile([0, .1, .25, .5, .75, .9, 1]).round(1).to_string())
    print("\nLowest 8 / highest 8 districts by mean discharge:")
    s2 = sm.sort_values("mean_m3s")
    print(pd.concat([s2.head(8), s2.tail(8)])[["district_id", "mean_m3s", "p95_m3s", "pct_null"]].round(1).to_string(index=False))
