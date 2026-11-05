"""Fase 8: Silver -> Gold (agregados diarios).

Métricas (todas cuentan noticias DISTINTAS, para que las repeticiones dentro de un texto o entre
feeds no inflen los indicadores):
  - gold_news_daily:        noticias por día, medio y sección principal.
  - gold_entity_daily:      noticias que mencionan cada entidad (persona, organización, lugar) por día.
  - gold_key_phrases_daily: noticias que contienen cada frase clave, por día y sección principal.

Solo se recalculan las fechas afectadas por la última ejecución de Silver (o todas con --all).
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict

import pyarrow as pa

from . import control, jobs
from .schemas import GOLD_TABLES, SILVER_TABLES
from .settings import Settings, iso, new_run_id, utc_now
from .silver import naive_utc, write_id_now
from .storage import GlueCatalog, S3Store, location_to_prefix

log = logging.getLogger("noticias.gold")


def _read_partition(s3: S3Store, locations: dict[str, str], date: str, table: str) -> list[dict]:
    if date not in locations:
        return []
    schema = SILVER_TABLES[table][1]
    return s3.read_parquet_prefix(location_to_prefix(s3.bucket, locations[date]), schema).to_pylist()


def aggregate_date(news: list[dict], entities: list[dict], phrases: list[dict]) -> dict[str, list[dict]]:
    by_section: dict[tuple, set] = defaultdict(set)
    for r in news:
        by_section[(r["media"], r["section"])].add(r["news_id"])
    news_ids = {r["news_id"] for r in news}
    section_of = {r["news_id"]: r["section"] for r in news}

    ent_news: dict[tuple, set] = defaultdict(set)
    ent_names: dict[tuple, Counter] = defaultdict(Counter)
    for e in entities:
        if e["news_id"] not in news_ids:  # nunca debería ocurrir: lo valida la Fase 9
            continue
        key = (e["entity_type"], e["entity_text_normalized"])
        ent_news[key].add(e["news_id"])
        ent_names[key][e["entity_text"]] += 1

    kp_news: dict[tuple, set] = defaultdict(set)
    kp_names: dict[tuple, Counter] = defaultdict(Counter)
    for p in phrases:
        if p["news_id"] not in news_ids:
            continue
        key = (section_of[p["news_id"]], p["key_phrase_normalized"])
        kp_news[key].add(p["news_id"])
        kp_names[key][p["key_phrase"]] += 1

    return {
        "gold_news_daily": [{"media": m, "section": s, "news_count": len(ids)}
                            for (m, s), ids in sorted(by_section.items())],
        "gold_entity_daily": [{"entity_type": t, "entity_text_normalized": n,
                               "entity_text": ent_names[(t, n)].most_common(1)[0][0], "news_count": len(ids)}
                              for (t, n), ids in sorted(ent_news.items())],
        "gold_key_phrases_daily": [{"section": s, "key_phrase_normalized": n,
                                    "key_phrase": kp_names[(s, n)].most_common(1)[0][0], "news_count": len(ids)}
                                   for (s, n), ids in sorted(kp_news.items())],
    }


def run_gold(settings: Settings, run_id: str | None = None, dates: list[str] | None = None,
             all_dates: bool = False, publish: bool = True) -> dict:
    """Construye Gold para las fechas indicadas. Con publish=False deja las ubicaciones nuevas en
    tmp/jobs/<run_id>/gold_pending.json y la tarea de Glue del DAG las publica (publish_gold)."""
    s3 = S3Store(settings.bucket, settings.region)
    catalog = GlueCatalog(settings.glue_database, settings.region)
    silver_locs = {t: catalog.partition_locations(t) for t in SILVER_TABLES}

    if all_dates:
        dates = sorted(silver_locs["silver_news"])
    elif dates is None:
        status = control.read_run_status(s3, run_id, "silver") if run_id else None
        if status is None:
            raise RuntimeError(f"No hay resumen de Silver para run_id={run_id}; use --date o --all")
        dates = status["affected_dates"]
    gold_run_id = run_id or f"gold-{new_run_id()}"

    write_id = write_id_now()
    built_at = naive_utc(utc_now())
    locations: dict[str, dict[str, str]] = {t: {} for t in GOLD_TABLES}
    totals = Counter()
    for date in sorted(dates):
        aggregates = aggregate_date(
            _read_partition(s3, silver_locs["silver_news"], date, "silver_news"),
            _read_partition(s3, silver_locs["silver_news_entities"], date, "silver_news_entities"),
            _read_partition(s3, silver_locs["silver_news_key_phrases"], date, "silver_news_key_phrases"),
        )
        for table, (path, schema) in GOLD_TABLES.items():
            rows = [{**r, "gold_run_id": gold_run_id, "built_at": built_at} for r in aggregates[table]]
            prefix = f"{path}/published_date={date}/v={write_id}/"
            s3.write_parquet(prefix + "part-00000.parquet", pa.Table.from_pylist(rows, schema=schema))
            locations[table][date] = s3.uri(prefix)
            totals[table] += len(rows)
        log.info("run_id=%s task=gold date=%s news_daily=%d entity_daily=%d key_phrases_daily=%d",
                 gold_run_id, date, len(aggregates["gold_news_daily"]), len(aggregates["gold_entity_daily"]),
                 len(aggregates["gold_key_phrases_daily"]))

    summary = {"run_id": gold_run_id, "stage": "gold", "status": "complete" if publish else "built",
               "dates": sorted(dates), "rows": dict(totals), "write_id": write_id, "finished_at": iso(utc_now())}
    if publish:
        for table, locs in locations.items():
            catalog.publish_partitions(table, locs)
    else:
        jobs.save(s3, gold_run_id, "gold_pending", {"locations": locations, "summary": summary})
    control.write_run_status(s3, gold_run_id, "gold", summary)
    return summary


def publish_gold(settings: Settings, job_id: str) -> dict:
    """Actualiza en Glue las particiones de Gold construidas por run_gold(publish=False) y verifica que
    todas las fechas afectadas existan en las tablas Silver y Gold."""
    s3 = S3Store(settings.bucket, settings.region)
    catalog = GlueCatalog(settings.glue_database, settings.region)
    pending = jobs.load(s3, job_id, "gold_pending")
    for table, locs in pending["locations"].items():
        catalog.publish_partitions(table, locs)
    dates = set(pending["summary"]["dates"])
    missing = {}
    for table in list(SILVER_TABLES) + list(GOLD_TABLES):
        registered = catalog.partition_locations(table)
        lacking = sorted(d for d in dates if d not in registered)
        if lacking:
            missing[table] = lacking
    if missing:
        raise RuntimeError(f"Particiones sin registrar en Glue: {missing}")
    summary = {**pending["summary"], "status": "complete", "published_at": iso(utc_now())}
    control.write_run_status(s3, job_id, "gold", summary)
    log.info("run_id=%s task=glue_catalog tablas=%d fechas=%s particiones verificadas",
             job_id, len(SILVER_TABLES) + len(GOLD_TABLES), sorted(dates))
    return summary
