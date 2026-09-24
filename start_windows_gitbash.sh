#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

PY=".venv/Scripts/python.exe"
PORT="${PORT:-8000}"

if [ ! -x "$PY" ]; then
  echo "[1/5] Membuat virtual environment..."
  python -m venv .venv
else
  echo "[1/5] Virtual environment siap."
fi

echo "[2/5] Memasang / memverifikasi dependency..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt

echo "[3/5] Memeriksa retrieval index..."
if [ -f "data/index/tfidf.joblib" ] && [ -f "data/index/matrix.npz" ] && [ -f "data/index/metadata.json" ]; then
  echo "Index lokal ditemukan. Build dilewati."
else
  echo "Index belum lengkap. Menjalankan build_index.py..."
  "$PY" scripts/build_index.py
fi

echo "[4/5] Memeriksa syntax backend + ML..."
"$PY" -m compileall -q backend ml
echo "Syntax check OK."

echo "[5/5] Menjalankan CDSS Mata di http://localhost:$PORT"
"$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
