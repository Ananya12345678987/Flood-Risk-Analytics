import os, time
import imdlib as imd

D = "data/raw/imd/rain"
good = os.path.getsize(f"{D}/2023.grd")          # known-good 365-day file
per_day = good / 365
print(f"per-day size derived from 2023: {per_day:.0f} bytes\n")

def days(y):
    return 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365

def ok(y):
    p = f"{D}/{y}.grd"
    return os.path.exists(p) and abs(os.path.getsize(p) - per_day * days(y)) < 1

for y in range(2000, 2024):
    p = f"{D}/{y}.grd"
    if os.path.exists(p) and not ok(y):
        print(f"{y}: wrong size ({os.path.getsize(p)} bytes) -> deleting")
        os.remove(p)

for y in range(2000, 2024):
    if ok(y):
        continue
    for attempt in range(1, 6):
        try:
            imd.get_data("rain", y, y, fn_format="yearwise", file_dir="data/raw/imd")
            if ok(y):
                print(f"{y}: OK on attempt {attempt}", flush=True)
                break
            print(f"{y}: downloaded but size wrong -> retrying", flush=True)
            os.remove(p) if os.path.exists(f"{D}/{y}.grd") else None
        except Exception as e:
            print(f"{y}: attempt {attempt} failed: {type(e).__name__}", flush=True)
        time.sleep(10 * attempt)

print("\nFINAL CHECK")
bad = [y for y in range(2000, 2024) if not ok(y)]
for y in range(2000, 2024):
    s = os.path.getsize(f"{D}/{y}.grd") if os.path.exists(f"{D}/{y}.grd") else 0
    print(f"  {y}  {s:>10} bytes  {'OK' if ok(y) else 'BAD'}")
print("\nBad years:", bad or "none")
