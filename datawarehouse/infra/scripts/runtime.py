#!/usr/bin/env python3
"""Resolve exact Secrets Manager ARNs into the pipeline environment, then exec."""
import json
import os
from pathlib import Path
import sys
import boto3

config = json.loads(Path("/opt/ecommerce/runtime.json").read_text())
env = os.environ.copy()
env.update({key: str(value) for key, value in config.items() if value is not None})
client = boto3.client("secretsmanager", region_name=env["AWS_REGION"])
for prefix, arn_key in (("MYSQL", "MYSQL_SECRET_ARN"), ("MONGO", "MONGO_SECRET_ARN"), ("REDSHIFT", "REDSHIFT_SECRET_ARN")):
    if not env.get(arn_key):
        continue
    secret = json.loads(client.get_secret_value(SecretId=env[arn_key])["SecretString"])
    if prefix == "MONGO":
        env["MONGO_URI"] = secret["uri"]
        env["MONGO_DATABASE"] = secret["database"]
    else:
        for source, target in (("host", "HOST"), ("port", "PORT"), ("username", "USER"), ("password", "PASSWORD"), ("database", "DATABASE")):
            env[f"{prefix}_{target}"] = str(secret[source])
env.update({
    "MYSQL_SSL_CA": "/opt/ecommerce/certs/global-bundle.pem",
    "MONGO_TLS_CA_FILE": "/opt/ecommerce/certs/global-bundle.pem",
    "DBT_BIN": "/opt/ecommerce/dbt/bin/dbt",
    "DW_PYTHON": "/opt/ecommerce/runtime/bin/python",
    "AIRFLOW_HOME": "/opt/ecommerce/airflow",
    "AIRFLOW__CORE__DAGS_FOLDER": "/opt/ecommerce/app/dags",
    "AIRFLOW__CORE__EXECUTOR": "SequentialExecutor",
    "PGSSLROOTCERT": "/opt/ecommerce/certs/redshift-ca.crt",
    "HOME": "/opt/ecommerce",
    "AIRFLOW__CORE__LOAD_EXAMPLES": "False",
    "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN": "sqlite:////opt/ecommerce/airflow/airflow.db",
    "DBT_PROJECT_DIR": "/opt/ecommerce/app/dbt",
    "DBT_PROFILES_DIR": "/opt/ecommerce/app/dbt",
})
if len(sys.argv) < 2:
    raise SystemExit("Usage: runtime.py executable [args...]")
os.chdir("/opt/ecommerce/app")
os.execvpe(sys.argv[1], sys.argv[1:], env)
