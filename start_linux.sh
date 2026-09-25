#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
PORT="${PORT:-8000}"
OLLAMA_URL="${VISION_PROVIDER_URL:-http://127.0.0.1:11434/api/chat}"
VISION_MODEL="${VISION_MODEL:-qwen3-vl:2b}"
export VISION_ENABLED="${VISION_ENABLED:-true}"
export VISION_PROVIDER_URL="$OLLAMA_URL"
export VISION_MODEL
export VISION_TIMEOUT="${VISION_TIMEOUT:-180}"

echo "[1/6] Memeriksa Ollama..."
if ! curl -fsS "http://127.0.0.1:11434/api/tags" >/tmp/cdss_ollama_tags.json; then
  echo
  echo "ERROR: Ollama tidak dapat diakses di http://127.0.0.1:11434"
  echo "Pastikan service Ollama aktif:"
  echo "  sudo systemctl status ollama"
  echo "  sudo systemctl start ollama"
  exit 1
fi

if ! grep -q "\"name\":\"${VISION_MODEL}\"" /tmp/cdss_ollama_tags.json; then
  echo
  echo "WARNING: model ${VISION_MODEL} belum ditemukan."
  echo "Pasang dengan:"
  echo "  ollama pull ${VISION_MODEL}"
  echo
  echo "Melanjutkan tanpa model vision akan membuat status Vision = model_missing."
fi

echo "[2/6] Menyiapkan Python virtual environment..."
if [ ! -x "$PY" ]; then
  python3 -m venv .venv
fi

echo "[3/6] Memasang / memverifikasi dependency..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt

echo "[4/6] Memeriksa retrieval index..."
if [ -f "data/index/tfidf.joblib" ] && [ -f "data/index/matrix.npz" ] && [ -f "data/index/metadata.json" ] && [ -f "data/index/diagnoses.json" ]; then
  echo "Index lokal ditemukan. Build dilewati."
else
  echo "Index belum lengkap. Menjalankan build_index.py..."
  "$PY" scripts/build_index.py
fi

echo "[5/6] Memeriksa syntax backend + ML..."
"$PY" -m compileall -q backend ml
echo "Syntax check OK."

echo "[6/6] Menjalankan CDSS Mata di http://localhost:${PORT}"
echo "Vision model: ${VISION_MODEL}"
exec "$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
