#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "============================================================"
echo " Khudaferin - local environment setup (macOS / Linux)"
echo "============================================================"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
echo
echo " Setup complete! Run the project with:  ./run.sh"
echo " Full AI verification:                  .venv/bin/python verify_ai_engine.py"
echo
