#!/bin/bash
# Run from any directory; only allowlisted application files enter the artifact.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
TF="$ROOT/infra/terraform"
: "${AWS_REGION:=us-east-1}"
BUCKET=$(terraform -chdir="$TF" output -raw raw_bucket)
BUILD="$ROOT/infra/.build"
umask 077
mkdir -p "$BUILD"
terraform -chdir="$TF" output -json runtime_config > "$BUILD/runtime.json"
BUNDLE="bundle-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
tar --exclude=__pycache__ --exclude='*.pyc' --exclude=dbt/dbt_packages --exclude=dbt/target --exclude=dbt/logs -czf "$BUILD/$BUNDLE" -C "$ROOT" src dags dbt requirements.txt pyproject.toml infra/scripts
aws s3 cp "$BUILD/$BUNDLE" "s3://$BUCKET/deploy/$BUNDLE" --region "$AWS_REGION"
aws s3 cp "$BUILD/runtime.json" "s3://$BUCKET/deploy/runtime.json" --region "$AWS_REGION"
printf 'Bundle: s3://%s/deploy/%s\nConfig: s3://%s/deploy/runtime.json\n' "$BUCKET" "$BUNDLE" "$BUCKET"
