#!/bin/bash
# Usage: remote-deploy.sh INSTANCE_ID s3://bucket/deploy/bundle-TIMESTAMP.tar.gz
set -euo pipefail
INSTANCE=${1:?Instance ID required}
BUNDLE=${2:?Explicit bundle URI required}
: "${AWS_REGION:=us-east-1}"
PARAMS=$(python3 - "$BUNDLE" <<'PY'
import json, shlex, sys
uri = sys.argv[1]
if not uri.startswith("s3://") or "/deploy/bundle-" not in uri or not uri.endswith(".tar.gz"):
    raise SystemExit("Use the exact deploy/bundle-*.tar.gz URI printed by upload-bundle.sh")
config = uri.removesuffix(".tar.gz") + ".runtime.json"
commands = [
    "set -eu",
    "cloud-init status --wait",
    "systemctl stop ecommerce-airflow.service ecommerce-airflow-web.service 2>/dev/null || true",
    "umask 077",
    'STAGE=$(mktemp -d /var/tmp/ecommerce-deploy.XXXXXXXX)',
    'trap \'rm -rf -- "$STAGE"\' EXIT',
    'mkdir "$STAGE/app"',
    "aws s3 cp " + shlex.quote(uri) + ' "$STAGE/bundle.tar.gz"',
    "aws s3 cp " + shlex.quote(config) + ' "$STAGE/runtime.json"',
    'tar --no-same-owner -xzf "$STAGE/bundle.tar.gz" -C "$STAGE/app"',
    # Only trusted root-owned staging files are read/executed before dropping UID.
    'chmod -R a+rX,go-w "$STAGE"',
    'bash "$STAGE/app/infra/scripts/deploy-instance.sh" "$STAGE/runtime.json"',
]
print(json.dumps({"commands": commands, "executionTimeout": ["3600"]}))
PY
)
aws ssm send-command --region "$AWS_REGION" --instance-ids "$INSTANCE" --document-name AWS-RunShellScript --parameters "$PARAMS" --timeout-seconds 3600 --query Command.CommandId --output text
