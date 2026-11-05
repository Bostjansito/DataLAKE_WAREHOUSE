#!/usr/bin/env bash
# Ejecuta terraform plan + apply y guarda ambas salidas como evidencia.
# Uso: ./tf_apply_evidencia.sh <carpeta-evidencia> [recurso ...]
#   ./tf_apply_evidencia.sh 02-iam aws_iam_role.airflow_ec2 ...   -> aplica solo esos recursos
#   ./tf_apply_evidencia.sh 05-ec2                                -> aplica toda la configuración
set -uo pipefail
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

FASE="${1:?Indica la carpeta de evidencia, por ejemplo 02-iam}"
shift
TARGETS=()
for r in "$@"; do TARGETS+=("-target=$r"); done
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TF_DIR="$ROOT/datalake/infra/terraform"
EVID="$ROOT/datalake/evidencias/$FASE"
mkdir -p "$EVID"
cd "$TF_DIR"

terraform fmt -check >/dev/null || { echo "terraform fmt reporta diferencias"; terraform fmt -diff; exit 1; }
terraform validate -no-color || exit 1

{ echo "\$ terraform plan ${TARGETS[*]:-} -out=fase.tfplan   # $(date -u +%FT%TZ)"
  terraform plan -no-color -input=false "${TARGETS[@]}" -out=fase.tfplan 2>&1; } > "$EVID/01-terraform-plan.txt"
grep -E "^Plan:|No changes" "$EVID/01-terraform-plan.txt" || { tail -20 "$EVID/01-terraform-plan.txt"; exit 1; }

{ echo "\$ terraform apply fase.tfplan   # $(date -u +%FT%TZ)"
  terraform apply -no-color -input=false fase.tfplan 2>&1; } > "$EVID/02-terraform-apply.txt"
STATUS=$?
rm -f fase.tfplan
grep -E "Apply complete|Error" "$EVID/02-terraform-apply.txt"
exit $STATUS
