#!/usr/bin/env bash
# Inicia la interfaz web en http://127.0.0.1:8000 (documentacion de la API en /docs).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
  echo "El entorno no existe. Ejecute primero ./scripts/setup.sh" >&2
  exit 1
fi

exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}" --reload
