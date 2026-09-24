#!/usr/bin/env bash
set -e
python scripts/build_index.py
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
