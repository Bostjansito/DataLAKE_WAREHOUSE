#!/usr/bin/env bash
# Abre la interfaz de Airflow en http://localhost:8081 (LOCAL_PORT) con reenvío de puertos de Session Manager.
# Requiere session-manager-plugin. La instancia no tiene puertos abiertos: el acceso se autoriza con IAM.
set -euo pipefail
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
TF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../terraform" && pwd)"
INSTANCE="$(terraform -chdir="$TF_DIR" output -raw airflow_instance_id)"
exec aws ssm start-session --target "$INSTANCE" --document-name AWS-StartPortForwardingSession \
  --parameters portNumber=8080,localPortNumber=${LOCAL_PORT:-8081}
