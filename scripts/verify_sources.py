import time
import requests

results = []

def check(name, fn):
    t = time.time()
    try:
        status, msg = "OK", fn()
    except Exception as e:
        status, msg = "FAIL", f"{type(e).__name__}: {str(e)[:200]}"
    results.append((name, status))
    print(f"[{status}] {name}: {msg} ({time.time()-t:.1f}s)\n")

def get(url, params):
    r = requests.get(url, params=params, timeout=90)
    r.raise_for_status()
    return r.json()

def nasa_power():
    j = get("https://power.larc.nasa.gov/api/temporal/daily/point", dict(
        parameters="T2M,RH2M,PS,WS2M,PRECTOTCORR", community="AG",
        longitude=77.59, latitude=12.97, start="20240701", end="20240710", format="JSON"))
    p = j["properties"]["parameter"]
    first = {k: list(v.values())[0] for k, v in p.items()}
    return f"{len(p['T2M'])} days; first-day values {first}"

def om_archive():
    j = get("https://archive-api.open-meteo.com/v1/archive", dict(
        latitude=12.97, longitude=77.59, start_date="2024-07-01", end_date="2024-07-10",
        daily="temperature_2m_mean,precipitation_sum", timezone="Asia/Kolkata"))
    d = j["daily"]
    return f"{len(d['time'])} days; temp[0]={d['temperature_2m_mean'][0]}, rain[0]={d['precipitation_sum'][0]}"

def om_flood(lat, lon):
    def run():
        j = get("https://flood-api.open-meteo.com/v1/flood", dict(
            latitude=lat, longitude=lon, daily="river_discharge",
            start_date="2020-07-01", end_date="2020-07-10"))
        v = j["daily"]["river_discharge"]
        nn = [x for x in v if x is not None]
        return f"{len(nn)}/{len(v)} non-null values; sample={v[:3]}"
    return run

def om_elevation():
    j = get("https://api.open-meteo.com/v1/elevation", dict(latitude=12.97, longitude=77.59))
    return f"elevation response: {j}"

def imd_rain():
    import imdlib as imd
    imd.get_data("rain", 2023, 2023, fn_format="yearwise", file_dir="data/raw/imd")
    data = imd.open_data("rain", 2023, 2023, "yearwise", "data/raw/imd")
    ds = data.get_xarray()
    return f"dims={dict(ds.sizes)}; vars={list(ds.data_vars)}"

check("NASA POWER daily weather (Bengaluru)", nasa_power)
check("Open-Meteo ERA5 archive (Bengaluru)", om_archive)
check("Open-Meteo flood API on Brahmaputra (Guwahati)", om_flood(26.18, 91.75))
check("Open-Meteo flood API in desert (Jaisalmer) - expect null/low", om_flood(26.9, 70.9))
check("Open-Meteo elevation", om_elevation)
check("IMD gridded rainfall 2023 via imdlib (~25 MB)", imd_rain)

print("SUMMARY")
for n, s in results:
    print(f"  {s:4}  {n}")
