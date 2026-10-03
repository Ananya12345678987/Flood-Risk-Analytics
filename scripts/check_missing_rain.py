import sys; sys.path.insert(0, ".")
import pandas as pd
m = pd.read_csv("data/processed/cell_district.csv")
r = pd.read_parquet("data/processed/rainfall_district_daily",
                    columns=["district_id"]).drop_duplicates()
have = set(r.district_id)
miss = m[~m.district_id.isin(have)][["state", "district", "assignment", "lat", "lon"]]
print("Districts with NO rainfall series:", miss.district_id.nunique() if "district_id" in miss else len(miss))
print(miss.to_string(index=False))
pilot = set(pd.read_csv("data/processed/districts_pilot.csv").district_id)
print("\nPILOT districts missing rainfall:", sorted(pilot - have) or "none")
