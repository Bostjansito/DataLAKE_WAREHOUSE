#!/usr/bin/env bash
# Dispara el DAG noticias_datalake en la instancia (por SSM) con una configuración JSON y espera el final.
# Uso: dag_trigger.sh '{"bronze_run_id": "20261105T003325Z"}'
#      dag_trigger.sh '{}'                                   # ejecución normal (extrae los RSS)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="${1:-"{}"}"
B64=$(printf '%s' "$CONF" | base64 -w0)
# EXEC_DATE ya definido = no se dispara de nuevo, solo se consulta esa ejecución.
REUSE="${EXEC_DATE:-}"
EXEC_DATE="${EXEC_DATE:-$(date -u +%Y-%m-%dT%H:%M:%S+00:00)}"
RUN_ID="manual__$EXEC_DATE"
# En la instancia: ejecuta un comando de Airflow como el usuario airflow con su entorno.
AF="sudo -u airflow bash -c 'set -a; . /etc/sysconfig/airflow; set +a; exec \"\$@\"' _"

[ -n "$REUSE" ] || "$DIR/ssm_run.sh" "$AF airflow dags trigger noticias_datalake -r '$RUN_ID' -e '$EXEC_DATE' -c \"\$(echo $B64 | base64 -d)\" >/dev/null 2>&1" >/dev/null
echo "run_id=$RUN_ID conf=$CONF"
STATE=queued
for i in $(seq 1 90); do
  [ "$i" -gt 1 ] && sleep 10
  STATE=$("$DIR/ssm_run.sh" "$AF airflow dags state noticias_datalake '$EXEC_DATE' 2>/dev/null | tail -1" | cut -d, -f1 | tr -d '[:space:]')
  case "$STATE" in success|failed) break ;; esac
done
echo "estado=$STATE"
"$DIR/ssm_run.sh" "$AF airflow tasks states-for-dag-run noticias_datalake '$RUN_ID' -o plain 2>/dev/null | awk 'NR>1{print \$3, \$4, \$5, \$6}' | column -t"
