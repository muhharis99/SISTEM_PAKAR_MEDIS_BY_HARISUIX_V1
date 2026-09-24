#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/Scripts/python.exe" ]; then
  echo "[1/4] Membuat virtual environment..."
  python -m venv .venv
fi

echo "[2/4] Memasang dependency..."
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -r requirements.txt

echo "[3/4] Memastikan index retrieval tersedia..."
.venv/Scripts/python.exe scripts/build_index.py

echo "[4/4] Menjalankan CDSS Mata di http://localhost:8000"
.venv/Scripts/python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
