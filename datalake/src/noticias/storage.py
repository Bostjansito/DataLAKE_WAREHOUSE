"""Acceso a S3 (objetos, JSON, Parquet) y a las particiones de Glue Data Catalog."""
from __future__ import annotations

import io
import json
import logging
from typing import Iterable

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.config import Config
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)

BOTO_CONFIG = Config(retries={"max_attempts": 5, "mode": "standard"})


class S3Store:
    def __init__(self, bucket: str, region: str):
        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region, config=BOTO_CONFIG)

    def uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream",
                  metadata: dict[str, str] | None = None) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                               Metadata=metadata or {})

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put_json(self, key: str, obj) -> None:
        self.put_bytes(key, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                       "application/json")

    def get_json(self, key: str):
        return json.loads(self.get_bytes(key))

    def put_jsonl(self, key: str, rows: Iterable[dict]) -> None:
        body = "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows) + "\n"
        self.put_bytes(key, body.encode("utf-8"), "application/x-ndjson")

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(o["Key"] for o in page.get("Contents", []))
        return keys

    def write_parquet(self, key: str, table: pa.Table) -> None:
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        self.put_bytes(key, buf.getvalue(), "application/vnd.apache.parquet")

    def read_parquet_prefix(self, prefix: str, schema: pa.Schema) -> pa.Table:
        tables = [pq.read_table(io.BytesIO(self.get_bytes(k)), schema=schema)
                  for k in self.list_keys(prefix) if k.endswith(".parquet")]
        return pa.concat_tables(tables) if tables else schema.empty_table()


class GlueCatalog:
    """Registra particiones explícitamente (sin crawlers)."""

    def __init__(self, database: str, region: str):
        self.database = database
        self.client = boto3.client("glue", region_name=region, config=BOTO_CONFIG)
        self._tables: dict[str, dict] = {}

    def _table(self, name: str) -> dict:
        if name not in self._tables:
            self._tables[name] = self.client.get_table(DatabaseName=self.database, Name=name)["Table"]
        return self._tables[name]

    def partition_locations(self, table: str) -> dict[str, str]:
        """Devuelve {valor_particion: ubicacion_s3} (tablas con una sola clave de partición)."""
        out: dict[str, str] = {}
        paginator = self.client.get_paginator("get_partitions")
        for page in paginator.paginate(DatabaseName=self.database, TableName=table):
            for p in page["Partitions"]:
                out[p["Values"][0]] = p["StorageDescriptor"]["Location"]
        return out

    def publish_partitions(self, table: str, locations: dict[str, str]) -> dict[str, int]:
        """Crea o actualiza particiones para que apunten a las ubicaciones dadas.

        Es el paso de "publicación": mientras no se ejecuta, Athena sigue viendo la versión anterior.
        """
        if not locations:
            return {"created": 0, "updated": 0}
        sd_base = {k: v for k, v in self._table(table)["StorageDescriptor"].items()}
        existing = self.partition_locations(table)

        def part_input(value: str, location: str) -> dict:
            return {"Values": [value], "StorageDescriptor": {**sd_base, "Location": location}}

        to_create = [part_input(v, loc) for v, loc in locations.items() if v not in existing]
        to_update = [{"PartitionValueList": [v], "PartitionInput": part_input(v, loc)}
                     for v, loc in locations.items() if v in existing and existing[v] != loc]

        for i in range(0, len(to_create), 100):
            resp = self.client.batch_create_partition(
                DatabaseName=self.database, TableName=table, PartitionInputList=to_create[i:i + 100])
            if resp.get("Errors"):
                raise RuntimeError(f"Glue BatchCreatePartition {table}: {resp['Errors']}")
        for i in range(0, len(to_update), 100):
            resp = self.client.batch_update_partition(
                DatabaseName=self.database, TableName=table, Entries=to_update[i:i + 100])
            if resp.get("Errors"):
                raise RuntimeError(f"Glue BatchUpdatePartition {table}: {resp['Errors']}")
        log.info("glue table=%s partitions_created=%d partitions_updated=%d",
                 table, len(to_create), len(to_update))
        return {"created": len(to_create), "updated": len(to_update)}


def location_to_prefix(bucket: str, location: str) -> str:
    prefix = location.removeprefix(f"s3://{bucket}/")
    return prefix if prefix.endswith("/") else prefix + "/"
