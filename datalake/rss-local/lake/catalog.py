"""Publish complete snapshots to Glue; readers must wait for ready.json.

Glue has no multi-table transaction: an interrupted switch is resumed idempotently.
Queries through this module run only after all locations and partitions converge.
"""
from __future__ import annotations

import copy
import re
import time

import boto3
from botocore.config import Config

from .schemas import TABLE_SCHEMAS
from .storage import read_json, write_json


def clients(region):
    session = boto3.Session(region_name=region)
    config = Config(retries={"mode": "standard", "total_max_attempts": 3},
                    connect_timeout=10, read_timeout=60)
    return session.client("glue", config=config), session.client("athena", config=config)


def register_snapshot(store, manifest, database, glue):
    """Reconcile partitions, including old dates; retry after any interrupted switch."""
    run_id = manifest["run_id"]
    current = read_json(store, "_control/current.json")
    if current["run_id"] != run_id:
        raise ValueError("Solo se registra el snapshot vigente")
    write_json(store, "_control/catalog_status.json", {"run_id": run_id, "status": "updating"})
    for name, metadata in manifest["tables"].items():
        table = glue.get_table(DatabaseName=database, Name=name)["Table"]
        descriptor = copy.deepcopy(table["StorageDescriptor"])
        descriptor["Location"] = metadata["location"]
        table_input = {key: table[key] for key in (
            "Name", "Description", "Owner", "Retention", "PartitionKeys", "TableType", "Parameters"
        ) if key in table}
        table_input["StorageDescriptor"] = descriptor
        table_input.setdefault("Parameters", {})["lake_run_id"] = run_id
        glue.update_table(DatabaseName=database, TableInput=table_input)
        previous = {}
        for page in glue.get_paginator("get_partitions").paginate(DatabaseName=database, TableName=name):
            for partition in page["Partitions"]:
                previous[tuple(partition["Values"])] = partition
        expected = set()
        for date in metadata["partitions"]:
            values = (date,)
            expected.add(values)
            partition_descriptor = copy.deepcopy(descriptor)
            partition_descriptor["Location"] = metadata["location"] + f"publication_date={date}/"
            partition = {"Values": list(values), "StorageDescriptor": partition_descriptor,
                         "Parameters": {"lake_run_id": run_id}}
            if values in previous:
                glue.update_partition(DatabaseName=database, TableName=name,
                                      PartitionValueList=list(values), PartitionInput=partition)
            else:
                glue.create_partition(DatabaseName=database, TableName=name, PartitionInput=partition)
        for values in previous.keys() - expected:
            glue.delete_partition(DatabaseName=database, TableName=name, PartitionValues=list(values))
    status = {"run_id": run_id, "status": "ready", "tables": sorted(manifest["tables"])}
    write_json(store, "_control/catalog_status.json", status)
    return status


def query(athena, sql, database, workgroup, timeout=180):
    """Execute with bounded polling and cancel on timeout; return results and scan bytes."""
    execution_id = athena.start_query_execution(
        QueryString=sql, QueryExecutionContext={"Database": database}, WorkGroup=workgroup
    )["QueryExecutionId"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        execution = athena.get_query_execution(QueryExecutionId=execution_id)["QueryExecution"]
        state = execution["Status"]["State"]
        if state == "SUCCEEDED":
            rows = []
            for page in athena.get_paginator("get_query_results").paginate(QueryExecutionId=execution_id):
                rows.extend([[cell.get("VarCharValue") for cell in row["Data"]]
                             for row in page["ResultSet"]["Rows"]])
            return {"execution_id": execution_id, "bytes_scanned": execution.get("Statistics", {}).get("DataScannedInBytes", 0),
                    "rows": rows}
        if state in {"FAILED", "CANCELLED"}:
            raise RuntimeError(f"Athena {execution_id}: {execution['Status']}")
        time.sleep(2)
    athena.stop_query_execution(QueryExecutionId=execution_id)
    raise TimeoutError(f"Athena {execution_id} superó {timeout}s y se canceló")


def validate_athena(store, manifest, database, workgroup, athena):
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", database):
        raise ValueError("Nombre de base de datos no válido")
    status = read_json(store, "_control/catalog_status.json")
    if status != {"run_id": manifest["run_id"], "status": "ready", "tables": sorted(TABLE_SCHEMAS)}:
        raise ValueError("Catálogo incompleto; vuelva a ejecutar register_snapshot")
    evidence = {}
    for name, metadata in manifest["tables"].items():
        result = query(athena, f'SELECT count(*) AS n FROM "{database}"."{name}"', database, workgroup)
        if int(result["rows"][1][0]) != metadata["row_count"]:
            raise ValueError(f"Athena no concilia conteo {name}")
        evidence[name] = result
    checks = {
        "duplicate_news": "SELECT count(*) - count(DISTINCT news_id) FROM news",
        "orphan_entities": "SELECT count(*) FROM news_entities e LEFT JOIN news n ON e.news_id=n.news_id WHERE n.news_id IS NULL",
        "orphan_phrases": "SELECT count(*) FROM news_key_phrases e LEFT JOIN news n ON e.news_id=n.news_id WHERE n.news_id IS NULL",
        "daily_reconciliation": "SELECT count(*) FROM (SELECT medium,section,publication_date,count(*) n FROM news GROUP BY 1,2,3) s FULL OUTER JOIN daily_news g ON s.medium=g.medium AND s.section=g.section AND s.publication_date=g.publication_date WHERE coalesce(s.n,-1) <> coalesce(g.news_count,-1)",
        "entity_reconciliation": "SELECT count(*) FROM (SELECT entity,entity_type,publication_date,count(DISTINCT news_id) n FROM news_entities GROUP BY 1,2,3) s FULL OUTER JOIN entity_daily g ON s.entity=g.entity AND s.entity_type=g.entity_type AND s.publication_date=g.publication_date WHERE coalesce(s.n,-1) <> coalesce(g.news_count,-1)",
        "phrase_reconciliation": "SELECT count(*) FROM (SELECT section,phrase,publication_date,count(DISTINCT news_id) n FROM news_key_phrases GROUP BY 1,2,3) s FULL OUTER JOIN section_phrases g ON s.section=g.section AND s.phrase=g.phrase AND s.publication_date=g.publication_date WHERE coalesce(s.n,-1) <> coalesce(g.news_count,-1)",
    }
    for name, sql in checks.items():
        result = query(athena, sql, database, workgroup)
        if int(result["rows"][1][0]) != 0:
            raise ValueError(f"Control Athena no satisfecho: {name}")
        evidence[name] = result
    dates = manifest["tables"]["news"]["partitions"]
    date = dates[-1]
    evidence["partition_filtered"] = query(athena, f"SELECT sum(length(title)) FROM news WHERE publication_date = '{date}'", database, workgroup)
    evidence["partition_unfiltered"] = query(athena, "SELECT sum(length(title)) FROM news", database, workgroup)
    write_json(store, f"_control/runs/{manifest['run_id']}/athena.json", evidence)
    return evidence
