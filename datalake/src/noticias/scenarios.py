"""Copias controladas de un RSS guardado en Bronze para demostrar escenarios sin depender del medio.

Se toma un feed.xml existente, se modifica de forma conocida y se guarda como un NUEVO lote de Bronze
(batch_type=controlled_copy, con la ruta del original en `origin_bronze_key`). Bronze nunca se sobrescribe.

Modos:
  - modificado:   cambia la descripción del primer ítem (nueva versión y nuevo análisis de Comprehend) y
                  la fecha del segundo sin tocar su texto (nueva versión sin llamar a Comprehend).
  - defectuosos:  conserva los ítems originales (quedan como repetidos sin cambios) y agrega ítems con
                  título vacío, sin enlace, con enlace inválido, sin fecha, con fecha ilegible y un
                  duplicado dentro del mismo lote.
"""
from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET

from defusedxml import ElementTree as SafeET

from . import control
from .ingest import bronze_prefix, classify_response, list_bronze_manifests
from .settings import Settings, iso, new_run_id, utc_now
from .storage import GlueCatalog, S3Store

log = logging.getLogger("noticias.scenarios")

MODES = ("modificado", "defectuosos")


def _item(title: str | None, link: str | None, pubdate: str | None, description: str) -> ET.Element:
    item = ET.Element("item")
    for tag, value in (("title", title), ("link", link), ("pubDate", pubdate), ("description", description)):
        if value is not None:
            ET.SubElement(item, tag).text = value
    return item


def mutate(xml_bytes: bytes, mode: str, run_id: str) -> tuple[bytes, list[str]]:
    root = SafeET.fromstring(xml_bytes)  # defusedxml: sin entidades externas
    channel = root.find("channel")
    items = channel.findall("item")
    changes = []
    if mode == "modificado":
        desc = items[0].find("description")
        desc.text = (desc.text or "") + f" [Actualización controlada {run_id}: texto ampliado por el editor]"
        changes.append(f"item0 descripción modificada: {items[0].findtext('link')}")
        pub = items[1].find("pubDate")
        if pub is not None and pub.text and pub.text[-6] in "+-":
            # Misma hora expresada en otra zona horaria (UTC): cambia el contenido crudo, no el texto.
            from .parse import parse_pubdate
            dt, _ = parse_pubdate(pub.text)
            pub.text = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            changes.append(f"item1 fecha reescrita en UTC (mismo texto analizado): {items[1].findtext('link')}")
    elif mode == "defectuosos":
        first = items[0]
        base = "https://www.eltiempo.com/politica/escenario-controlado"
        extra = [
            _item("", f"{base}-titulo-vacio-9000001", first.findtext("pubDate"), "Ítem sin título"),
            _item("Noticia sin enlace", None, first.findtext("pubDate"), "Ítem sin enlace"),
            _item("Noticia con enlace inválido", "javascript:alert(1)", first.findtext("pubDate"), "Enlace no http"),
            _item("Noticia controlada sin fecha de publicación", f"{base}-sin-fecha-9000002", None,
                  "Ítem válido sin pubDate: se conserva en la partición sin_fecha"),
            _item("Noticia controlada con fecha ilegible", f"{base}-fecha-ilegible-9000003", "ayer en la tarde",
                  "Ítem válido con fecha que no se puede interpretar"),
        ]
        for e in extra:
            channel.append(e)
        channel.append(ET.fromstring(ET.tostring(first)))  # duplicado dentro del mismo lote
        changes = ["+1 título vacío", "+1 sin enlace", "+1 enlace inválido", "+1 sin fecha",
                   "+1 fecha ilegible", "+1 duplicado del item0"]
    else:
        raise ValueError(f"Modo desconocido {mode}; use {MODES}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), changes


def controlled_copy(settings: Settings, from_run_id: str, source_id: str, mode: str,
                    run_id: str | None = None) -> dict:
    s3 = S3Store(settings.bucket, settings.region)
    catalog = GlueCatalog(settings.glue_database, settings.region)
    originals = [m for m in list_bronze_manifests(s3, [from_run_id]) if m["source_id"] == source_id]
    if not originals:
        raise RuntimeError(f"No existe el lote {from_run_id}/{source_id} en Bronze")
    origin = originals[0]
    run_id = run_id or new_run_id()
    body, changes = mutate(s3.get_bytes(origin["bronze_key"]), mode, run_id)
    status, error, n_items = classify_response(200, body)

    now = utc_now()
    ingestion_date = now.strftime("%Y-%m-%d")
    prefix = bronze_prefix(source_id, ingestion_date, run_id)
    content_hash = hashlib.sha256(body).hexdigest()
    record = {**{k: origin.get(k) for k in ("source_id", "media", "section", "url", "language")},
              "run_id": run_id, "batch_type": "controlled_copy", "ingestion_ts": iso(now),
              "ingestion_date": ingestion_date, "http_status": None, "status": status, "error_message": error,
              "items_received": n_items, "content_bytes": len(body), "content_hash": content_hash,
              "bronze_key": prefix + "feed.xml", "origin_bronze_key": origin["bronze_key"],
              "scenario": mode, "changes": changes}
    s3.put_bytes(record["bronze_key"], body, "application/rss+xml",
                 metadata={"run-id": run_id, "source-id": source_id, "sha256": content_hash,
                           "origin": origin["bronze_key"]})
    s3.put_json(prefix + "_manifest.json", record)
    control.write_batch_record(s3, catalog, ingestion_date, record)
    log.info("run_id=%s source=%s task=controlled_copy modo=%s origen=%s cambios=%s",
             run_id, source_id, mode, origin["bronze_key"], changes)
    return record
