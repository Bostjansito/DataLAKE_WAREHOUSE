#!/usr/bin/env bash
# Ejecuta un escenario de calidad/recuperación en Airflow y guarda la evidencia.
# Uso: datalake/scripts/escenario.sh <nombre> '<conf JSON del DAG>' [comando previo de la CLI...]
#   escenario.sh 02-registros-defectuosos '{"bronze_run_id":"X"}'
# La evidencia queda en datalake/evidencias/09-escenarios/<nombre>.log con:
#   - estado de cada tarea del DAG
#   - resumen de Silver (conteos por lote: recibidos, válidos, rechazados, nuevos, actualizados...)
#   - estado final de la ejecución y resultado de las validaciones con Athena
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAME="$1"; CONF="$2"
OUT="$ROOT/datalake/evidencias/09-escenarios/$NAME.log"
mkdir -p "$(dirname "$OUT")"
BUCKET="${DATALAKE_BUCKET:-datalake-noticias-387512138242-us-east-1}"
{
  echo "# Escenario $NAME  ($(date -u +%FT%TZ))"
  echo "\$ dag_trigger.sh '$CONF'"
  "$ROOT/datalake/infra/scripts/dag_trigger.sh" "$CONF"
} 2>&1 | tee "$OUT"
EXEC=$(grep -o 'run_id=manual__[^ ]*' "$OUT" | head -1 | sed 's/run_id=manual__//')
RUN=${RUN:-}; [ -n "$RUN" ] || RUN=$(python3 -c "import sys,datetime; print(datetime.datetime.fromisoformat(sys.argv[1]).strftime('%Y%m%dT%H%M%SZ'))" "$EXEC")
{
  echo; echo "# control/runs/run_id=$RUN/"
  for stage in extract silver dag; do
    if aws s3 cp --only-show-errors "s3://$BUCKET/control/runs/run_id=$RUN/$stage.json" /tmp/stage.json 2>/dev/null; then
      python3 - "$stage" /tmp/stage.json <<'PY'
import json, sys
stage, path = sys.argv[1], sys.argv[2]
d = json.load(open(path))
keep = {"extract": ["status", "sources_ok", "sources_failed"],
        "silver": ["mode", "batch_stats", "news_current", "news_changed", "affected_dates", "write_id", "comprehend"],
        "dag": ["status", "extraction", "params", "validations"]}[stage]
print(f"## {stage}.json")
print(json.dumps({k: d.get(k) for k in keep}, ensure_ascii=False, indent=1))
PY
    fi
  done
} 2>&1 | tee -a "$OUT"
