"""Transactional staged COPY, primary-key replacement and durable batch state."""
import hashlib
import json
import os
from contextlib import contextmanager

import psycopg2
from psycopg2 import sql

from aws_dw.extraction.extractor import (
    MYSQL_COLUMNS, MONGO_COLUMNS, read_manifest, s3_client, validate_batch_id, verify_payload,
)

COLUMN_TYPES = {
    "customer_id": "BIGINT", "product_id": "BIGINT", "order_id": "BIGINT", "order_item_id": "BIGINT",
    "review_id": "BIGINT", "event_id": "BIGINT", "quantity": "INTEGER", "rating": "INTEGER",
    "registration_date": "DATE", "updated_at": "TIMESTAMP", "order_date": "TIMESTAMP",
    "reviewed_at": "TIMESTAMPTZ", "occurred_at": "TIMESTAMPTZ", "price": "DECIMAL(12,2)",
    "unit_price": "DECIMAL(12,2)", "subtotal": "DECIMAL(14,2)", "total": "DECIMAL(14,2)",
    "is_active": "BOOLEAN", "document_json": "VARCHAR(65535)",
}
TABLES = {(source, entity): columns for source, entities in
          (("mysql", MYSQL_COLUMNS), ("mongodb", MONGO_COLUMNS)) for entity, columns in entities.items()}


def _table(source, entity):
    return ("mysql_" if source == "mysql" else "mongo_") + entity


def _connect_redshift():
    return psycopg2.connect(
        host=os.environ["REDSHIFT_HOST"], port=int(os.getenv("REDSHIFT_PORT", "5439")),
        dbname=os.environ["REDSHIFT_DATABASE"], user=os.environ["REDSHIFT_USER"],
        password=os.environ["REDSHIFT_PASSWORD"], sslmode="verify-full", connect_timeout=15,
    )


@contextmanager
def warehouse():
    conn = _connect_redshift()
    try:
        with conn:
            with conn.cursor() as cur:
                yield cur
    finally:
        conn.close()


def initialize():
    with warehouse() as cur:
        cur.execute('CREATE SCHEMA IF NOT EXISTS "raw"')
        cur.execute("""CREATE TABLE IF NOT EXISTS "raw"."batch_ledger" (
            batch_id VARCHAR(64), manifest_sha256 VARCHAR(64), status VARCHAR(20),
            rows_loaded BIGINT, loaded_at TIMESTAMPTZ, completed_at TIMESTAMPTZ)""")
        for (source, entity), columns in TABLES.items():
            definitions = [sql.SQL("{} {}").format(sql.Identifier(column),
                           sql.SQL(COLUMN_TYPES.get(column, "VARCHAR(1024)"))) for column in columns]
            definitions.extend([sql.SQL("_loaded_at TIMESTAMPTZ"), sql.SQL("_source VARCHAR(64)"),
                                sql.SQL("_batch_id VARCHAR(64)")])
            cur.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
                sql.Identifier("raw", _table(source, entity)), sql.SQL(", ").join(definitions)))


def batch_status(batch_id):
    batch_id = validate_batch_id(batch_id)
    initialize()
    with warehouse() as cur:
        cur.execute('SELECT status FROM "raw"."batch_ledger" WHERE batch_id=%s', (batch_id,))
        row = cur.fetchone()
        return row[0] if row else None


def load_batch(batch_id):
    """Replay reads S3 only. All six raw tables and pending state commit together."""
    batch_id = validate_batch_id(batch_id)
    initialize()
    s3 = s3_client()
    manifests = [read_manifest(source, batch_id, s3) for source in ("mysql", "mongodb")]
    digest = hashlib.sha256(json.dumps(manifests, sort_keys=True).encode()).hexdigest()
    for manifest in manifests:
        expected = MYSQL_COLUMNS if manifest["source"] == "mysql" else MONGO_COLUMNS
        if set(manifest["entities"]) != set(expected):
            raise ValueError("Incomplete entity manifest")
        for entity, info in manifest["entities"].items():
            if info["columns"] != expected[entity]:
                raise ValueError("Manifest column mismatch")
            prefix = f"raw/{manifest['source']}/{entity}/batch_id={batch_id}/"
            if not info["key"].startswith(prefix) or info["s3_uri"] != f"s3://{os.environ['S3_BUCKET']}/{info['key']}":
                raise ValueError("Manifest payload outside batch")
            verify_payload(s3, info)
    with warehouse() as cur:
        # Redshift UNIQUE constraints are informational: explicitly serialize/check state.
        cur.execute('LOCK TABLE "raw"."batch_ledger"')
        cur.execute('SELECT manifest_sha256,status FROM "raw"."batch_ledger" WHERE batch_id=%s', (batch_id,))
        existing = cur.fetchone()
        if existing:
            if existing[0] != digest:
                raise ValueError("Batch manifest changed after load")
            return False
        cur.execute("""SELECT batch_id FROM "raw"."batch_ledger" WHERE status <> 'succeeded'""")
        if cur.fetchone():
            raise RuntimeError("Complete or recover the pending batch before loading another")
        if batch_id != "0":
            cur.execute("""SELECT 1 FROM "raw"."batch_ledger" WHERE batch_id='0' AND status='succeeded'""")
            if not cur.fetchone():
                raise RuntimeError("Initial batch 0 must succeed before incrementals")
        rows = 0
        for manifest in manifests:
            source = manifest["source"]
            for entity, info in manifest["entities"].items():
                columns = TABLES[source, entity]
                raw = sql.Identifier("raw", _table(source, entity))
                stage = sql.Identifier("stage_" + _table(source, entity))
                names = sql.SQL(", ").join(map(sql.Identifier, columns))
                cur.execute(sql.SQL("CREATE TEMP TABLE {} (LIKE {})").format(stage, raw))
                # COPY lists only actual CSV fields, never metadata columns.
                cur.execute(sql.SQL("""COPY {} ({}) FROM {} IAM_ROLE {} REGION {}
                    CSV IGNOREHEADER 1 EMPTYASNULL BLANKSASNULL DATEFORMAT 'auto' TIMEFORMAT 'auto'""").format(
                    stage, names, sql.Literal(info["s3_uri"]),
                    sql.Literal(os.environ["REDSHIFT_COPY_ROLE_ARN"]), sql.Literal(os.environ["AWS_REGION"])))
                cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(stage))
                if cur.fetchone()[0] != info["rows"]:
                    raise ValueError(f"COPY row count mismatch for {source}.{entity}")
                pk = sql.Identifier(columns[0])
                cur.execute(sql.SQL("SELECT {} FROM {} GROUP BY {} HAVING COUNT(*) > 1 LIMIT 1").format(pk, stage, pk))
                if cur.fetchone():
                    raise ValueError(f"Duplicate source keys in {source}.{entity}")
                cur.execute(sql.SQL("DELETE FROM {} USING {} WHERE {}.{} = {}.{}").format(
                    raw, stage, raw, pk, stage, pk))
                cur.execute(sql.SQL("""INSERT INTO {} ({}, _loaded_at, _source, _batch_id)
                    SELECT {}, %s::TIMESTAMPTZ, %s, %s FROM {}""").format(raw, names, names, stage),
                    (manifest["extracted_at"], f"{source}.{entity}", batch_id))
                rows += info["rows"]
        cur.execute("""INSERT INTO "raw"."batch_ledger"
            (batch_id,manifest_sha256,status,rows_loaded,loaded_at)
            VALUES (%s,%s,'pending',%s,CURRENT_TIMESTAMP)""", (batch_id, digest, rows))
    return True


def mark_batch_succeeded(batch_id):
    with warehouse() as cur:
        cur.execute('LOCK TABLE "raw"."batch_ledger"')
        cur.execute('SELECT status FROM "raw"."batch_ledger" WHERE batch_id=%s', (validate_batch_id(batch_id),))
        row = cur.fetchone()
        if row is None or row[0] not in ("pending", "succeeded"):
            raise RuntimeError("Batch was not loaded")
        cur.execute("""UPDATE "raw"."batch_ledger" SET status='succeeded', completed_at=CURRENT_TIMESTAMP
            WHERE batch_id=%s AND status='pending'""", (batch_id,))


def get_load_stats(batch_id):
    with warehouse() as cur:
        cur.execute('SELECT batch_id,status,rows_loaded,loaded_at,completed_at FROM "raw"."batch_ledger" WHERE batch_id=%s',
                    (validate_batch_id(batch_id),))
        return cur.fetchall()
