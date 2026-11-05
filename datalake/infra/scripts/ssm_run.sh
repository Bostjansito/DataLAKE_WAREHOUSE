#!/usr/bin/env bash
# Ejecuta un comando en la instancia de Airflow con SSM Run Command (sin SSH) y muestra la salida.
# Uso: datalake/infra/scripts/ssm_run.sh "<comando>"
#   ssm_run.sh "tail -20 /var/log/airflow-bootstrap.log"
#   ssm_run.sh "/opt/datalake/deploy.sh"          # despliega la versión nueva del código
set -euo pipefail
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
TF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../terraform" && pwd)"
INSTANCE="$(terraform -chdir="$TF_DIR" output -raw airflow_instance_id)"
CMD="${1:?Indica el comando}"
PARAMS=$(python3 -c 'import json,sys; print(json.dumps({"commands":[sys.argv[1]]}))' "$CMD")
ID=$(aws ssm send-command --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
  --parameters "$PARAMS" --query Command.CommandId --output text)
for _ in $(seq 1 120); do
  STATUS=$(aws ssm get-command-invocation --command-id "$ID" --instance-id "$INSTANCE" \
    --query Status --output text 2>/dev/null || echo Pending)
  case "$STATUS" in Pending|InProgress|Delayed) sleep 3 ;; *) break ;; esac
done
aws ssm get-command-invocation --command-id "$ID" --instance-id "$INSTANCE" \
  --query '[StandardOutputContent,StandardErrorContent]' --output text
[ "$STATUS" = "Success" ]
