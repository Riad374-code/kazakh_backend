#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/uvicorn" ]; then
    echo ".venv not found. Run ./setup.sh first."
    exit 1
fi
source .venv/bin/activate
echo "Starting Khudaferin Logic API on http://localhost:8000"
echo "Swagger docs: http://localhost:8000/docs"
exec uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
