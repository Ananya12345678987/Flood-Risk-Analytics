import sys
sys.path.insert(0, ".")
import difflib
import pandas as pd
import geopandas as gpd
from pipeline.district_names import norm, ALIASES, canonical

PILOT = ["assam", "kerala", "karnataka", "maharashtra"]
g = gpd.read_file("data/raw/boundaries/datameet/maps-master/Districts/Census_2011/2011_Dist.shp")
g["dist_n"] = g["DISTRICT"].map(norm)
g["state_n"] = g["ST_NM"].map(norm)

ifi = pd.read_csv("data/raw/ifi/India_Flood_Inventory_v3.csv")
ifi.columns = [c.strip() for c in ifi.columns]
ifi["start"] = pd.to_datetime(ifi["Start Date"], dayfirst=True, errors="coerce")
ifi = ifi[(ifi.start.dt.year >= 2000) & (ifi.start.dt.year <= 2023)]
single = ifi[~ifi["State"].fillna("").str.contains(",")].copy()
single["state_n"] = single["State"].fillna("").map(norm)
single["dist"] = single["Districts"].fillna("").str.split(",")
inc = single.explode("dist")
inc["dist_n"] = inc["dist"].map(norm)
inc = inc[inc.dist_n != ""].copy()
inc["canon"] = [canonical(s, d) for s, d in zip(inc.state_n, inc.dist_n)]
inc = inc.drop_duplicates(["UEI", "state_n", "canon"])   # one row per event-district pair

for st in PILOT:
    names = set(g[g.state_n == st].dist_n)
    print("=" * 70)
    print(st.upper(), "- shapefile districts:", len(names))
    bad = [(k, v) for k, v in ALIASES.get(st, {}).items() if v not in names]
    if bad:
        print("!! ALIAS TARGETS NOT FOUND IN SHAPEFILE:")
        for k, v in bad:
            sug = difflib.get_close_matches(v, sorted(names), n=3, cutoff=0.5)
            print(f"   {k!r} -> {v!r}   suggestions: {sug}")
    counts = inc[inc.state_n == st]["canon"].value_counts()
    ok = counts[counts.index.isin(names)]
    un = counts[~counts.index.isin(names)]
    print(f"event-district pairs matched: {ok.sum()}/{counts.sum()} ({100*ok.sum()/max(counts.sum(),1):.1f}%)")
    if len(un):
        print("still unmatched (name: count -> closest):")
        for name, c in un.head(25).items():
            cm = difflib.get_close_matches(name, sorted(names), n=1, cutoff=0.7)
            print(f"   {name!r:38} {c:4} -> {cm[0] if cm else '-'}")
    print("shapefile districts with zero events:", sorted(names - set(counts.index)))
    print("shapefile names:", sorted(names))
