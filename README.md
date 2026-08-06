# Khudaferin — Caspian Sea AI Marine Pollution Platform

Backend monorepo for the **Khudaferin** marine disaster management platform: satellite-driven
oil-spill detection, 30-day hydrodynamic drift forecasts, cleanup priority ranking, oil & gas
risk, and energy-impact analytics over the Caspian Sea.

```
kazakh_backend/
├── KazakhAI_ML_Gemini/   → Deployable FastAPI "Logic API" (web service)
│   ├── api/              → FastAPI app + all HTTP endpoints
│   ├── src/              → AI models, drift engine, risk/energy/priority engines
│   │   └── checkpoints/  → Verified model weights + seed data (COMMITTED to git)
│   ├── requirements.txt        → Full local stack (incl. torch)
│   ├── requirements-server.txt → Minimal deploy stack (torch-free)
│   ├── setup.bat / setup.sh    → One-command local environment setup
│   └── run.bat / run.sh        → One-command local server start
├── pipeline/             → Offline data-engineering CLI (Copernicus satellite ingest)
├── Dockerfile            → Railway image (torch-free, minimal)
├── railway.toml          → Railway service config
├── frontend_integ.md     → Endpoint contract for the frontend team (READ THIS)
└── REMAINING_PROJECT_TASKS.md
```

> **Model weights are committed.** The trained U-Net weights (`src/checkpoints/unet_caspian_best.pth`,
> `unet_caspian_best.weights.json`) and all seed checkpoints are versioned in git and are **not**
> gitignored. Every developer gets the full trained model with a fresh clone — nothing to download.

---

## 1. Run the whole project locally (2 commands)

```bash
cd KazakhAI_ML_Gemini
./setup.sh        # Windows: setup.bat   → creates .venv + installs everything incl. torch
./run.sh          # Windows: run.bat     → starts the API on http://localhost:8000
```

That's it. The environment is ready to run **everything**: the API server, the trained
U-Net/classifier models, the drift simulator, the priority/risk/energy engines, and the full
verification suite — no extra downloads, no external database (SQLite auto-seeds on boot).

Prefer manual steps? (Python 3.11+ required):

```bash
cd KazakhAI_ML_Gemini
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # full local stack incl. torch
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

> Want the smallest possible local install (API only, torch-free, matches Railway)?
> `pip install -r requirements-server.txt` instead. You'll still get the API, but the
> U-Net/classifier and `verify_ai_engine.py` need `requirements.txt` (torch).

### Verify everything runs (models + drift + API)

```bash
cd KazakhAI_ML_Gemini
python verify_ai_engine.py
```

This instantiates the trained U-Net and classifier, runs the 30-day Lagrangian drift
simulation, the 8-factor priority engine, the risk heatmap generator, and smoke-tests every
API route. It writes only to a temp scratch dir — it never overwrites the committed seed
checkpoints.

### On startup the server
1. Creates/opens the SQLite operational store (`data/kazakh_ai.db`).
2. Seeds it from the checkpoints in `src/checkpoints/`.
3. Ingests live Open-Meteo weather (falls back to synthetic offline).
4. Launches a background scheduler that refreshes risk/energy/trend/anomaly stages
   every `REFRESH_INTERVAL_SECONDS` (default `3600`).

### Verify the API is up
- Health check: `http://localhost:8000/api/v1/health` → `{"server_status": "ONLINE", ...}`
- API index (full route list): `http://localhost:8000/api/v1`
- Swagger UI: `http://localhost:8000/docs`
- Full route smoke test: `python api/app.py`

---

## 2. Prerequisites

- **Python 3.11+** (tested on 3.12/3.13)
- Git
- (Optional, for model training) a GPU + Copernicus satellite data — see section 4.

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

Retraining the U-Net segmenter or sensor-fusion classifier is **not** part of the web service
and needs `torch` + satellite data. With the full local install (`requirements.txt`), use the
modules directly:

```bash
cd KazakhAI_ML_Gemini
python -m src.models.train          # trains U-Net on the tile dataset
```

> Note: the deployed Railway API does **not** run these models — it serves the committed
> checkpoint artifacts. `/api/v1/detect/segment` is a demo probe. Locally, the models run
> fine (verified by `verify_ai_engine.py`).

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

- Full AI engine + API: `python KazakhAI_ML_Gemini/verify_ai_engine.py`
- API routes: `python KazakhAI_ML_Gemini/api/app.py` (verifies every endpoint returns 200).
- Data pipeline: `cd pipeline/marine_dataset && uv run pytest`.
