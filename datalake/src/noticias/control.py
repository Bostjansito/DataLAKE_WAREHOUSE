"""Registro de control por lote/fuente y estado de cada ejecución (zona control/)."""
from __future__ import annotations

import json

from .storage import GlueCatalog, S3Store

BATCH_FIELDS = (
    "run_id", "batch_type", "source_id", "media", "section", "url", "http_status", "content_hash",
    "content_bytes", "bronze_key", "ingestion_ts", "status", "error_message", "items_received",
    "items_valid", "items_rejected", "items_duplicate_in_batch", "items_new", "items_updated",
    "items_unchanged", "processed_at", "processing_run_id",
)


def batch_key(ingestion_date: str, run_id: str, source_id: str, suffix: str | None = None) -> str:
    # Clave plana dentro de la partición: Athena lee todos los archivos de la carpeta.
    name = f"{run_id}__{source_id}" + (f"__{suffix}" if suffix else "")
    return f"control/batches/ingestion_date={ingestion_date}/{name}.json"


def write_batch_record(s3: S3Store, catalog: GlueCatalog, ingestion_date: str, record: dict,
                       suffix: str | None = None) -> str:
    row = {k: record.get(k) for k in BATCH_FIELDS}
    key = batch_key(ingestion_date, row["run_id"], row["source_id"], suffix)
    s3.put_jsonl(key, [row])  # sobrescribe: idempotente ante reintentos
    catalog.publish_partitions(
        "control_batches", {ingestion_date: s3.uri(f"control/batches/ingestion_date={ingestion_date}/")})
    return key


def read_batch_record(s3: S3Store, ingestion_date: str, run_id: str, source_id: str) -> dict | None:
    key = batch_key(ingestion_date, run_id, source_id)
    if not s3.exists(key):
        return None
    return json.loads(s3.get_bytes(key).decode("utf-8").splitlines()[0])


def run_status_key(run_id: str, stage: str) -> str:
    return f"control/runs/run_id={run_id}/{stage}.json"


def write_run_status(s3: S3Store, run_id: str, stage: str, summary: dict) -> None:
    s3.put_json(run_status_key(run_id, stage), summary)


def read_run_status(s3: S3Store, run_id: str, stage: str) -> dict | None:
    key = run_status_key(run_id, stage)
    return s3.get_json(key) if s3.exists(key) else None
