"""No AWS: SDK-shape validation and stateful Glue/Athena contract doubles."""
import copy
import json
from pathlib import Path

import botocore.session
from botocore.validate import validate_parameters
import pytest

from lake import LocalStore
from lake.catalog import register_snapshot, query
from lake.cli import execute, parser
from lake.storage import write_json, read_json
from lake.schemas import TABLE_SCHEMAS


class Glue:
    def __init__(self):
        self.model = botocore.session.get_session().get_service_model("glue")
        self.tables = {name: {"Name": name, "StorageDescriptor": {"Location": "s3://lake/old/", "Columns": [{"Name": "x", "Type": "string"}]},
                              "PartitionKeys": [{"Name": "publication_date", "Type": "string"}], "TableType": "EXTERNAL_TABLE"}
                       for name in TABLE_SCHEMAS}
        self.partitions = {name: {("2026-10-20",): {"Values": ["2026-10-20"], "StorageDescriptor": {"Location": "s3://lake/old/"}}} for name in TABLE_SCHEMAS}
        self.fail_once = True

    def get_table(self, DatabaseName, Name):
        return {"Table": copy.deepcopy(self.tables[Name])}

    def update_table(self, **kwargs):
        validate_parameters(kwargs, self.model.operation_model("UpdateTable").input_shape)
        self.tables[kwargs["TableInput"]["Name"]] = copy.deepcopy(kwargs["TableInput"])

    def get_paginator(self, name):
        owner = self
        class Pages:
            def paginate(self, DatabaseName, TableName):
                yield {"Partitions": copy.deepcopy(list(owner.partitions[TableName].values()))}
        return Pages()

    def create_partition(self, **kwargs):
        validate_parameters(kwargs, self.model.operation_model("CreatePartition").input_shape)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("controlled Glue failure")
        self.partitions[kwargs["TableName"]][tuple(kwargs["PartitionInput"]["Values"])] = copy.deepcopy(kwargs["PartitionInput"])

    def update_partition(self, **kwargs):
        validate_parameters(kwargs, self.model.operation_model("UpdatePartition").input_shape)
        self.partitions[kwargs["TableName"]][tuple(kwargs["PartitionValueList"])] = copy.deepcopy(kwargs["PartitionInput"])

    def delete_partition(self, **kwargs):
        validate_parameters(kwargs, self.model.operation_model("DeletePartition").input_shape)
        del self.partitions[kwargs["TableName"]][tuple(kwargs["PartitionValues"])]


def test_glue_interrupted_switch_converges_and_removes_old_partitions(tmp_path):
    store, glue = LocalStore(tmp_path), Glue()
    manifest = {"run_id": "batch", "tables": {name: {"location": f"s3://lake/{name}/", "partitions": ["2026-10-22", "2026-10-23"]} for name in TABLE_SCHEMAS}}
    write_json(store, "_control/current.json", manifest)
    with pytest.raises(RuntimeError):
        register_snapshot(store, manifest, "rss_lake", glue)
    assert read_json(store, "_control/catalog_status.json")["status"] == "updating"
    assert register_snapshot(store, manifest, "rss_lake", glue)["status"] == "ready"
    assert register_snapshot(store, manifest, "rss_lake", glue)["status"] == "ready"
    for name in TABLE_SCHEMAS:
        assert set(glue.partitions[name]) == {("2026-10-22",), ("2026-10-23",)}
        assert glue.tables[name]["StorageDescriptor"]["Location"] == f"s3://lake/{name}/"
        for values, partition in glue.partitions[name].items():
            assert partition["StorageDescriptor"]["Location"] == f"s3://lake/{name}/publication_date={values[0]}/"


def test_cli_rebuild_references_bronze_without_new_logical_copy(tmp_path):
    def args(*extra):
        return parser().parse_args(["run", "--root", str(tmp_path), *extra])
    first = execute(args("--run-id", "original", "--fixture-dir", "tests/fixtures/initial"))
    store = LocalStore(tmp_path)
    original_keys = store.list("bronze/")
    rebuilt = execute(args("--run-id", "rebuilt", "--from-bronze", "original"))
    assert rebuilt["tables"]["news"]["row_count"] == first["tables"]["news"]["row_count"] == 4
    assert rebuilt["metrics"]["repeated"] == 4
    assert store.list("bronze/") == original_keys
    assert read_json(store, "_control/runs/rebuilt/ingest.json")["replay_of"] == "original"
    assert execute(args("--run-id", "rebuilt", "--replay")) == rebuilt
    with pytest.raises(ValueError, match="ocupado"):
        execute(args("--run-id", "rebuilt", "--from-bronze", "does-not-exist"))
    assert execute(args("--run-id", "original", "--replay")) == first
    assert read_json(store, "_control/current.json")["run_id"] == "rebuilt"


def test_athena_timeout_cancels_and_failures_surface():
    class Athena:
        stopped = False
        state = "RUNNING"
        def start_query_execution(self, **kwargs):
            return {"QueryExecutionId": "test"}
        def get_query_execution(self, **kwargs):
            return {"QueryExecution": {"Status": {"State": self.state, "StateChangeReason": "controlled"}}}
        def stop_query_execution(self, **kwargs):
            self.stopped = True
    client = Athena()
    with pytest.raises(TimeoutError):
        query(client, "SELECT 1", "rss_lake", "rss-lake", timeout=0)
    assert client.stopped
    client.state = "FAILED"
    with pytest.raises(RuntimeError, match="controlled"):
        query(client, "SELECT 1", "rss_lake", "rss-lake")


def test_s3_exists_exact_prefix_and_access_denied_not_suppressed():
    from lake.storage import S3Store
    class Client:
        result = {}
        error = False
        def list_objects_v2(self, **kwargs):
            assert kwargs == {"Bucket": "lake", "Prefix": "_control/run.json", "MaxKeys": 1}
            if self.error:
                raise PermissionError("AccessDenied")
            return self.result
    store = object.__new__(S3Store)
    store.bucket, store.client = "lake", Client()
    assert not store.exists("_control/run.json")
    store.client.result = {"Contents": [{"Key": "_control/run.json/child"}]}
    assert not store.exists("_control/run.json")
    store.client.result = {"Contents": [{"Key": "_control/run.json"}]}
    assert store.exists("_control/run.json")
    store.client.error = True
    with pytest.raises(PermissionError):
        store.exists("_control/run.json")
