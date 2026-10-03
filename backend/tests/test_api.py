"""API tests. The data below is a SYNTHETIC TEST FIXTURE (never used by the app or shown in the UI);
it only checks that endpoints, warning logic and error handling behave correctly."""
import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app

DATES = pd.date_range("2023-06-01", "2023-06-30")


def _district(did, state, tier, last_high):
    n = len(DATES)
    river = tier in ("minor", "major")
    df = pd.DataFrame({
        "district_id": did, "state": state, "date": DATES, "label_status": "normal", "flood_onset": 0,
        "ml_usable": True, "rain_1d_mm": np.linspace(1, 20, n), "rain_3d_mm": np.linspace(3, 60, n),
        "rain_7d_mm": np.linspace(7, 140, n), "rain_30d_mm": np.linspace(30, 300, n),
        "rain_7d_anomaly_z": np.linspace(0, 1.5, n), "temp_c": 27.0, "humidity_pct": 80.0,
        "pressure_kpa": 100.0, "wind_ms": 2.0,
        "discharge_m3s": np.linspace(10, 30, n) if river else np.nan,
        "discharge_ratio_to_median": np.linspace(1, 2, n) if river else np.nan,
        "discharge_change_3d_pct": 0.1 if river else np.nan,
        "discharge_above_p95": 0.0 if river else np.nan, "river_tier": tier,
        "onsets_prev_3y": 1.0, "elev_mean_m": 40.0, "risk_score": np.linspace(30, 60, n),
        "risk_class": "LOW", "ml_prob": 0.002, "ml_class": "LOW",
        "c_rain": 50.0, "c_river": 50.0 if river else np.nan, "c_history": 50.0, "c_geography": 60.0, "c_weather": 50.0})
    if last_high:
        i = df.index[-1]
        df.loc[i, ["rain_3d_mm", "c_rain", "rain_7d_anomaly_z", "risk_score", "discharge_ratio_to_median",
                   "discharge_above_p95", "onsets_prev_3y", "c_geography"]] = [210.0, 99.0, 3.2, 95.0, 6.0, 1.0, 4.0, 90.0]
        df.loc[i, ["risk_class", "ml_class"]] = ["HIGH", "HIGH"]
    return df


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp("proc")
    (root / "serving").mkdir()
    d = pd.concat([_district("assam__a", "Assam", "major", True), _district("assam__b", "Assam", "none", False),
                   _district("kerala__c", "Kerala", "minor", False)], ignore_index=True)
    d.to_parquet(root / "serving" / "daily.parquet", index=False)
    pd.DataFrame({"district_id": ["assam__a", "assam__b", "kerala__c"], "state": ["Assam", "Assam", "Kerala"],
                  "district": ["Alpha", "Beta", "Gamma"], "area_km2": [10.0, 20.0, 30.0]}).to_csv(root / "districts_pilot.csv", index=False)
    json.dump({"date_min": "2023-06-01", "date_max": "2023-06-30", "default_as_of": "2023-06-30", "base_onset_rate_pct": 0.5,
               "class_stats": {"score": {"HIGH": {"days": 100, "onsets": 4, "onset_rate_pct": 4.0, "lift": 8.0}}, "ml": {}}},
              open(root / "serving" / "meta.json", "w"))
    w = {"rain": 0.3, "river": 0.26, "history": 0.19, "geography": 0.0, "weather": 0.25}
    json.dump({"weights_5": w, "weights_4": {**w, "river": 0.0, "rain": 0.56}}, open(root / "risk_config.json", "w"))
    return TestClient(create_app(root))


def test_health_ok(client):
    assert client.get("/api/health").json() == {"status": "ok", "data_loaded": True, "error": None}


def test_regions_and_meta(client):
    states = {s["state"] for s in client.get("/api/regions").json()["states"]}
    assert states == {"Assam", "Kerala"}
    assert "HISTORICAL REPLAY" in client.get("/api/meta").json()["mode"]


def test_summary_is_valid_json_without_nan(client):
    r = client.get("/api/summary", params={"state": "Assam"})
    assert r.status_code == 200
    j = r.json()
    assert j["rain_total"]["value"] > 0 and j["risk"]["risk_class"] == "HIGH"


def test_warning_is_dynamic_and_explained(client):
    j = client.get("/api/warning", params={"district": "assam__a", "date": "2023-06-30"}).json()
    assert j["level"] == "HIGH RISK"
    text = " ".join(j["reasons"])
    assert "210 mm" in text and "95th percentile" in text and "historical comparison" in text
    assert abs(sum(c["percent"] for c in j["contributions"]) - 100) < 0.5


def test_normal_day_has_no_alarm(client):
    j = client.get("/api/warning", params={"district": "assam__b", "date": "2023-06-10"}).json()
    assert j["level"] == "NORMAL"


def test_district_without_river_returns_null_river(client):
    rows = client.get("/api/timeseries", params={"district": "assam__b"}).json()["rows"]
    assert rows and all(r["discharge_m3s"] is None for r in rows)
    assert client.get("/api/summary", params={"district": "assam__b"}).json()["river_available"] is False


def test_map_and_history(client):
    m = client.get("/api/map", params={"date": "2023-06-30"}).json()["rows"]
    assert {r["district"] for r in m} == {"Alpha", "Beta", "Gamma"}
    h = client.get("/api/warnings/history", params={"state": "Assam"}).json()["rows"]
    assert h and h[0]["level"] == "HIGH RISK"


def test_bad_inputs(client):
    assert client.get("/api/summary", params={"district": "nope"}).status_code == 404
    assert client.get("/api/summary", params={"start": "2023-06-20", "end": "2023-06-10"}).status_code == 400


def test_missing_data_does_not_crash(tmp_path):
    c = TestClient(create_app(tmp_path))
    h = c.get("/api/health").json()
    assert h["status"] == "degraded" and h["data_loaded"] is False
    assert c.get("/api/summary").status_code == 503
