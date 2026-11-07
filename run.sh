#!/usr/bin/env bash
# BhashaBridge AI - one-step setup and run for Linux / macOS.
set -e
cd "$(dirname "$0")"

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "Python 3.10+ is required: https://www.python.org/downloads/"; exit 1; }

if [ ! -d venv ]; then
  echo "Creating virtual environment..."
  "$PY" -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate

echo "Installing dependencies..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "Created .env. Open it and set GNANI_API_KEY=<your key>, then run ./run.sh again."
  exit 0
fi
if grep -q "your_new_api_key" .env; then
  echo "NOTE: .env still has the placeholder GNANI_API_KEY. Voice features need your real key."
fi

echo "Starting BhashaBridge AI at http://127.0.0.1:5000  (Ctrl+C to stop)"
python app.py
