import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, ".")

OUT = Path("data/processed")
NONE_BELOW, MAJOR_FROM = 1.0, 10.0      # m3/s long-term mean; judgement thresholds, not official


def combine(folder, name, cols):
    files = sorted(Path(folder).glob("*.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[cols]
    df.to_parquet(OUT / name, index=False)
    print(f"{name}: {len(df):,} rows, {df.district_id.nunique()} districts")


combine("data/raw/weather", "weather_daily.parquet",
        ["district_id", "date", "temp_c", "humidity_pct", "pressure_kpa", "wind_ms"])
combine("data/raw/river", "river_daily.parquet", ["district_id", "date", "discharge_m3s"])

lab = pd.read_parquet(OUT / "flood_labels.parquet")
lab["date"] = pd.to_datetime(lab["date"]).dt.strftime("%Y-%m-%d")
lab[["district_id", "date", "label_status"]].to_parquet(OUT / "flood_labels_daily.parquet", index=False)
print("flood_labels_daily.parquet:", len(lab), "rows")


def tier(m):
    if pd.isna(m) or m < NONE_BELOW:
        return "none"
    return "major" if m >= MAJOR_FROM else "minor"


s = pd.read_csv(OUT / "river_summary_raw.csv")
s["river_tier"] = s["mean_m3s"].map(tier)
pil = pd.read_csv(OUT / "districts_pilot.csv")[["district_id", "state"]]
t = pil.merge(s[["district_id", "mean_m3s", "river_tier"]], on="district_id", how="left")
t["river_tier"] = t["river_tier"].fillna("none")
t.to_csv(OUT / "river_tiers.csv", index=False)
print("\nRiver tiers by state (districts):")
print(pd.crosstab(t["state"], t["river_tier"]).to_string())
print("\nMajor-river districts:")
print(t[t.river_tier == "major"].sort_values("mean_m3s", ascending=False)[["district_id", "mean_m3s"]].round(1).to_string(index=False))
