#!/usr/bin/env bash
# Prepara el entorno en Linux/macOS: crea .venv, instala dependencias y ejecuta las pruebas.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
  echo "Creando entorno virtual en $ROOT/.venv"
  python3 -m venv .venv
fi

.venv/bin/python --version
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt -r requirements-dev.txt
.venv/bin/python -B -m unittest discover -s tests -v

echo
echo "Entorno listo. Ejecute:"
echo "  ./scripts/run_app.sh"
