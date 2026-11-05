"""Validaciones de calidad con Athena sobre lo publicado (lo mismo que ve un analista).

Todas las reglas van en UNA consulta: Athena cobra un mínimo de 10 MB por consulta, así que agruparlas
reduce el costo. Cada columna del resultado es la cantidad de registros que incumplen una regla: todas
deben ser 0. La consulta usa el workgroup del proyecto (límite de 100 MB escaneados).
"""
from __future__ import annotations

import logging
import time

import boto3

from .settings import Settings
from .storage import BOTO_CONFIG

log = logging.getLogger("noticias.validate")

CHECKS_SQL = """
WITH news AS (SELECT * FROM silver_news),
ent AS (SELECT * FROM silver_news_entities),
kp AS (SELECT * FROM silver_news_key_phrases),
silver_by_section AS (
  SELECT published_date, media, section, count(DISTINCT news_id) AS n FROM news GROUP BY 1, 2, 3),
gold_by_section AS (
  SELECT published_date, media, section, sum(news_count) AS n FROM gold_news_daily GROUP BY 1, 2, 3),
silver_by_entity AS (
  SELECT e.published_date, e.entity_type, e.entity_text_normalized, count(DISTINCT e.news_id) AS n
  FROM ent e GROUP BY 1, 2, 3),
gold_by_entity AS (
  SELECT published_date, entity_type, entity_text_normalized, sum(news_count) AS n
  FROM gold_entity_daily GROUP BY 1, 2, 3)
SELECT
  (SELECT count(*) FROM news) AS noticias_vigentes,
  (SELECT count(*) - count(DISTINCT news_id) FROM news) AS ids_duplicados,
  (SELECT count(*) FROM news WHERE news_id IS NULL OR title IS NULL OR title = '' OR link IS NULL
      OR media IS NULL OR section IS NULL OR content_hash IS NULL) AS campos_obligatorios_vacios,
  (SELECT count(*) FROM news WHERE NOT regexp_like(link, '^https?://[^/\\s]+')) AS enlaces_invalidos,
  (SELECT count(*) FROM news WHERE (published_date = 'sin_fecha') <> (published_at_utc IS NULL)
      OR (published_at_utc IS NOT NULL
          AND published_date <> date_format(published_at_utc, '%Y-%m-%d'))) AS fechas_inconsistentes,
  (SELECT count(*) FROM news WHERE enrichment_status IS NULL) AS noticias_sin_enriquecimiento,
  (SELECT count(*) FROM ent e LEFT JOIN news n
      ON n.news_id = e.news_id AND n.published_date = e.published_date WHERE n.news_id IS NULL) AS entidades_huerfanas,
  (SELECT count(*) FROM kp k LEFT JOIN news n
      ON n.news_id = k.news_id AND n.published_date = k.published_date WHERE n.news_id IS NULL) AS frases_huerfanas,
  (SELECT count(*) FROM silver_by_section s FULL OUTER JOIN gold_by_section g
      ON s.published_date = g.published_date AND s.media = g.media AND s.section = g.section
      WHERE coalesce(s.n, 0) <> coalesce(g.n, 0)) AS descuadre_gold_noticias,
  (SELECT count(*) FROM silver_by_entity s FULL OUTER JOIN gold_by_entity g
      ON s.published_date = g.published_date AND s.entity_type = g.entity_type
         AND s.entity_text_normalized = g.entity_text_normalized
      WHERE coalesce(s.n, 0) <> coalesce(g.n, 0)) AS descuadre_gold_entidades
"""

RULES = ("ids_duplicados", "campos_obligatorios_vacios", "enlaces_invalidos", "fechas_inconsistentes",
         "noticias_sin_enriquecimiento",
         "entidades_huerfanas", "frases_huerfanas", "descuadre_gold_noticias", "descuadre_gold_entidades")


def run_query(settings: Settings, sql: str, timeout_s: int = 120) -> tuple[list[dict], dict]:
    athena = boto3.client("athena", region_name=settings.region, config=BOTO_CONFIG)
    qid = athena.start_query_execution(
        QueryString=sql, WorkGroup=settings.athena_workgroup,
        QueryExecutionContext={"Database": settings.glue_database})["QueryExecutionId"]
    deadline = time.time() + timeout_s
    while True:
        info = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = info["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        if time.time() > deadline:
            athena.stop_query_execution(QueryExecutionId=qid)
            raise TimeoutError(f"Athena {qid} no terminó en {timeout_s}s")
        time.sleep(1.5)
    if state != "SUCCEEDED":
        raise RuntimeError(f"Athena {qid} {state}: {info['Status'].get('StateChangeReason')}")
    rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
    header = [c.get("VarCharValue") for c in rows[0]["Data"]]
    data = [dict(zip(header, [c.get("VarCharValue") for c in r["Data"]])) for r in rows[1:]]
    stats = {"query_execution_id": qid, "bytes_scanned": info["Statistics"].get("DataScannedInBytes"),
             "engine_ms": info["Statistics"].get("EngineExecutionTimeInMillis")}
    return data, stats


def run_validations(settings: Settings, run_id: str) -> dict:
    rows, stats = run_query(settings, CHECKS_SQL)
    result = {k: int(v) for k, v in rows[0].items()}
    failed = {k: result[k] for k in RULES if result[k] != 0}
    log.info("run_id=%s task=validate_athena resultado=%s bytes_scanned=%s query=%s",
             run_id, result, stats["bytes_scanned"], stats["query_execution_id"])
    summary = {"run_id": run_id, "checks": result, "failed": failed, **stats,
               "status": "failed" if failed else "passed"}
    if failed:
        raise RuntimeError(f"Validaciones con Athena fallidas: {failed}")
    return summary
