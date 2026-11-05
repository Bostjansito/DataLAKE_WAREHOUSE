#!/usr/bin/env python3
"""Resolve managed credentials in memory, then exec without logging secrets."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

import boto3


RUNTIME_PATH = Path("/opt/ecommerce/runtime.json")
APP_PATH = "/opt/ecommerce/app"
RUNTIME_ENV = {
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
}


def resolve_environment(config, environ=None, client=None):
    """Database endpoints belong to config; native secrets supply only credentials.

    No credentials are written to disk, and every process start requests the
    current version for MySQL, DocumentDB, and Redshift.
    """
    env = dict(os.environ if environ is None else environ)
    for key, value in config.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = str(value)
    prefixes = [prefix for prefix in ("MYSQL", "MONGO", "REDSHIFT")
                if env.get(f"{prefix}_SECRET_ARN")]
    try:
        if prefixes and client is None:
            client = boto3.client("secretsmanager", region_name=env["AWS_REGION"])
        for prefix in prefixes:
            secret = json.loads(client.get_secret_value(
                SecretId=env[f"{prefix}_SECRET_ARN"], VersionStage="AWSCURRENT"
            )["SecretString"])
            for field in ("username", "password"):
                if not isinstance(secret[field], str) or not secret[field]:
                    raise ValueError("Invalid credential")
            for field in ("HOST", "PORT", "DATABASE"):
                if not env.get(f"{prefix}_{field}"):
                    raise ValueError("Missing database endpoint")
            if prefix == "MONGO":
                host = env["MONGO_HOST"]
                # Terraform supplies a DNS endpoint, never a URI or query string.
                if any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for char in host):
                    raise ValueError("Invalid source endpoint")
                port = int(env["MONGO_PORT"])
                if not 1 <= port <= 65535:
                    raise ValueError("Invalid source port")
                username = quote(secret["username"], safe="")
                password = quote(secret["password"], safe="")
                database = quote(env["MONGO_DATABASE"], safe="")
                env["MONGO_URI"] = (
                    f"mongodb://{username}:{password}@{host}:{port}/{database}"
                    "?authSource=admin&tls=true&replicaSet=rs0&retryWrites=false"
                )
            else:
                env[f"{prefix}_USER"] = secret["username"]
                env[f"{prefix}_PASSWORD"] = secret["password"]
    except Exception:
        # SDK/parser exceptions can embed SecretString contents or a Mongo URI.
        raise RuntimeError("Unable to resolve database runtime configuration") from None
    env.update(RUNTIME_ENV)
    return env


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("Usage: runtime.py executable [args...]", file=sys.stderr)
        return 2
    try:
        config = json.loads(RUNTIME_PATH.read_text())
        env = resolve_environment(config)
        os.chdir(APP_PATH)
        os.execvpe(args[0], args, env)
    except Exception:
        print("Unable to launch configured runtime; check configuration and AWS permissions", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
