# Khudaferin — Caspian Sea AI Marine Pollution Platform

Backend monorepo for the **Khudaferin** marine disaster management platform: satellite-driven
oil-spill detection, 30-day hydrodynamic drift forecasts, cleanup priority ranking, oil & gas
risk, and energy-impact analytics over the Caspian Sea.

```
kazakh_backend/
├── KazakhAI_ML_Gemini/   → Deployable FastAPI "Logic API" (web service)
├── pipeline/             → Offline data-engineering CLI (Copernicus satellite ingest)
├── Dockerfile            → Railway image (torch-free, minimal)
├── railway.toml          → Railway service config
├── frontend_integ.md     → Endpoint contract for the frontend team (READ THIS)
└── REMAINING_PROJECT_TASKS.md
```

---

## 1. Prerequisites

- **Python 3.11+** (tested on 3.12/3.13)
- Git

That's it for the API. The ML training stack (`torch`) and the data pipeline (geo-stack)
are optional and only needed for local ML/data work — see sections 4 and 5.

---

## 2. Start the API server (the main thing)

The FastAPI app lives in `KazakhAI_ML_Gemini/`. Its SQLite store auto-seeds from verified
pipeline checkpoints on boot — no manual setup, no external database.

```bash
cd KazakhAI_ML_Gemini

# 1. Create a virtual environment (optional but recommended)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt     # full stack (incl. torch) — local dev
# OR
pip install -r requirements-server.txt   # minimal, torch-free — matches Railway

# 3. Run
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

On startup the server:
1. Creates/opens the SQLite operational store (`data/kazakh_ai.db`).
2. Seeds it from the checkpoints in `src/checkpoints/`.
3. Ingests live Open-Meteo weather (falls back to synthetic offline).
4. Launches a background scheduler that refreshes risk/energy/trend/anomaly stages
   every `REFRESH_INTERVAL_SECONDS` (default `3600`).

### Verify it works

- Health check: `http://localhost:8000/api/v1/health` → `{"server_status": "ONLINE", ...}`
- API index (full route list): `http://localhost:8000/api/v1`
- Swagger UI: `http://localhost:8000/docs`
- Full route smoke test: `python api/app.py`

### Run the full AI-engine verification suite (needs torch)

```bash
cd KazakhAI_ML_Gemini
python verify_ai_engine.py
```

---

## 3. Environment variables (all optional)

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `DATABASE_PATH` | `data/kazakh_ai.db` | Absolute path to the SQLite file. |
| `DATA_DIR` | `data/` | Directory for the SQLite file. |
| `REFRESH_INTERVAL_SECONDS` | `3600` | Background refresh interval. |
| `CORS_ORIGINS` | `*` | Comma-separated frontend origins. |
| `PORT` | `8000` | HTTP port (set automatically by Railway). |

---

## 4. (Optional) ML training / model work

Training the U-Net segmenter or sensor-fusion classifier is **not** part of the web service
and needs `torch` + satellite data. Install the full stack and use the modules directly:

```bash
cd KazakhAI_ML_Gemini
pip install -r requirements.txt
python -m src.models.train          # trains U-Net on the tile dataset
```

> Note: the deployed API does **not** run these models — it serves verified checkpoint
> artifacts. `/api/v1/detect/segment` is a demo probe.

---

## 5. (Optional) Data-engineering pipeline

`pipeline/marine_dataset/` is a standalone CLI that downloads Copernicus Sentinel / weather
data and builds training datasets. It is **not** deployed to Railway. See
`pipeline/marine_dataset/README.md`. Requires Copernicus credentials in
`pipeline/marine_dataset/.env` (copy from `.env.example`).

---

## 6. Deploy to Railway

Connect this repo to Railway — the root `Dockerfile` + `railway.toml` are auto-detected.
The image is intentionally torch-free and small. Recommended settings:

- `CORS_ORIGINS` → your frontend host (e.g. `https://khudaferin.app`)
- For persistent data: add a **Volume**, then `DATABASE_PATH=/data/kazakh_ai.db`
- Healthcheck: Railway pings `GET /api/v1/health`

More detail: `KazakhAI_ML_Gemini/README.md`.

---

## 7. Frontend integration

Read **[`frontend_integ.md`](frontend_integ.md)** — it is the authoritative API contract:
every endpoint, request/response shape, and the frontend checklist (map layers, polling,
error handling). Start with `GET /api/v1` to discover all routes at runtime.

---

## 8. Tests

- API routes: `python api/app.py` (verifies every endpoint returns 200).
- Data pipeline: `cd pipeline/marine_dataset && uv run pytest`.
