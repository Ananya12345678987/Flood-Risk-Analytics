import pandas as pd

df = pd.read_csv("data/raw/ifi/India_Flood_Inventory_v3.csv")
df = df.drop(columns=[c for c in df.columns if c.startswith("Unnamed")])
df.columns = [c.strip() for c in df.columns]
df["start"] = pd.to_datetime(df["Start Date"], dayfirst=True, errors="coerce")
df["year"] = df["start"].dt.year

print("Total rows:", len(df))
print("Unparseable start dates:", int(df["start"].isna().sum()))
print("Date range:", df["start"].min(), "->", df["start"].max())
print("Columns:", list(df.columns))

r = df[(df.year >= 2000) & (df.year <= 2023)].copy()
print("\n=== 2000-2023: %d events ===" % len(r))
print("Events per year:\n", r["year"].value_counts().sort_index().to_string())

def pct(s):
    return round(100 * s.notna().mean(), 1)

print("\n% of events with value present:")
for c in ["Districts", "District_LGD_Codes", "Latitude", "Longitude",
          "Severity", "Main Cause", "Human fatality", "Area Affected"]:
    if c in r.columns:
        print(f"  {c:20} {pct(r[c])}%")

print("\nMain Cause:\n", r["Main Cause"].value_counts(dropna=False).head(12).to_string())
print("\nSeverity:\n", r["Severity"].value_counts(dropna=False).head(10).to_string())
src = "Event Source" if "Event Source" in r.columns else None
if src:
    print("\nEvent Source:\n", r[src].value_counts(dropna=False).to_string())

print("\n=== Pilot states (events 2000-2023) ===")
for s in ["Karnataka", "Kerala", "Assam", "Bihar", "Odisha"]:
    sub = r[r["State"].fillna("").str.contains(s)]
    print(f"  {s:10} events={len(sub):4}  with district codes={pct(sub['District_LGD_Codes'])}%")

print("\nSample rows that DO have districts:")
cols = [c for c in ["Start Date", "State", "Districts", "District_LGD_Codes", "Main Cause", "Severity"] if c in r.columns]
print(r[r["District_LGD_Codes"].notna()][cols].head(5).to_string())
