# Flood Risk Analytics

Big Data Analytics mini-project: flood-risk assessment and early-warning decision support for Assam, Kerala, Karnataka and Maharashtra (2000-2023).

Stack: PySpark, FastAPI, React + Vite + Leaflet, Parquet. Data: IMD gridded rainfall, NASA POWER, GloFAS (via Open-Meteo), India Flood Inventory v3, DataMeet boundaries.

This is a risk indication tool, not a flood forecast. River values are modelled discharge, not gauge readings. The full README is still being written.

Raw and processed data are not stored in this repository. They are produced by the scripts in `pipeline/`, `spark/` and `ml/`.

Run: `uvicorn backend.app.main:app --port 8000` and, in `frontend/`, `npm install` then `npm run dev`.
