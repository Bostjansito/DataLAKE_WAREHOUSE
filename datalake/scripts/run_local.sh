#!/usr/bin/env bash
# Ejecuta el pipeline desde WSL con las credenciales del perfil de AWS local.
# Uso: datalake/scripts/run_local.sh <extract|silver|gold|run> [opciones]
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
DL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -x "$DL/.venv/bin/python" ]; then
  uv venv --quiet --python 3.12 "$DL/.venv"
  uv pip install --quiet --python "$DL/.venv/bin/python" -r "$DL/requirements.txt" pytest
fi

if [ -f "$DL/.env" ]; then set -a; . "$DL/.env"; set +a; fi
export DATALAKE_BUCKET="${DATALAKE_BUCKET:-datalake-noticias-387512138242-us-east-1}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export PYTHONPATH="$DL/src"

if [ "${1:-}" = "test" ]; then
  shift
  exec "$DL/.venv/bin/python" -m pytest -q "$DL/tests" "$@"
fi
exec "$DL/.venv/bin/python" -m noticias.cli "$@"
