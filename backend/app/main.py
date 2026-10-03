"""FastAPI backend. Start from the project root:  uvicorn backend.app.main:app --port 8000"""
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .store import DISCLAIMER, LEVELS, Store, clean

SOURCES = [
    {"variable": "Rainfall", "source": "IMD gridded daily rainfall, 0.25 deg", "type": "observed (interpolated), aggregated to district"},
    {"variable": "Weather", "source": "NASA POWER daily (~0.5 deg)", "type": "reanalysis (derived); neighbouring districts can share values"},
    {"variable": "River", "source": "GloFAS via Open-Meteo flood API", "type": "MODELLED discharge (m3/s) at one point per district, not a measured gauge level"},
    {"variable": "Flood events", "source": "India Flood Inventory v3, IIT Delhi (Zenodo 10.5281/zenodo.11275211, CC BY 4.0)", "type": "event records; no severity or coordinates; 2021+ recorded differently"},
    {"variable": "Boundaries", "source": "DataMeet district boundaries (Census 2011, CC BY 2.5 India)", "type": "approximate; newer districts attributed to their 2011 parent"},
]
GEO = {"districts": "districts_pilot.geojson", "states": "states.geojson"}


def create_app(data_dir=None):
    store = Store(data_dir)
    app = FastAPI(title="Flood Risk Analytics API", version="1.0",
                  description="Early-warning decision-support. Risk indications, not forecasts.")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET"], allow_headers=["*"])

    def need():
        if store.error:
            raise HTTPException(503, f"Processed data not available ({store.error}). Run the pipeline first.")
        return store

    def check(state, district):
        s = need()
        if district and district not in s.names:
            raise HTTPException(404, f"Unknown district '{district}'")
        if state and state not in set(s.districts.state):
            raise HTTPException(404, f"Unknown state '{state}'")
        return s

    def window(start, end):
        m = need().meta
        lo, hi = pd.Timestamp(m["date_min"]), pd.Timestamp(m["date_max"])
        e = pd.Timestamp(end) if end else pd.Timestamp(m["default_as_of"])
        s = pd.Timestamp(start) if start else e - pd.Timedelta(days=59)
        e, s = min(max(e, lo), hi), min(max(s, lo), hi)
        if s > e:
            raise HTTPException(400, "start must not be after end")
        return s, e

    @app.get("/api/health")
    def health():
        return {"status": "degraded" if store.error else "ok", "data_loaded": store.error is None, "error": store.error}

    @app.get("/api/meta")
    def meta():
        s = need()
        m = s.meta
        return {"date_min": m["date_min"], "date_max": m["date_max"], "default_as_of": m["default_as_of"],
                "default_start": str((pd.Timestamp(m["default_as_of"]) - pd.Timedelta(days=59)).date()),
                "mode": "HISTORICAL REPLAY", "notice": f"Data ends {m['date_max']}. Dates are replayed as if live; this is not real-time.",
                "levels": LEVELS, "sources": SOURCES, "disclaimer": DISCLAIMER,
                "base_onset_rate_pct": m.get("base_onset_rate_pct"), "class_stats": s.class_stats}

    @app.get("/api/regions")
    def regions():
        s = need()
        tiers = s.d.drop_duplicates("district_id").set_index("district_id")["river_tier"].to_dict()
        out = []
        for st, g in s.districts.groupby("state"):
            out.append({"state": st, "districts": [{"id": r.district_id, "name": r.district, "area_km2": r.area_km2,
                                                    "river_tier": tiers.get(r.district_id)} for r in g.sort_values("district").itertuples()]})
        return {"states": out}

    @app.get("/api/summary")
    def summary(state: str | None = None, district: str | None = None, start: str | None = None, end: str | None = None):
        s = check(state, district)
        a, b = window(start, end)
        n = (b - a).days + 1
        cur = s.series(state, district, a, b)
        prev = s.series(state, district, a - pd.Timedelta(days=n), a - pd.Timedelta(days=1))

        def agg(x, col, how):
            return None if x.empty or x[col].notna().sum() == 0 else float(getattr(x[col], how)())

        def chg(c, p):
            return None if c is None or p in (None, 0) else round(100 * (c - p) / p, 1)

        def kpi(col, how, unit):
            c, p = agg(cur, col, how), agg(prev, col, how)
            return {"value": None if c is None else round(c, 2), "previous": None if p is None else round(p, 2),
                    "change_pct": chg(c, p), "unit": unit}

        w = s.warning(state, district, b)
        return {"start": str(a.date()), "end": str(b.date()), "days": n, "scope": district or state or "All pilot states",
                "rain_total": kpi("rain_mm", "sum", "mm"), "river_discharge": kpi("discharge_m3s", "mean", "m3/s (modelled)"),
                "temperature": kpi("temp_c", "mean", "degC"), "humidity": kpi("humidity_pct", "mean", "%"),
                "pressure": kpi("pressure_kpa", "mean", "kPa"), "wind": kpi("wind_ms", "mean", "m/s"),
                "risk": {k: w.get(k) for k in ("risk_score", "risk_class", "ml_class", "level", "driver_district")} if w["available"] else None,
                "river_available": bool(cur["discharge_m3s"].notna().any()) if not cur.empty else False}

    @app.get("/api/timeseries")
    def timeseries(state: str | None = None, district: str | None = None, start: str | None = None,
                   end: str | None = None, freq: str = Query("D", pattern="^[DWM]$")):
        s = check(state, district)
        a, b = window(start, end)
        out = s.series(state, district, a, b, freq)
        return {"freq": freq, "start": str(a.date()), "end": str(b.date()), "rows": clean(out)}

    @app.get("/api/warning")
    def warning(state: str | None = None, district: str | None = None, date: str | None = None):
        s = check(state, district)
        _, b = window(None, date)
        return s.warning(state, district, b)

    @app.get("/api/warnings/history")
    def warning_history(state: str | None = None, district: str | None = None, start: str | None = None,
                        end: str | None = None, limit: int = 60):
        s = check(state, district)
        a, b = window(start, end)
        d = s.sel(state, district, a, b)
        d = d[d["lvl"] >= 2]
        if d.empty:
            return {"rows": []}
        d = d.assign(flag=1)
        g = d.groupby("date", observed=True).agg(level=("lvl", "max"), n_flagged=("flag", "sum")).reset_index()
        g = g.sort_values("date", ascending=False).head(limit)
        top = d.sort_values(["lvl", "risk_score"], ascending=False).drop_duplicates("date").set_index("date")
        g["district"] = [s.names.get(str(top.loc[x, "district_id"])) for x in g["date"]]
        g["risk_score"] = [top.loc[x, "risk_score"] for x in g["date"]]
        g["level"] = [LEVELS[int(x)] for x in g["level"]]
        return {"rows": clean(g)}

    @app.get("/api/map")
    def map_risk(date: str | None = None, level: str = Query("district", pattern="^(district|state)$"),
                 state: str | None = None):
        s = check(state, None)
        _, b = window(None, date)
        d = s.sel(state, None, b, b)
        if d.empty:
            return {"date": str(b.date()), "rows": []}
        d = d.assign(district_id=d["district_id"].astype(str), state=d["state"].astype(str), flag=(d["lvl"] >= 2).astype(int))
        if level == "state":
            g = d.groupby("state").agg(max_score=("risk_score", "max"), mean_score=("risk_score", "mean"),
                                       level=("lvl", "max"), n_districts=("flag", "size"), n_flagged=("flag", "sum")).reset_index()
            g["level"] = [LEVELS[int(x)] for x in g["level"]]
            return {"date": str(b.date()), "level": "state", "rows": clean(g)}
        d["district"] = d["district_id"].map(s.names)
        d["level"] = [LEVELS[int(x)] for x in d["lvl"]]
        cols = ["district_id", "district", "state", "risk_score", "risk_class", "ml_class", "level", "rain_3d_mm", "river_tier"]
        return {"date": str(b.date()), "level": "district", "rows": clean(d[cols])}

    @app.get("/api/floods")
    def floods(state: str | None = None, district: str | None = None, start: str | None = None,
               end: str | None = None, q: str | None = None, limit: int = 300):
        s = check(state, district)
        if s.events is None:
            raise HTTPException(503, "Flood event file not available")
        a, b = window(start, end) if (start or end) else (pd.Timestamp(s.meta["date_min"]), pd.Timestamp(s.meta["date_max"]))
        e = s.events
        e = e[(pd.to_datetime(e["start_date"]) <= b) & (pd.to_datetime(e["end_date"]) >= a)]
        if district:
            e = e[e["district_id"] == district]
        elif state:
            e = e[e["state"] == state]
        if q:
            e = e[e["district"].str.contains(q, case=False, na=False) | e["cause_class"].str.contains(q, case=False, na=False)]
        e = e.sort_values("start_date", ascending=False)
        e = e.assign(duration_days=(pd.to_datetime(e["end_date"]) - pd.to_datetime(e["start_date"])).dt.days + 1)
        return {"total": int(len(e)), "shown": int(min(len(e), limit)),
                "note": "Severity and coordinates are not recorded in this inventory. Events over 14 days are excluded from model training.",
                "rows": clean(e.head(limit))}

    @app.get("/api/floods/frequency")
    def flood_frequency(state: str | None = None, district: str | None = None):
        s = check(state, district)
        d = s.sel(state, district)
        on = d[d["flood_onset"] == 1].groupby(d["date"].dt.year, observed=True).size()
        years = range(int(d["date"].dt.year.min()), int(d["date"].dt.year.max()) + 1)
        return {"rows": [{"year": y, "onsets": int(on.get(y, 0))} for y in years],
                "note": "Counts of district-level onset days. 2021 onward is recorded one district per row, so counts jump."}

    @app.get("/api/model")
    def model():
        s = need()
        m = s.model
        imp = m["importance"]
        return {"metrics": m["metrics"], "weights": (m["config"] or {}),
                "importance": clean(imp.head(15)) if imp is not None else None,
                "ablation": clean(m["ablation"]) if m["ablation"] is not None else None,
                "class_stats": s.class_stats,
                "notes": ["Target is a RECORDED flood onset in the India Flood Inventory, not true flooding.",
                          "Time-based split: fit 2000-2012, tune 2013-2015, test 2016-2020; 2021-2023 reported separately (recording style changed).",
                          "Plain accuracy is misleading (about 99.5% by always predicting no flood). Use PR-AUC, recall and lift.",
                          "Humidity ranks high but probably acts as a wet-regime proxy, so importance is not causation."]}

    @app.get("/api/climatology")
    def climatology(state: str | None = None):
        s = need()
        if s.clim is None:
            raise HTTPException(503, "Climatology file not available")
        c = s.clim if not state else s.clim[s.clim["state"] == state]
        return {"rows": clean(c.groupby("month", as_index=False)["mean_monthly_mm"].mean())}

    @app.get("/api/trends")
    def trends(state: str | None = None):
        s = need()
        if s.trend is None:
            raise HTTPException(503, "Trend file not available")
        t = s.trend if not state else s.trend[s.trend["state"] == state]
        return {"note": "Linear trend of annual rainfall, 2000-2023. Significance is approximate (ignores autocorrelation).",
                "rows": clean(t.sort_values("annual_trend_mm_per_yr", ascending=False))}

    @app.get("/api/geo/{layer}")
    def geo(layer: str):
        if layer not in GEO:
            raise HTTPException(404, "layer must be 'districts' or 'states'")
        p = Path(store.dir) / GEO[layer]
        if not p.exists():
            raise HTTPException(404, f"{GEO[layer]} not found")
        return FileResponse(p, media_type="application/geo+json")

    return app


app = create_app()
