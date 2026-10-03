"""Phase 3c: IMD grid -> (a) cell->district mapping, (b) cell-level daily rainfall Parquet.

Cells whose centre lies inside a district polygon belong to that district.
Districts too small to contain any cell centre get the nearest cell (flagged
assignment='nearest_cell_fallback'); such a cell may then serve two districts.
Covers ALL 2011 districts (India-wide rainfall); weather/river stay pilot-only.
"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
import geopandas as gpd
import imdlib as imd
from pipeline.district_names import norm

RAW_SHP = "data/raw/boundaries/datameet/maps-master/Districts/Census_2011/2011_Dist.shp"
OUT = Path("data/processed")
CELLS = OUT / "rain_cells"
CELLS.mkdir(parents=True, exist_ok=True)
YEARS = range(2000, 2024)


def slug(s):
    return norm(s).replace(" ", "_")


def load_year(y):
    return imd.open_data("rain", y, y, "yearwise", "data/raw/imd").get_xarray()


ds0 = load_year(2023)
lat, lon = ds0["lat"].values, ds0["lon"].values
step = float(lat[1] - lat[0])
print(f"grid: {len(lat)} lat x {len(lon)} lon, step {step}")

g = gpd.read_file(RAW_SHP)
g["geometry"] = g.geometry.buffer(0)
g["district_id"] = g["ST_NM"].map(slug) + "__" + g["DISTRICT"].map(slug)
dup = g["district_id"].duplicated(keep=False)
g.loc[dup, "district_id"] = g.loc[dup, "district_id"] + "__" + g.loc[dup, "censuscode"].astype(str)
print("districts:", len(g), "| ids made unique via census code:", int(dup.sum()))

LON, LAT = np.meshgrid(lon, lat)
ilat, ilon = np.meshgrid(np.arange(len(lat)), np.arange(len(lon)), indexing="ij")
pts = pd.DataFrame({"ilat": ilat.ravel(), "ilon": ilon.ravel(),
                    "lat": LAT.ravel(), "lon": LON.ravel()})
pts["cell_id"] = pts.ilat * 1000 + pts.ilon
pg = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts.lon, pts.lat), crs=4326)

j = gpd.sjoin(pg, g[["district_id", "ST_NM", "DISTRICT", "geometry"]], how="inner", predicate="within")
j = j.drop_duplicates("cell_id")          # a point exactly on a border can match twice
m = j[["cell_id", "ilat", "ilon", "lat", "lon", "district_id", "ST_NM", "DISTRICT"]].copy()
m["assignment"] = "cell_centre_inside"

missing = g[~g["district_id"].isin(m["district_id"])]
rows = []
for r in missing.itertuples():
    p = r.geometry.representative_point()
    a = int(np.clip(round((p.y - lat[0]) / step), 0, len(lat) - 1))
    b = int(np.clip(round((p.x - lon[0]) / step), 0, len(lon) - 1))
    rows.append(dict(cell_id=a * 1000 + b, ilat=a, ilon=b, lat=lat[a], lon=lon[b],
                     district_id=r.district_id, ST_NM=r.ST_NM, DISTRICT=r.DISTRICT,
                     assignment="nearest_cell_fallback"))
if rows:
    m = pd.concat([m, pd.DataFrame(rows)], ignore_index=True)
m = m.rename(columns={"ST_NM": "state", "DISTRICT": "district"})
m.to_csv(OUT / "cell_district.csv", index=False)

cells = m.drop_duplicates("cell_id").sort_values("cell_id")
ci_lat, ci_lon, ci_id = cells.ilat.values, cells.ilon.values, cells.cell_id.values
print("cells kept:", len(cells), "| mapping rows:", len(m), "| fallback districts:", len(rows))

pilot_ids = set(pd.read_csv(OUT / "districts_pilot.csv")["district_id"])
per = m.groupby("district_id").size()
pp = per[per.index.isin(pilot_ids)]
print("cells per PILOT district  min/median/max:", pp.min(), pp.median(), pp.max())
print("pilot districts with <=2 cells:", sorted(pp[pp <= 2].index.tolist()))
print("fallback districts:", [r["district_id"] for r in rows])

stats = {}
t0 = time.time()
for y in YEARS:
    ds = ds0 if y == 2023 else load_year(y)
    arr = ds["rain"].transpose("time", "lat", "lon").values
    vals = arr[:, ci_lat, ci_lon].astype("float32")
    vals[vals < 0] = np.nan                       # IMD missing-value sentinel
    times = pd.to_datetime(ds["time"].values).strftime("%Y-%m-%d").values
    T, N = vals.shape
    df = pd.DataFrame({"date": np.repeat(times, N), "cell_id": np.tile(ci_id, T),
                       "rain_mm": vals.ravel()})
    n_nan = int(df["rain_mm"].isna().sum())
    df = df.dropna(subset=["rain_mm"])
    d = CELLS / f"year={y}"
    d.mkdir(exist_ok=True)
    df.to_parquet(d / "part-0.parquet", index=False)
    stats[y] = dict(rows=int(len(df)), nan_dropped=n_nan)
    print(f"{y}: {len(df):>9} rows written, {n_nan} NaN dropped ({time.time()-t0:.0f}s)", flush=True)

json.dump(dict(cells=int(len(cells)), districts=int(len(g)), fallback=[r["district_id"] for r in rows],
               years=stats), open(OUT / "rain_cells_report.json", "w"), indent=2)
print("total cell-day rows:", sum(v["rows"] for v in stats.values()))
