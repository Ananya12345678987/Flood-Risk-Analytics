import pandas as pd
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 80)

df = pd.read_csv("data/raw/ifi/India_Flood_Inventory_v3.csv")
df = df.drop(columns=[c for c in df.columns if c.startswith("Unnamed")])
df.columns = [c.strip() for c in df.columns]
df["start"] = pd.to_datetime(df["Start Date"], dayfirst=True, errors="coerce")
df["year"] = df["start"].dt.year
r = df[(df.year >= 2000) & (df.year <= 2023)].copy()

def uniq(s):
    return {x.strip().lower() for x in str(s).split(",") if x.strip()} if pd.notna(s) else set()

r["n_dist"] = r["Districts"].apply(lambda s: len(uniq(s)))
r["n_state"] = r["State"].apply(lambda s: len(uniq(s)))
r["sev_word"] = r["Main Cause"].fillna("").str.lower().str.contains("severe|moderate|minor|major")

print("=== Per year: events, avg unique districts per event, % severity words in Main Cause")
g = r.groupby("year").agg(events=("UEI", "count"), avg_districts=("n_dist", "mean"),
                          sev_word_pct=("sev_word", lambda x: round(100 * x.mean(), 1)))
g["avg_districts"] = g["avg_districts"].round(2)
print(g.to_string())

print("\n=== 2022: 6 sample rows")
cols = ["Start Date", "End Date", "State", "Districts", "Main Cause", "Human fatality"]
print(r[r.year == 2022][cols].sample(6, random_state=1).to_string())

print("\n=== Events per state, 2000-2023 (multi-state events count once per state)")
r["st_list"] = r["State"].apply(lambda x: sorted(uniq(x)))
print(r.explode("st_list")["st_list"].value_counts().head(20).to_string())

print("\n=== Distinct districts with at least one event (single-state rows only)")
r["dlist"] = r["Districts"].apply(lambda x: sorted(uniq(x)))
one = r[r.n_state == 1].explode("dlist")
print(one.groupby("State")["dlist"].nunique().sort_values(ascending=False).head(15).to_string())
