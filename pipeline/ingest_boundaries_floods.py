"""Phase 3a: boundaries + flood-event cleaning.

Outputs (data/processed/):
  states.geojson            all-India state outlines (dissolved from districts, simplified)
  districts_pilot.geojson   pilot-state district polygons (simplified for the web map)
  districts_pilot.csv       district table: id, names, area_km2, representative point
  flood_events_district.parquet   one row per (event, district)
  flood_district_days.parquet     one row per (district, date) flagged flooded
  ingest_report.json        what was kept, dropped, and why
"""
import sys, json
from collections import Counter
from pathlib import Path
sys.path.insert(0, ".")
import pandas as pd
import geopandas as gpd
from pipeline.district_names import norm, resolve

PILOT = ["assam", "kerala", "karnataka", "maharashtra"]
START, END = pd.Timestamp("2000-01-01"), pd.Timestamp("2023-12-31")
RAW_SHP = "data/raw/boundaries/datameet/maps-master/Districts/Census_2011/2011_Dist.shp"
RAW_IFI = "data/raw/ifi/India_Flood_Inventory_v3.csv"
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)
report = {}


def slug(s):
    return norm(s).replace(" ", "_")


# ---------------------------------------------------------------- boundaries
g = gpd.read_file(RAW_SHP)
g["geometry"] = g.geometry.buffer(0)               # repair invalid polygons
g["state_n"] = g["ST_NM"].map(norm)
g["dist_n"] = g["DISTRICT"].map(norm)

states = g.dissolve(by="ST_NM", as_index=False)[["ST_NM", "geometry"]]
states["state_id"] = states["ST_NM"].map(slug)
states["geometry"] = states.geometry.simplify(0.01, preserve_topology=True)
states.to_file(OUT / "states.geojson", driver="GeoJSON")
report["states_in_outline"] = len(states)

pil = g[g.state_n.isin(PILOT)].copy()
proj = pil.to_crs(6933)                              # equal-area CRS for area
pil["area_km2"] = (proj.area / 1e6).round(1)
pt = proj.representative_point().to_crs(4326)        # guaranteed inside the polygon
pil["point_lat"] = pt.y.round(4).values
pil["point_lon"] = pt.x.round(4).values
pil["district_id"] = pil["state_n"].map(slug) + "__" + pil["dist_n"].map(slug)
pil["state"] = pil["ST_NM"]
pil["district"] = pil["DISTRICT"]
dups = pil["district_id"].duplicated().sum()
report["pilot_districts"] = int(len(pil))
report["pilot_duplicate_ids"] = int(dups)
if dups:
    print("WARNING: duplicate district ids:", pil[pil.district_id.duplicated(keep=False)].district_id.tolist())
keep = ["district_id", "state", "district", "area_km2", "point_lat", "point_lon"]
pil[keep].to_csv(OUT / "districts_pilot.csv", index=False)
pil["geometry"] = pil.geometry.simplify(0.005, preserve_topology=True)
pil[keep + ["geometry"]].to_file(OUT / "districts_pilot.geojson", driver="GeoJSON")

# ---------------------------------------------------------------- flood events
df = pd.read_csv(RAW_IFI)
df = df.drop(columns=[c for c in df.columns if c.startswith("Unnamed")])
df.columns = [c.strip() for c in df.columns]
report["ifi_rows_total"] = int(len(df))

df["start"] = pd.to_datetime(df["Start Date"], dayfirst=True, errors="coerce")
df["end"] = pd.to_datetime(df["End Date"], dayfirst=True, errors="coerce")
report["dropped_bad_start_date"] = int(df["start"].isna().sum())
df = df[df["start"].notna()]
df = df[(df.start >= START) & (df.start <= END)].copy()
report["events_in_period"] = int(len(df))
bad_end = df["end"].isna() | (df["end"] < df["start"])
report["end_date_fixed_to_start"] = int(bad_end.sum())
df.loc[bad_end, "end"] = df.loc[bad_end, "start"]
df["span_days"] = (df["end"] - df["start"]).dt.days + 1
report["max_span_days"] = int(df["span_days"].max())
report["events_span_over_60_days"] = int((df["span_days"] > 60).sum())


def cause_class(s):
    t = str(s).lower() if pd.notna(s) else ""
    for key, label in [("cyclone", "cyclone"), ("cloud", "cloudburst"), ("flash", "flash flood"),
                       ("landslide", "landslide"), ("rain", "heavy rain"), ("flood", "flood (cause unspecified)")]:
        if key in t:
            return label
    return "other/unspecified"


df["cause_class"] = df["Main Cause"].map(cause_class)
df["state_n"] = df["State"].fillna("").map(norm)
multi = df["State"].fillna("").str.contains(",")
report["multi_state_rows_excluded_all_india"] = int(multi.sum())
report["multi_state_rows_excluded_touching_pilot"] = int(
    (multi & df["State"].fillna("").map(norm).apply(lambda s: any(p in s for p in PILOT))).sum())
ev = df[(~multi) & df["state_n"].isin(PILOT)].copy()
report["pilot_events"] = int(len(ev))

status_ct = Counter()
unmatched = Counter()
pairs = []
for r in ev.itertuples():
    shp_names = set(pil.loc[pil.state_n == r.state_n, "dist_n"])
    resolved = []
    for piece in str(r.Districts if pd.notna(r.Districts) else "").split(","):
        names, status = resolve(r.state_n, piece, shp_names)
        status_ct[status] += 1
        if status == "unmatched":
            unmatched[(r.state_n, norm(piece))] += 1
        resolved += names
    for n in dict.fromkeys(resolved):
        pairs.append(dict(event_id=r.UEI, state_n=r.state_n, dist_n=n, start_date=r.start, end_date=r.end,
                          cause_class=r.cause_class,
                          event_fatalities=getattr(r, "_14", None)))
report["district_piece_status"] = dict(status_ct)
report["unmatched_examples"] = [f"{s}: {d} (x{c})" for (s, d), c in unmatched.most_common(25)]

ep = pd.DataFrame(pairs)
ep = ep.merge(pil[["district_id", "state_n", "dist_n", "state", "district"]], on=["state_n", "dist_n"], how="left")
ep = ep.drop(columns=["state_n", "dist_n", "event_fatalities"])
ep["n_districts_in_event"] = ep.groupby("event_id")["district_id"].transform("nunique")
ep.to_parquet(OUT / "flood_events_district.parquet", index=False)
report["event_district_pairs"] = int(len(ep))
report["events_with_no_resolved_district"] = int(len(set(ev.UEI) - set(ep.event_id)))

# district-day flood flags
days = []
for r in ep.itertuples():
    for d in pd.date_range(r.start_date, r.end_date, freq="D"):
        days.append((r.district_id, d))
fd = (pd.DataFrame(days, columns=["district_id", "date"])
        .groupby(["district_id", "date"]).size().reset_index(name="n_events"))
fd.to_parquet(OUT / "flood_district_days.parquet", index=False)
report["flooded_district_days"] = int(len(fd))
n_days = (END - START).days + 1
report["pilot_district_days_total"] = int(len(pil) * n_days)
report["flood_day_base_rate_pct"] = round(100 * len(fd) / (len(pil) * n_days), 3)

json.dump(report, open(OUT / "ingest_report.json", "w"), indent=2, default=str)

# ---------------------------------------------------------------- summary
print(json.dumps(report, indent=2, default=str))
fd["year"] = fd["date"].dt.year
print("\nFlooded district-days per year (pilot states):")
print(fd.groupby("year").size().to_string())
print("\nFlooded district-days per state:")
fd2 = fd.merge(pil[["district_id", "state"]], on="district_id")
print(fd2.groupby("state").size().to_string())
print("\nCause classes (event-district pairs):")
print(ep["cause_class"].value_counts().to_string())
