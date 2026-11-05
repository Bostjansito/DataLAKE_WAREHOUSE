"""Offline runtime tests: no AWS requests, credentials, or database connections."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, unquote, urlsplit

import boto3
from botocore.stub import Stubber
import pytest

from aws_dw.extraction import extractor


SCRIPTS = Path(__file__).resolve().parents[1] / "infra" / "scripts"
spec = importlib.util.spec_from_file_location("deployment_runtime", SCRIPTS / "runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def source_config():
    return {
        "AWS_REGION": "us-east-1", "S3_BUCKET": "test-bucket",
        "MYSQL_HOST": "mysql.example.test", "MYSQL_PORT": 3306,
        "MYSQL_DATABASE": "ecommerce", "MYSQL_SECRET_ARN": "mysql-secret",
        "MONGO_HOST": "docdb.example.test", "MONGO_PORT": 27017,
        "MONGO_DATABASE": "ecommerce", "MONGO_SECRET_ARN": "mongo-secret",
    }


def test_native_secrets_use_separate_endpoints_and_escape_credentials():
    config = source_config()
    username, password = "user+ /:@é", "pass/?#@:% +é"
    client = boto3.client("secretsmanager", region_name="us-east-1",
                          aws_access_key_id="offline", aws_secret_access_key="offline")
    with Stubber(client) as stub:
        for prefix in ("MYSQL", "MONGO"):
            stub.add_response("get_secret_value", {
                "SecretString": json.dumps({"username": username, "password": password})
            }, {"SecretId": config[f"{prefix}_SECRET_ARN"], "VersionStage": "AWSCURRENT"})
        env = runtime.resolve_environment(config, environ={}, client=client)
        stub.assert_no_pending_responses()
    assert env["MYSQL_HOST"] == config["MYSQL_HOST"]
    assert env["MYSQL_PORT"] == "3306"
    assert env["MYSQL_USER"] == username
    assert env["MYSQL_PASSWORD"] == password
    uri = urlsplit(env["MONGO_URI"])
    assert unquote(uri.username) == username
    assert unquote(uri.password) == password
    assert uri.hostname == config["MONGO_HOST"]
    assert uri.port == 27017
    assert uri.path == "/ecommerce"
    assert parse_qs(uri.query) == {
        "authSource": ["admin"], "tls": ["true"],
        "replicaSet": ["rs0"], "retryWrites": ["false"],
    }
    assert "MONGO_PASSWORD" not in env
    assert env["MYSQL_SSL_CA"] == env["MONGO_TLS_CA_FILE"]


def test_redshift_native_secret_uses_separate_endpoints():
    client = Mock()
    secret = {"username": "warehouse", "password": "offline-password"}
    config = {"REDSHIFT_SECRET_ARN": "redshift-secret",
              "REDSHIFT_HOST": "warehouse.example.test", "REDSHIFT_PORT": 5439,
              "REDSHIFT_DATABASE": "analytics"}
    client.get_secret_value.return_value = {"SecretString": json.dumps(secret)}
    env = runtime.resolve_environment(config, {}, client)
    assert env["REDSHIFT_USER"] == secret["username"]
    assert env["REDSHIFT_PASSWORD"] == secret["password"]
    for field in ("HOST", "PORT", "DATABASE"):
        assert env[f"REDSHIFT_{field}"] == str(config[f"REDSHIFT_{field}"])


def test_redshift_rejects_secret_only_legacy_endpoint_contract():
    client = Mock()
    client.get_secret_value.return_value = {"SecretString": json.dumps({
        "username": "warehouse", "password": "offline-password",
        "host": "legacy.example.test", "port": 5439, "database": "analytics",
    })}
    with pytest.raises(RuntimeError):
        runtime.resolve_environment({"REDSHIFT_SECRET_ARN": "redshift-secret"}, {}, client)


def test_compute_only_does_not_construct_aws_client(monkeypatch):
    client = Mock(side_effect=AssertionError("AWS access forbidden"))
    monkeypatch.setattr(runtime.boto3, "client", client)
    env = runtime.resolve_environment({"AWS_REGION": "us-east-1", "MYSQL_SECRET_ARN": None}, {})
    client.assert_not_called()
    assert "MONGO_URI" not in env


def test_retired_mongo_secret_is_not_fetched_and_replay_runtime_starts(monkeypatch, tmp_path):
    config = source_config()
    config.update(MONGO_SECRET_ARN=None, MONGO_HOST=None, MONGO_PORT=None,
                  MONGO_DATABASE=None, REDSHIFT_SECRET_ARN="redshift-secret",
                  REDSHIFT_HOST="warehouse.example.test", REDSHIFT_PORT=5439,
                  REDSHIFT_DATABASE="analytics")
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(config))
    monkeypatch.setattr(runtime, "RUNTIME_PATH", path)
    # Explicit null must clear stale inherited ARNs, not resurrect deleted secrets.
    monkeypatch.setenv("MONGO_SECRET_ARN", "retired-mongo-secret")
    client = Mock()
    client.get_secret_value.return_value = {"SecretString": json.dumps({
        "username": "offline-user", "password": "offline-password"})}
    monkeypatch.setattr(runtime.boto3, "client", Mock(return_value=client))
    monkeypatch.setattr(runtime.os, "chdir", Mock())
    execute = Mock()
    monkeypatch.setattr(runtime.os, "execvpe", execute)
    assert runtime.main(["python", "-m", "aws_dw", "pipeline", "--batch-id", "1", "--replay"]) == 0
    assert [call.kwargs["SecretId"] for call in client.get_secret_value.call_args_list] == [
        "mysql-secret", "redshift-secret"]
    env = execute.call_args.args[2]
    assert "MONGO_SECRET_ARN" not in env
    assert env["MYSQL_PASSWORD"] == "offline-password"
    assert env["REDSHIFT_PASSWORD"] == "offline-password"


@pytest.mark.parametrize("payload", ["not json OFFLINE_SECRET", "[]", "{}",
                                     '{"username":"name","password":null}'])
def test_invalid_secret_errors_are_redacted(payload):
    client = Mock()
    client.get_secret_value.return_value = {"SecretString": payload}
    with pytest.raises(RuntimeError, match="^Unable to resolve database runtime configuration$") as error:
        runtime.resolve_environment(source_config(), {}, client)
    assert error.value.__suppress_context__
    assert payload not in str(error.value)


def test_aws_error_does_not_expose_payload():
    client = Mock()
    client.get_secret_value.side_effect = ValueError("mongodb://user:OFFLINE_SECRET@host")
    with pytest.raises(RuntimeError) as error:
        runtime.resolve_environment(source_config(), {}, client)
    assert "OFFLINE_SECRET" not in str(error.value)
    assert "mongodb://" not in str(error.value)


@pytest.mark.parametrize("missing", ["MYSQL_HOST", "MYSQL_PORT", "MONGO_HOST", "MONGO_DATABASE"])
def test_managed_credentials_require_endpoint_fields(missing):
    config = source_config()
    del config[missing]
    client = Mock()
    client.get_secret_value.return_value = {
        "SecretString": json.dumps({"username": "user", "password": "offline-password"})}
    with pytest.raises(RuntimeError):
        runtime.resolve_environment(config, {}, client)


def test_runtime_main_executes_in_deployed_application(monkeypatch, tmp_path):
    path = tmp_path / "runtime.json"
    path.write_text('{"AWS_REGION":"us-east-1"}')
    monkeypatch.setattr(runtime, "RUNTIME_PATH", path)
    chdir, execute = Mock(), Mock()
    monkeypatch.setattr(runtime.os, "chdir", chdir)
    monkeypatch.setattr(runtime.os, "execvpe", execute)
    assert runtime.main(["/opt/ecommerce/runtime/bin/python", "-m", "aws_dw", "seed"]) == 0
    chdir.assert_called_once_with("/opt/ecommerce/app")
    executable, args, env = execute.call_args.args
    assert executable == "/opt/ecommerce/runtime/bin/python"
    assert args[-1] == "seed"
    assert env["DBT_PROJECT_DIR"] == "/opt/ecommerce/app/dbt"
    assert env["AIRFLOW__CORE__DAGS_FOLDER"] == "/opt/ecommerce/app/dags"


def test_runtime_main_redacts_configuration_error(monkeypatch, tmp_path, capsys):
    path = tmp_path / "runtime.json"
    path.write_text("OFFLINE_SECRET not json")
    monkeypatch.setattr(runtime, "RUNTIME_PATH", path)
    assert runtime.main(["unused"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "OFFLINE_SECRET" not in captured.err


def test_mysql_enforces_ca_and_identity_verification(monkeypatch):
    for key, value in {"MYSQL_HOST": "mysql.example.test", "MYSQL_USER": "user",
                       "MYSQL_PASSWORD": "offline-password", "MYSQL_DATABASE": "ecommerce",
                       "MYSQL_SSL_CA": "/offline/ca.pem"}.items():
        monkeypatch.setenv(key, value)
    connect = Mock()
    monkeypatch.setattr(extractor.pymysql, "connect", connect)
    extractor.get_mysql_connection(streaming=False)
    kwargs = connect.call_args.kwargs
    assert kwargs["ssl_ca"] == "/offline/ca.pem"
    assert kwargs["ssl_verify_cert"] is True
    assert kwargs["ssl_verify_identity"] is True
    assert kwargs["cursorclass"] == extractor.pymysql.cursors.Cursor


def test_mongo_enforces_documentdb_tls_options(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://offline.example.test/ecommerce")
    monkeypatch.setenv("MONGO_TLS_CA_FILE", "/offline/ca.pem")
    connect = Mock()
    monkeypatch.setattr(extractor, "MongoClient", connect)
    extractor.get_mongo_client()
    kwargs = connect.call_args.kwargs
    assert kwargs["tls"] is True
    assert kwargs["tlsCAFile"] == "/offline/ca.pem"
    assert kwargs["tlsAllowInvalidCertificates"] is False
    assert kwargs["tlsAllowInvalidHostnames"] is False
    assert kwargs["retryWrites"] is False


@pytest.mark.parametrize("variable,connector", [
    ("MYSQL_SSL_CA", extractor.get_mysql_connection),
    ("MONGO_TLS_CA_FILE", extractor.get_mongo_client),
])
def test_missing_ca_fails_before_database_client(monkeypatch, variable, connector):
    monkeypatch.delenv(variable, raising=False)
    mysql, mongo = Mock(), Mock()
    monkeypatch.setattr(extractor.pymysql, "connect", mysql)
    monkeypatch.setattr(extractor, "MongoClient", mongo)
    with pytest.raises(RuntimeError, match="verified TLS"):
        connector()
    mysql.assert_not_called()
    mongo.assert_not_called()


def test_mongo_constructor_error_never_discloses_uri(monkeypatch):
    uri = "mongodb://user:OFFLINE_SECRET@offline.example.test"
    monkeypatch.setenv("MONGO_URI", uri)
    monkeypatch.setenv("MONGO_TLS_CA_FILE", "/offline/ca.pem")
    monkeypatch.setattr(extractor, "MongoClient", Mock(side_effect=ValueError(uri)))
    with pytest.raises(RuntimeError) as error:
        extractor.get_mongo_client()
    assert "OFFLINE_SECRET" not in str(error.value)
    assert error.value.__suppress_context__
