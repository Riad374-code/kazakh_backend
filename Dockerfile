# Khudaferin - Caspian Sea AI Marine Pollution & Hydrodynamics Logic API
# Railway deployment image. Minimal & torch-free on purpose: the API serves
# verified pipeline checkpoints, so the multi-GB ML training stack is excluded.
# Torch-only modules (src/models, src/ingestion/contract_loader) are never
# imported by the server code path (api/app.py).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data

WORKDIR /app

# --- Layer 1: dependencies (cached unless requirements change) --------------
COPY KazakhAI_ML_Gemini/requirements-server.txt ./requirements-server.txt
RUN pip install --upgrade pip && pip install -r requirements-server.txt

# --- Layer 2: application code + verified pipeline checkpoints (seed data) --
COPY KazakhAI_ML_Gemini/api ./api
COPY KazakhAI_ML_Gemini/src ./src
COPY KazakhAI_ML_Gemini/run.py ./run.py

# Writable runtime directory for the SQLite operational store.
# Attach a Railway volume here (or set DATABASE_PATH) for persistence.
RUN mkdir -p /app/data

EXPOSE 8000

# uvicorn, single worker: the app owns a single SQLite connection plus a
# background scheduler thread, so a single process is the correct topology.
CMD ["python", "run.py"]
