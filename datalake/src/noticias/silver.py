"""Fase 7: Bronze -> Silver (limpieza, validación, deduplicación, versionado y Comprehend).

Modos:
  - incremental (por defecto): aplica uno o varios lotes de Bronze sobre el estado vigente de Silver.
    Solo reescribe las particiones (fechas) que cambian; las noticias sin cambios no se reprocesan.
  - rebuild: reconstruye Silver completo desde todos los lotes de Bronze, sin consultar los RSS.
    Comprehend no se vuelve a llamar porque los resultados están en caché por hash del texto.

Publicación atómica: los Parquet se escriben en una carpeta nueva (v=<write_id>) y solo al final se
actualiza la ubicación de cada partición en Glue. Athena nunca ve archivos parciales ni duplicados.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone

import pyarrow as pa

from . import control, jobs
from .enrich import Doc, Enricher
from .ingest import list_bronze_manifests
from .parse import normalize_key, parse_feed
from .schemas import SILVER_TABLES
from .settings import Settings, iso, new_run_id, utc_now
from .storage import GlueCatalog, S3Store, location_to_prefix

log = logging.getLogger("noticias.silver")


def naive_utc(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def published_date(row: dict) -> str:
    ts = row.get("published_at_utc")
    return ts.strftime("%Y-%m-%d") if ts else "sin_fecha"


def write_id_now() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%S%fZ")


def load_silver_state(s3: S3Store, catalog: GlueCatalog) -> tuple[dict, dict, dict]:
    """Lee la versión publicada (vigente) de las tres tablas Silver."""
    loaded = {}
    for table, (_, schema) in SILVER_TABLES.items():
        rows = []
        for location in catalog.partition_locations(table).values():
            rows.extend(s3.read_parquet_prefix(location_to_prefix(s3.bucket, location), schema).to_pylist())
        loaded[table] = rows
    news = {r["news_id"]: r for r in loaded["silver_news"]}
    entities, phrases = defaultdict(list), defaultdict(list)
    for r in loaded["silver_news_entities"]:
        entities[r["news_id"]].append(r)
    for r in loaded["silver_news_key_phrases"]:
        phrases[r["news_id"]].append(r)
    return news, entities, phrases


def make_news_row(item, manifest: dict, language: str, ingest_ts: datetime, version: int,
                  first_seen: datetime, sections: list[str], section: str) -> dict:
    return {
        "news_id": item.news_id, "id_strategy": item.id_strategy, "guid": item.guid, "link": item.link,
        "title": item.title, "description": item.description, "media": manifest["media"],
        "section": section, "sections": sections, "published_at_raw": item.published_at_raw,
        "published_at_utc": naive_utc(item.published_at_utc), "date_status": item.date_status,
        "content_hash": item.content_hash, "analyzed_text_hash": item.analyzed_text_hash,
        "language": language, "enrichment_status": None, "version": version,
        "first_seen_at": first_seen, "last_updated_at": ingest_ts, "bronze_run_id": manifest["run_id"],
        "bronze_key": manifest["bronze_key"], "silver_run_id": None,
        "_analyzed_text": item.analyzed_text,  # temporal: no se escribe en Parquet
    }


def grouped_rows(news_id: str, items: list[dict], kind: str, result: dict, text_hash: str, run_id: str) -> list[dict]:
    """Una fila por entidad/frase distinta en la noticia (las repeticiones se cuentan en `mentions`)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for it in items:
        key = normalize_key(it["text"])
        if key:
            groups[(it.get("type"), key)].append(it)
    analyzed_at = naive_utc(result.get("analyzed_at"))
    rows = []
    for (etype, key), members in sorted(groups.items(), key=lambda kv: (kv[0][0] or "", kv[0][1])):
        display = Counter(m["text"] for m in members).most_common(1)[0][0]
        base = {"news_id": news_id, "score": max(m["score"] for m in members), "mentions": len(members),
                "analyzed_text_hash": text_hash, "language": result.get("language"),
                "analyzed_at": analyzed_at, "silver_run_id": run_id}
        if kind == "entity":
            rows.append({**base, "entity_type": etype, "entity_text": display, "entity_text_normalized": key})
        else:
            rows.append({**base, "key_phrase": display, "key_phrase_normalized": key})
    return rows


def write_quarantine(s3: S3Store, catalog: GlueCatalog, manifest: dict, rejected) -> None:
    date = manifest["ingestion_date"]
    now = iso(utc_now())
    rows = [{
        "run_id": manifest["run_id"], "source_id": manifest["source_id"], "bronze_key": manifest["bronze_key"],
        "item_index": r.index, "reasons": r.reasons, "raw_title": r.raw.get("title"),
        "raw_link": r.raw.get("link"), "raw_guid": r.raw.get("guid"), "raw_pubdate": r.raw.get("pubDate"),
        "raw_description": r.raw.get("description"), "quarantined_at": now,
    } for r in rejected]
    s3.put_jsonl(f"quarantine/news/ingestion_date={date}/{manifest['run_id']}__{manifest['source_id']}.jsonl", rows)
    catalog.publish_partitions("quarantine_news", {date: s3.uri(f"quarantine/news/ingestion_date={date}/")})


class SimulatedFailure(RuntimeError):
    """Fallo controlado para demostrar la recuperación (escenario 'Fallo controlado y reejecución')."""


def prepare_silver(settings: Settings, job_id: str, run_ids: list[str] | None = None,
                   rebuild: bool = False) -> dict:
    """Etapa 1 (limpieza, validación y deduplicación). Lee Bronze y el estado vigente de Silver y deja en
    tmp/jobs/<job_id>/prepared.json las particiones afectadas, ya resueltas, listas para enriquecer."""
    s3 = S3Store(settings.bucket, settings.region)
    catalog = GlueCatalog(settings.glue_database, settings.region)
    mode = "rebuild" if rebuild else "incremental"

    manifests = list_bronze_manifests(s3, None if rebuild else run_ids)
    if not manifests:
        raise RuntimeError(f"No hay lotes en Bronze para run_ids={run_ids}")

    if rebuild:
        news, entities, phrases = {}, defaultdict(list), defaultdict(list)
        original_dates: dict[str, str] = {}
    else:
        news, entities, phrases = load_silver_state(s3, catalog)
        original_dates = {nid: published_date(r) for nid, r in news.items()}
    previous_partitions = set(catalog.partition_locations("silver_news"))

    sources = {s.source_id: s for s in settings.sources}
    changed: set[str] = set()
    batch_stats = []

    for m in manifests:
        language = m.get("language") or (sources[m["source_id"]].language if m["source_id"] in sources else "es")
        valid, rejected = parse_feed(s3.get_bytes(m["bronze_key"]), m["media"])
        ingest_ts = naive_utc(m["ingestion_ts"])
        st = Counter(received=len(valid) + len(rejected), valid=len(valid), rejected=len(rejected))
        if rejected:
            write_quarantine(s3, catalog, m, rejected)
            for r in rejected:
                log.info("run_id=%s source=%s task=validate item=%d rechazado motivos=%s",
                         m["run_id"], m["source_id"], r.index, ",".join(r.reasons))

        seen_in_batch: set[str] = set()
        for item in valid:
            if item.news_id in seen_in_batch:
                st["duplicate_in_batch"] += 1
                continue
            seen_in_batch.add(item.news_id)
            current = news.get(item.news_id)

            if current is None:
                news[item.news_id] = make_news_row(item, m, language, ingest_ts, 1, ingest_ts,
                                                   [m["section"]], m["section"])
                changed.add(item.news_id)
                st["new"] += 1
                continue

            sections = list(current["sections"] or [])
            section_added = m["section"] not in sections
            if section_added:
                sections.append(m["section"])  # la misma noticia publicada en otro feed

            # Solo un lote más reciente que el de la versión vigente puede modificarla: reprocesar un
            # lote antiguo nunca revierte una noticia a una versión anterior.
            if m["run_id"] > current["bronze_run_id"] and item.content_hash != current["content_hash"]:
                row = make_news_row(item, m, language, ingest_ts, current["version"] + 1,
                                    current["first_seen_at"], sections, current["section"])
                if item.analyzed_text_hash == current["analyzed_text_hash"] and "_analyzed_text" not in current:
                    # Cambió la noticia (p. ej. la fecha) pero no el texto analizado, y la versión
                    # anterior ya estaba enriquecida: se conservan sus entidades y frases sin llamar
                    # a Comprehend. Si la versión anterior también es de esta ejecución (aún sin
                    # enriquecer, p. ej. en rebuild), se enriquece normalmente y la caché evita la llamada.
                    row.pop("_analyzed_text")
                    row["enrichment_status"] = current["enrichment_status"]
                news[item.news_id] = row
                changed.add(item.news_id)
                st["updated"] += 1
            else:
                st["unchanged"] += 1
                if section_added:
                    current["sections"] = sections
                    changed.add(item.news_id)
        batch_stats.append({"manifest": m, "stats": dict(st)})

    affected = {published_date(news[n]) for n in changed} | {original_dates[n] for n in changed if n in original_dates}
    if rebuild:
        affected |= previous_partitions | {published_date(r) for r in news.values()}

    rows = [r for r in news.values() if published_date(r) in affected]
    ids = {r["news_id"] for r in rows}
    state = {
        "job_id": job_id, "mode": mode, "affected_dates": sorted(affected), "changed": sorted(changed),
        "to_enrich": sorted(n for n in changed if "_analyzed_text" in news[n]),
        "news": rows, "news_current": len(news),
        "entities": {i: entities.get(i, []) for i in ids}, "phrases": {i: phrases.get(i, []) for i in ids},
        "batch_stats": batch_stats,
    }
    jobs.save(s3, job_id, "prepared", state)
    log.info("run_id=%s task=prepare mode=%s news_current=%d changed=%d to_enrich=%d affected_dates=%s",
             job_id, mode, len(news), len(changed), len(state["to_enrich"]), sorted(affected))
    return {"job_id": job_id, "mode": mode, "affected_dates": sorted(affected), "news_current": len(news),
            "changed": len(changed), "to_enrich": len(state["to_enrich"]),
            "batch_stats": [{"run_id": b["manifest"]["run_id"], "source_id": b["manifest"]["source_id"],
                             **b["stats"]} for b in batch_stats]}


def enrich_silver(settings: Settings, job_id: str) -> dict:
    """Etapa 2: Comprehend solo para noticias nuevas o con texto analizado distinto (con caché)."""
    s3 = S3Store(settings.bucket, settings.region)
    state = jobs.load(s3, job_id, "prepared")
    by_id = {r["news_id"]: r for r in state["news"]}
    to_enrich = [by_id[n] for n in state["to_enrich"]]
    enricher = Enricher(s3, settings.region, settings.supported_languages, settings.max_text_bytes)
    results = enricher.enrich([Doc(r["analyzed_text_hash"], r["_analyzed_text"], r["language"]) for r in to_enrich])
    enriched = {}
    for row in to_enrich:
        res = results[row["analyzed_text_hash"]]
        enriched[row["news_id"]] = {
            "enrichment_status": res["status"],
            "entities": grouped_rows(row["news_id"], res["entities"], "entity", res, row["analyzed_text_hash"], job_id),
            "phrases": grouped_rows(row["news_id"], res["key_phrases"], "phrase", res, row["analyzed_text_hash"], job_id),
        }
    jobs.save(s3, job_id, "enriched", {"results": enriched, "comprehend": enricher.stats.__dict__})
    return {"job_id": job_id, "comprehend": enricher.stats.__dict__}


def publish_silver(settings: Settings, job_id: str, simulate_failure: bool = False) -> dict:
    """Etapa 3: escribe las particiones afectadas en carpetas nuevas v=<write_id> y luego cambia su
    ubicación en Glue (publicación atómica). Registra los conteos de cada lote."""
    s3 = S3Store(settings.bucket, settings.region)
    catalog = GlueCatalog(settings.glue_database, settings.region)
    state = jobs.load(s3, job_id, "prepared")
    enriched = jobs.load(s3, job_id, "enriched")
    entities, phrases = state["entities"], state["phrases"]

    changed = set(state["changed"])
    for row in state["news"]:
        res = enriched["results"].get(row["news_id"])
        if res:
            row["enrichment_status"] = res["enrichment_status"]
            entities[row["news_id"]] = res["entities"]
            phrases[row["news_id"]] = res["phrases"]
        if row["news_id"] in changed:
            row["silver_run_id"] = job_id

    write_id = write_id_now()
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in state["news"]:
        by_date[published_date(row)].append(row)
    locations: dict[str, dict[str, str]] = {t: {} for t in SILVER_TABLES}
    for date in state["affected_dates"]:
        rows = sorted(by_date.get(date, []), key=lambda r: r["news_id"])
        ids = [r["news_id"] for r in rows]
        data = {
            "silver_news": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
            "silver_news_entities": [e for i in ids for e in entities.get(i, [])],
            "silver_news_key_phrases": [p for i in ids for p in phrases.get(i, [])],
        }
        for table, (path, schema) in SILVER_TABLES.items():
            prefix = f"{path}/published_date={date}/v={write_id}/"
            s3.write_parquet(prefix + "part-00000.parquet", pa.Table.from_pylist(data[table], schema=schema))
            locations[table][date] = s3.uri(prefix)

    if simulate_failure:
        log.error("run_id=%s task=publish_silver FALLO CONTROLADO después de escribir v=%s y antes de "
                  "publicar en Glue: Athena sigue viendo la versión anterior", job_id, write_id)
        raise SimulatedFailure(f"Fallo controlado en publish_silver (archivos sin publicar en v={write_id})")

    for table in ("silver_news_entities", "silver_news_key_phrases", "silver_news"):
        catalog.publish_partitions(table, locations[table])

    # Registro de conteos por lote. Un lote ya procesado por otra ejecución genera un registro de
    # reprocesamiento aparte; el reintento de la misma ejecución sobrescribe su propio registro.
    processed_at = iso(utc_now())
    for b in state["batch_stats"]:
        m, st = b["manifest"], Counter(b["stats"])
        existing = control.read_batch_record(s3, m["ingestion_date"], m["run_id"], m["source_id"]) or dict(m)
        already = existing.get("processed_at") is not None and existing.get("processing_run_id") != job_id
        record = {**existing, "items_received": st["received"], "items_valid": st["valid"],
                  "items_rejected": st["rejected"], "items_duplicate_in_batch": st["duplicate_in_batch"],
                  "items_new": st["new"], "items_updated": st["updated"], "items_unchanged": st["unchanged"],
                  "processed_at": processed_at, "processing_run_id": job_id}
        if already:
            record["batch_type"] = "reprocess"
            control.write_batch_record(s3, catalog, m["ingestion_date"], record, suffix=f"reprocess-{job_id}")
        else:
            control.write_batch_record(s3, catalog, m["ingestion_date"], record)
        log.info("run_id=%s source=%s task=silver mode=%s received=%d valid=%d rejected=%d dup=%d new=%d updated=%d unchanged=%d",
                 m["run_id"], m["source_id"], state["mode"], st["received"], st["valid"], st["rejected"],
                 st["duplicate_in_batch"], st["new"], st["updated"], st["unchanged"])

    summary = {
        "run_id": job_id, "stage": "silver", "mode": state["mode"], "status": "complete",
        "bronze_batches": [f"{b['manifest']['run_id']}/{b['manifest']['source_id']}" for b in state["batch_stats"]],
        "batch_stats": [{"run_id": b["manifest"]["run_id"], "source_id": b["manifest"]["source_id"], **b["stats"]}
                        for b in state["batch_stats"]],
        "news_current": state["news_current"], "news_changed": len(changed),
        "affected_dates": state["affected_dates"], "write_id": write_id,
        "comprehend": enriched["comprehend"], "finished_at": processed_at,
    }
    control.write_run_status(s3, job_id, "silver", summary)
    log.info("run_id=%s task=silver mode=%s news_current=%d changed=%d affected_dates=%s",
             job_id, state["mode"], state["news_current"], len(changed), state["affected_dates"])
    return summary


def run_silver(settings: Settings, run_ids: list[str] | None = None, rebuild: bool = False,
               silver_run_id: str | None = None) -> dict:
    """Las tres etapas seguidas (uso local desde la CLI)."""
    mode = "rebuild" if rebuild else "incremental"
    job_id = silver_run_id or (run_ids[0] if run_ids and len(run_ids) == 1 and not rebuild
                               else f"{mode}-{new_run_id()}")
    prepare_silver(settings, job_id, run_ids, rebuild)
    enrich_silver(settings, job_id)
    return publish_silver(settings, job_id)
