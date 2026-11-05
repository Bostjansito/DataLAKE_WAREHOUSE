"""Estado intermedio entre tareas del DAG (zona tmp/, expira en 1 día por ciclo de vida).

Cada etapa de Airflow corre en un proceso distinto: lo que una etapa produce y la siguiente necesita
(noticias preparadas, resultados de Comprehend, ubicaciones pendientes de publicar) se guarda como JSON en
  tmp/jobs/<job_id>/<etapa>.json
Nada en tmp/ es visible en Athena: los datos solo se publican al cambiar la partición en Glue.
"""
from __future__ import annotations

from datetime import datetime

from .storage import S3Store

# Campos de fecha y hora que se serializan como texto y se reconstruyen al leer.
DATETIME_FIELDS = {"published_at_utc", "first_seen_at", "last_updated_at", "analyzed_at", "built_at"}
FMT = "%Y-%m-%dT%H:%M:%S.%f"


def _encode(value):
    if isinstance(value, datetime):
        return value.strftime(FMT)
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    return value


def _decode(value, key: str | None = None):
    if isinstance(value, dict):
        return {k: _decode(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if key in DATETIME_FIELDS and isinstance(value, str):
        return datetime.strptime(value, FMT)
    return value


def job_key(job_id: str, stage: str) -> str:
    return f"tmp/jobs/{job_id}/{stage}.json"


def save(s3: S3Store, job_id: str, stage: str, state: dict) -> str:
    key = job_key(job_id, stage)
    s3.put_json(key, _encode(state))
    return key


def load(s3: S3Store, job_id: str, stage: str) -> dict:
    key = job_key(job_id, stage)
    if not s3.exists(key):
        raise RuntimeError(f"Falta el estado intermedio {key}: ejecute antes la etapa '{stage}'")
    return _decode(s3.get_json(key))
