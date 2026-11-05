#!/usr/bin/env bash
# Espera a que termine el arranque de Airflow en la instancia (lee el log por SSM).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for _ in $(seq 1 60); do
  out=$("$DIR/ssm_run.sh" "tail -3 /var/log/airflow-bootstrap.log" 2>&1)
  if echo "$out" | grep -qE "bootstrap terminado|rror"; then echo "$out"; exit 0; fi
  sleep 20
done
echo "TIMEOUT"; echo "$out"; exit 1
