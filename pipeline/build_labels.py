"""Phase 3b: flood labels at (district, day) resolution.

Rules (documented in README):
  onset     : start day of an event whose span <= RELIABLE_MAX_SPAN days  -> label 1
  ongoing   : later days of such an event                                  -> excluded
  ambiguous : every day of events longer than RELIABLE_MAX_SPAN days       -> excluded
  (days not listed here are normal days, label 0)
Precedence when a day qualifies for several: onset > ongoing > ambiguous.
"""
import json
from pathlib import Path
import pandas as pd

OUT = Path("data/processed")
RELIABLE_MAX_SPAN = 14
N_DISTRICTS, N_DAYS = 106, 8766

ep = pd.read_parquet(OUT / "flood_events_district.parquet")
ep["span"] = (ep["end_date"] - ep["start_date"]).dt.days + 1

rel = ep[ep["span"] <= RELIABLE_MAX_SPAN]
amb = ep[ep["span"] > RELIABLE_MAX_SPAN]

onset = (rel[["district_id", "start_date"]].drop_duplicates()
         .rename(columns={"start_date": "date"}))
onset["label_status"] = "onset"


def expand(df, status, skip_first):
    rows = []
    for r in df.itertuples():
        start = r.start_date + pd.Timedelta(days=1 if skip_first else 0)
        if start > r.end_date:
            continue
        for d in pd.date_range(start, r.end_date, freq="D"):
            rows.append((r.district_id, d))
    out = pd.DataFrame(rows, columns=["district_id", "date"]).drop_duplicates()
    out["label_status"] = status
    return out


ongoing = expand(rel, "ongoing", True)
ambiguous = expand(amb, "ambiguous", False)

labels = (pd.concat([onset, ongoing, ambiguous], ignore_index=True)
            .drop_duplicates(["district_id", "date"], keep="first"))
labels.to_parquet(OUT / "flood_labels.parquet", index=False)

counts = labels["label_status"].value_counts().to_dict()
total = N_DISTRICTS * N_DAYS
usable = total - counts.get("ongoing", 0) - counts.get("ambiguous", 0)
report = {
    "reliable_max_span_days": RELIABLE_MAX_SPAN,
    "pairs_reliable": int(len(rel)), "pairs_ambiguous": int(len(amb)),
    "label_rows": {k: int(v) for k, v in counts.items()},
    "district_days_total": total,
    "district_days_usable_for_ml": int(usable),
    "positive_rate_pct_of_usable": round(100 * counts.get("onset", 0) / usable, 3),
}
json.dump(report, open(OUT / "label_report.json", "w"), indent=2)
print(json.dumps(report, indent=2))

labels["year"] = labels["date"].dt.year
print("\nLabel rows per year:")
print(pd.crosstab(labels["year"], labels["label_status"]).to_string())
