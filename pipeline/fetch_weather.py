import sys, time
from pathlib import Path
sys.path.insert(0, ".")
import pandas as pd, requests

OUT = Path("data/raw/weather"); OUT.mkdir(parents=True, exist_ok=True)
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
RENAME = {"T2M": "temp_c", "RH2M": "humidity_pct", "PS": "pressure_kpa", "WS2M": "wind_ms"}
d = pd.read_csv("data/processed/districts_pilot.csv")


def fetch(lat, lon, start, end):
    for attempt in range(1, 5):
        try:
            r = requests.get(URL, params=dict(parameters="T2M,RH2M,PS,WS2M", community="AG",
                             longitude=lon, latitude=lat, start=start, end=end, format="JSON"), timeout=180)
            if r.status_code == 429:
                time.sleep(30 * attempt); continue
            r.raise_for_status()
            p = r.json()["properties"]["parameter"]
            df = pd.DataFrame(p)
            df.index = pd.to_datetime(df.index, format="%Y%m%d")
            return df.rename_axis("date").reset_index().replace(-999, float("nan"))
        except Exception as e:
            print(f"    attempt {attempt}: {type(e).__name__}: {str(e)[:80]}", flush=True)
            time.sleep(5 * attempt)
    return None


def fetch_all(lat, lon):
    df = fetch(lat, lon, "20000101", "20231231")
    if df is not None:
        return df
    parts = [fetch(lat, lon, f"{a}0101", f"{b}1231") for a, b in [(2000, 2007), (2008, 2015), (2016, 2023)]]
    return pd.concat(parts) if all(p is not None for p in parts) else None


failed = []
for i, r in enumerate(d.itertuples(), 1):
    f = OUT / f"{r.district_id}.parquet"
    if f.exists():
        continue
    df = fetch_all(r.point_lat, r.point_lon)
    if df is None:
        failed.append(r.district_id); print(f"[{i}/{len(d)}] FAILED {r.district_id}", flush=True); continue
    df = df.rename(columns=RENAME)
    df.insert(0, "district_id", r.district_id)
    df.to_parquet(f, index=False)
    print(f"[{i}/{len(d)}] {r.district_id}: {len(df)} days", flush=True)
    time.sleep(0.5)

files = list(OUT.glob("*.parquet"))
print(f"\nDone: {len(files)}/{len(d)} districts cached. Failed: {failed or 'none'}")
if files:
    al = pd.concat([pd.read_parquet(x) for x in files])
    print("rows:", len(al)); print(al[list(RENAME.values())].describe().round(2).to_string())
