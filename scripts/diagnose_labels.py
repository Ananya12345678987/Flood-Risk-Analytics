import pandas as pd
pd.set_option("display.width", 200)

ep = pd.read_parquet("data/processed/flood_events_district.parquet")
ep["span"] = (ep.end_date - ep.start_date).dt.days + 1
ep["year"] = ep.start_date.dt.year

print("Span (days) distribution over event-district pairs:")
print(ep["span"].describe().round(1).to_string())
print(pd.cut(ep["span"], [0, 1, 3, 7, 14, 30, 60, 400]).value_counts().sort_index().to_string())

print("\nPer start-year: pairs, median span, mean span")
g = ep.groupby("year").agg(pairs=("event_id", "size"), median_span=("span", "median"),
                           mean_span=("span", "mean")).round(1)
print(g.to_string())

print("\nLongest events (by span x districts):")
ev = ep.groupby("event_id").agg(state=("state", "first"), start=("start_date", "first"),
                                end=("end_date", "first"), span=("span", "first"),
                                n_districts=("district_id", "nunique"),
                                cause=("cause_class", "first"))
ev["pair_days"] = ev.span * ev.n_districts
print(ev.sort_values("pair_days", ascending=False).head(12).to_string())

tot = (ep.span).sum()
print(f"\nShare of all pair-days coming from pairs with span > 30 days: "
      f"{100 * ep.loc[ep.span > 30, 'span'].sum() / tot:.1f}%")

N_DAYS = 8766                      # 2000-01-01 .. 2023-12-31
n_dist = ep.district_id.nunique()
total = 106 * N_DAYS
onset = ep[["district_id", "start_date"]].drop_duplicates().shape[0]
rows = []
for _, r in ep.iterrows():
    for d in pd.date_range(r.start_date, periods=min(r.span, 3), freq="D"):
        rows.append((r.district_id, d))
cap3 = len(set(rows))
print(f"\nBase rates over {total} district-days (106 districts x {N_DAYS} days):")
print(f"  full span flagged : {59972} ({100*59972/total:.2f}%)   <- what the script produced")
print(f"  onset day only    : {onset} ({100*onset/total:.3f}%)")
print(f"  onset + 2 days    : {cap3} ({100*cap3/total:.3f}%)")

print("\nOnset district-days per year, per state:")
on = ep[["district_id", "state", "start_date"]].drop_duplicates()
on["year"] = on.start_date.dt.year
print(on.pivot_table(index="year", columns="state", values="district_id", aggfunc="count", fill_value=0).to_string())
