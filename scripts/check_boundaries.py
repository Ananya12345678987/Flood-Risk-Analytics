import re, difflib
import pandas as pd
import geopandas as gpd
pd.set_option("display.width", 200)

PILOT = ["assam", "kerala", "karnataka", "maharashtra"]
FILES = [
    "data/raw/boundaries/datameet/maps-master/Districts/Census_2011/2011_Dist.shp",
    "data/raw/boundaries/datameet/maps-master/Survey-of-India-Index-Maps/Boundaries/India-Districts-2011Census.shp",
]

def norm(s):
    s = str(s).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

ifi = pd.read_csv("data/raw/ifi/India_Flood_Inventory_v3.csv")
ifi.columns = [c.strip() for c in ifi.columns]
ifi["start"] = pd.to_datetime(ifi["Start Date"], dayfirst=True, errors="coerce")
ifi = ifi[(ifi.start.dt.year >= 2000) & (ifi.start.dt.year <= 2023)]
multi = ifi["State"].fillna("").str.contains(",").sum()
print("Multi-state rows (excluded from this check):", multi)
single = ifi[~ifi["State"].fillna("").str.contains(",")].copy()
single["state_n"] = single["State"].fillna("").map(norm)
single["dist"] = single["Districts"].fillna("").str.split(",")
inc = single.explode("dist")
inc["dist_n"] = inc["dist"].map(norm)
inc = inc[inc.dist_n != ""]

def pick(cols, names):
    low = {c.lower(): c for c in cols}
    for n in names:
        if n in low:
            return low[n]
    return None

for f in FILES:
    print("=" * 72)
    print(f.split("/")[-1])
    g = gpd.read_file(f)
    print("rows:", len(g), "| CRS:", g.crs)
    print("columns:", [c for c in g.columns if c != "geometry"])
    print(g.drop(columns="geometry").head(3).to_string())
    dc = pick(g.columns, ["district", "dist_name", "dtname", "name_2", "dist_nm", "districtname", "dt_name"])
    sc = pick(g.columns, ["st_nm", "state", "state_name", "stname", "name_1", "st_name", "stateut"])
    if not dc or not sc:
        print("!! Could not auto-detect district/state columns - paste this output to me.")
        continue
    g["dist_n"] = g[dc].map(norm)
    g["state_n"] = g[sc].map(norm)
    for st in PILOT:
        shp_names = set(g[g.state_n == st].dist_n)
        counts = inc[inc.state_n == st]["dist_n"].value_counts()
        matched = counts[counts.index.isin(shp_names)]
        un = counts[~counts.index.isin(shp_names)]
        pct = 100 * matched.sum() / max(counts.sum(), 1)
        print(f"\n--- {st.title()}: shapefile districts={len(shp_names)}, IFI distinct names={len(counts)}, "
              f"incidences matched={matched.sum()}/{counts.sum()} ({pct:.1f}%)")
        if len(un):
            print("  Unmatched IFI names (count -> closest shapefile name):")
            for name, c in un.head(12).items():
                cm = difflib.get_close_matches(name, list(shp_names), n=1, cutoff=0.7)
                print(f"    {name!r:35} {c:4} -> {cm[0] if cm else '-'}")
        missing = sorted(shp_names - set(counts.index))
        print(f"  Shapefile districts with no matched events: {len(missing)}")
