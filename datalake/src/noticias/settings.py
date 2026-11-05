"""Configuración del pipeline: variables de entorno y fuentes RSS."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DATALAKE_ROOT = Path(__file__).resolve().parents[2]  # carpeta datalake/

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format=LOG_FORMAT)
    for noisy in ("botocore", "boto3", "urllib3", "s3transfer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@dataclass(frozen=True)
class Source:
    source_id: str
    media: str
    section: str
    url: str
    language: str = "es"


@dataclass(frozen=True)
class Settings:
    bucket: str
    region: str = "us-east-1"
    glue_database: str = "datalake_noticias_lab"
    athena_workgroup: str = "datalake-noticias-lab-wg"
    sources_file: Path = DATALAKE_ROOT / "config" / "sources.json"
    # Idiomas que Comprehend analiza para entidades y frases clave en este proyecto.
    supported_languages: tuple[str, ...] = ("es", "en")
    # Comprehend admite hasta 5.000 bytes UTF-8 por documento en las operaciones batch.
    max_text_bytes: int = 4500
    http_timeout_s: int = 20
    user_agent: str = "datalake-noticias-taller/1.0 (+proyecto academico)"
    sources: tuple[Source, ...] = field(default=())


def load_settings() -> Settings:
    bucket = os.environ.get("DATALAKE_BUCKET")
    if not bucket:
        raise RuntimeError("Falta la variable de entorno DATALAKE_BUCKET")
    sources_file = Path(os.environ.get("SOURCES_FILE", DATALAKE_ROOT / "config" / "sources.json"))
    base = Settings(
        bucket=bucket,
        region=os.environ.get("AWS_REGION", "us-east-1"),
        glue_database=os.environ.get("GLUE_DATABASE", "datalake_noticias_lab"),
        athena_workgroup=os.environ.get("ATHENA_WORKGROUP", "datalake-noticias-lab-wg"),
        sources_file=sources_file,
    )
    return Settings(**{**base.__dict__, "sources": load_sources(sources_file)})


def load_sources(path: Path) -> tuple[Source, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    sources = []
    seen = set()
    for raw in data.get("sources", []):
        missing = [k for k in ("source_id", "media", "section", "url") if not raw.get(k)]
        if missing:
            raise ValueError(f"Fuente mal configurada {raw}: faltan {missing}")
        if raw["source_id"] in seen:
            raise ValueError(f"source_id repetido: {raw['source_id']}")
        if raw["url"].rstrip("/").endswith("/rss"):
            raise ValueError(f"{raw['source_id']}: la URL apunta al directorio RSS, no a un feed")
        seen.add(raw["source_id"])
        sources.append(Source(**{k: raw[k] for k in Source.__dataclass_fields__ if k in raw}))
    if not sources:
        raise ValueError(f"No hay fuentes en {path}")
    return tuple(sources)


def new_run_id(now: datetime | None = None) -> str:
    """Identificador de ejecución ordenable lexicográficamente: AAAAMMDDTHHMMSSZ."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
