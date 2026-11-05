"""Fase 6: extracción de los feeds RSS y escritura en Bronze.

Bronze guarda la respuesta original sin modificar:
  bronze/source=<fuente>/ingestion_date=AAAA-MM-DD/run_id=<id>/feed.xml
  bronze/source=<fuente>/ingestion_date=AAAA-MM-DD/run_id=<id>/_manifest.json

- Una fuente que falla (red, HTTP, XML malformado) NO se guarda en Bronze, pero queda registrada en
  control/ con su estado; la ejecución se marca como parcial o fallida, nunca como "sin noticias".
- Reintentar la misma ejecución (mismo run_id) no vuelve a consultar una fuente ya guardada.
"""
from __future__ import annotations

import hashlib
import logging

import requests
from defusedxml import ElementTree as SafeET

from . import control
from .settings import Settings, Source, iso, utc_now
from .storage import GlueCatalog, S3Store

log = logging.getLogger("noticias.ingest")

OK_STATUSES = {"success", "empty"}


def bronze_prefix(source_id: str, ingestion_date: str, run_id: str) -> str:
    return f"bronze/source={source_id}/ingestion_date={ingestion_date}/run_id={run_id}/"


def classify_response(status_code: int, body: bytes) -> tuple[str, str | None, int]:
    """Devuelve (estado, error, número de ítems) de una respuesta HTTP."""
    if status_code != 200:
        return "http_error", f"HTTP {status_code}", 0
    if not body or not body.strip():
        return "empty_response", "Respuesta vacía", 0
    try:
        root = SafeET.fromstring(body)
    except SafeET.ParseError as exc:
        return "malformed_xml", f"XML malformado: {exc}", 0
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        return "malformed_xml", f"No es un RSS válido (raíz <{root.tag}>)", 0
    items = channel.findall("item")
    return ("success" if items else "empty"), None, len(items)


def extract_source(src: Source, run_id: str, s3: S3Store, catalog: GlueCatalog,
                   settings: Settings, session: requests.Session) -> dict:
    now = utc_now()
    ingestion_date = now.strftime("%Y-%m-%d")
    prefix = bronze_prefix(src.source_id, ingestion_date, run_id)
    manifest_key = prefix + "_manifest.json"

    # Reintento de la misma ejecución: el lote ya existe, no se consulta de nuevo la fuente.
    existing = [k for k in s3.list_keys(f"bronze/source={src.source_id}/") if f"/run_id={run_id}/_manifest.json" in k]
    if existing:
        manifest = s3.get_json(existing[0])
        log.info("source=%s run_id=%s task=extract lote ya existente en Bronze, se reutiliza", src.source_id, run_id)
        return {**manifest, "reused": True}

    record = {
        "run_id": run_id, "batch_type": "extraction", "source_id": src.source_id, "media": src.media,
        "section": src.section, "url": src.url, "ingestion_ts": iso(now), "http_status": None,
        "content_hash": None, "content_bytes": 0, "bronze_key": None, "error_message": None,
        "items_received": 0, "language": src.language,
    }
    try:
        resp = session.get(src.url, timeout=settings.http_timeout_s,
                           headers={"User-Agent": settings.user_agent, "Accept": "application/rss+xml, application/xml"})
        body = resp.content
        record["http_status"] = resp.status_code
        status, error, n_items = classify_response(resp.status_code, body)
    except requests.RequestException as exc:
        body, status, error, n_items = b"", "failed", f"{type(exc).__name__}: {exc}", 0

    record.update(status=status, error_message=error, items_received=n_items, content_bytes=len(body))

    if status in OK_STATUSES:
        content_hash = hashlib.sha256(body).hexdigest()
        bronze_key = prefix + "feed.xml"
        s3.put_bytes(bronze_key, body, "application/rss+xml",
                     metadata={"run-id": run_id, "source-id": src.source_id, "sha256": content_hash})
        record.update(content_hash=content_hash, bronze_key=bronze_key, ingestion_date=ingestion_date)
        s3.put_json(manifest_key, record)  # el manifiesto se escribe al final: marca el lote como completo

    control.write_batch_record(s3, catalog, ingestion_date, record)
    log.info("source=%s run_id=%s task=extract status=%s http=%s items=%s bytes=%s error=%s",
             src.source_id, run_id, status, record["http_status"], n_items, len(body), error)
    return record


def run_extraction(run_id: str, settings: Settings, source_ids: list[str] | None = None) -> dict:
    s3 = S3Store(settings.bucket, settings.region)
    catalog = GlueCatalog(settings.glue_database, settings.region)
    sources = [s for s in settings.sources if not source_ids or s.source_id in source_ids]
    with requests.Session() as session:
        results = [extract_source(src, run_id, s3, catalog, settings, session) for src in sources]

    ok = [r for r in results if r["status"] in OK_STATUSES]
    status = "complete" if len(ok) == len(results) else ("partial" if ok else "failed")
    summary = {
        "run_id": run_id, "stage": "extract", "status": status, "finished_at": iso(utc_now()),
        "sources_ok": [r["source_id"] for r in ok],
        "sources_failed": [{"source_id": r["source_id"], "status": r["status"], "error": r["error_message"]}
                           for r in results if r["status"] not in OK_STATUSES],
        "bronze_keys": [r["bronze_key"] for r in ok],
    }
    control.write_run_status(s3, run_id, "extract", summary)
    log.info("run_id=%s task=extract status=%s ok=%d failed=%d", run_id, status, len(ok), len(results) - len(ok))
    return summary


def list_bronze_manifests(s3: S3Store, run_ids: list[str] | None = None) -> list[dict]:
    """Lotes disponibles en Bronze (para procesar o reprocesar sin consultar los RSS)."""
    manifests = []
    for key in s3.list_keys("bronze/"):
        if not key.endswith("/_manifest.json"):
            continue
        if run_ids and not any(f"/run_id={r}/" in key for r in run_ids):
            continue
        manifests.append(s3.get_json(key))
    return sorted(manifests, key=lambda m: (m["run_id"], m["source_id"]))
