"""Pipeline persistente; ejecutar un solo escritor a la vez (DAG max_active_runs=1).

Cada etapa termina escribiendo su checkpoint. Los snapshots no son visibles hasta
validate; el catálogo se actualiza fuera de este módulo usando current.json.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import io
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
import pyarrow as pa
import pyarrow.parquet as pq

from .schemas import TABLE_SCHEMAS, SILVER_TABLES, GOLD_TABLES
from .storage import read_json, write_json

UTC = timezone.utc
CURRENT = "_control/current.json"
SUPPORTED_LANGUAGES = {"es", "en"}
# Conservative shared limit for both synchronous operations, measured in UTF-8.
MAX_TEXT_BYTES = 5000


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(value: str | bytes) -> str:
    return sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"p", "br", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean(value: str) -> str:
    parser = _HTMLText()
    parser.feed(unescape(value or ""))
    return " ".join("".join(parser.parts).split())


def canonical_link(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid_link")
    if parsed.username or parsed.password or any(c.isspace() for c in value):
        raise ValueError("invalid_link")
    port = parsed.port
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if port and not ((parsed.scheme.lower() == "https" and port == 443)
                     or (parsed.scheme.lower() == "http" and port == 80)):
        host += f":{port}"
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parsed.scheme.lower(), host, parsed.path.rstrip("/") or "/",
                       urlencode(sorted(query)), ""))


def parse_date(value: str) -> tuple[str | None, str, str]:
    if not value:
        return None, "1970-01-01", "missing"
    try:
        try:
            date = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            return None, "1970-01-01", "missing_timezone"
        date = date.astimezone(UTC)
        return date.isoformat(), date.date().isoformat(), "valid"
    except (ValueError, TypeError, OverflowError):
        return None, "1970-01-01", "invalid"


def _local_tag(element):
    return element.tag.rsplit("}", 1)[-1]


def parse_feed(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    tag = _local_tag(root).lower()
    if tag not in {"rss", "rdf", "feed"}:
        raise ValueError("XML no es RSS/Atom")
    if tag == "rss" and not any(_local_tag(e) == "channel" for e in root):
        raise ValueError("RSS sin channel")
    result = []
    for item in root.iter():
        if _local_tag(item) not in {"item", "entry"}:
            continue
        fields = {}
        for child in item:
            name = _local_tag(child)
            value = "".join(child.itertext()).strip()
            if name == "link" and child.get("href"):
                if child.get("rel", "alternate") != "alternate":
                    continue
                value = child.get("href")
            fields.setdefault(name, value)
        result.append({
            "guid": fields.get("guid", fields.get("id", "")),
            "title": fields.get("title", ""), "link": fields.get("link", ""),
            "description": fields.get("description", fields.get("summary", fields.get("encoded", fields.get("content", "")))),
            "original_date": fields.get("pubDate", fields.get("published", fields.get("date", fields.get("updated", "")))),
        })
    return result


def fetch_feed(feed: dict) -> tuple[int, bytes]:
    request = Request(feed["url"], headers={"User-Agent": "RSS-Medallion-Lab/1.0", "Accept": "application/rss+xml, application/xml, text/xml"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except HTTPError as error:
            with error:
                result = error.code, error.read()
            if result[0] not in {429, 500, 502, 503, 504} or attempt == 2:
                return result
        except (URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
        time.sleep(0.5 * 2 ** attempt)


class DisabledEnricher:
    cache_namespace = "disabled-v1"

    def analyze(self, text: str, language: str) -> dict:
        return {"status": "skipped_disabled", "entities": [], "key_phrases": [], "analyzed_at": None}


class ComprehendEnricher:
    def __init__(self, region: str):
        import boto3
        from botocore.config import Config
        self.client = boto3.client("comprehend", region_name=region, config=Config(
            retries={"mode": "standard", "total_max_attempts": 3},
            connect_timeout=10, read_timeout=60))
        self.cache_namespace = f"comprehend-v1-{region}"

    def analyze(self, text: str, language: str, checkpoint=None) -> dict:
        values = {}
        for operation, field in (("detect_entities", "Entities"), ("detect_key_phrases", "KeyPhrases")):
            def invoke(op=operation, result_field=field):
                response = getattr(self.client, op)(Text=text, LanguageCode=language)
                return {"values": response[result_field], "analyzed_at": now()}
            values[field] = checkpoint(operation, invoke) if checkpoint else invoke()
        return {"status": "completed", "entities": values["Entities"]["values"],
                "key_phrases": values["KeyPhrases"]["values"],
                "analyzed_at": max(v["analyzed_at"] for v in values.values())}


def committed_manifest(store, run_id):
    """Find a committed ancestor without confusing prepared validation with a commit."""
    current = read_json(store, CURRENT) if store.exists(CURRENT) else None
    seen = set()
    while current and current["run_id"] not in seen:
        if current["run_id"] == run_id:
            return current
        seen.add(current["run_id"])
        parent = current.get("parent_run_id")
        key = f"_control/runs/{parent}/validated.json" if parent else None
        current = read_json(store, key) if key and store.exists(key) else None
    return None


class Pipeline:
    def __init__(self, store, feeds: list[dict], enricher):
        self.store, self.feeds, self.enricher = store, feeds, enricher
        seen = set()
        if not feeds:
            raise ValueError("Debe configurar al menos una fuente")
        for feed in feeds:
            for field in ("source", "medium", "section", "url", "language"):
                if not isinstance(feed.get(field), str) or not feed[field].strip():
                    raise ValueError(f"Configuración sin {field}")
            canonical_link(feed["url"])
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", feed["source"]) or feed["source"] in seen:
                raise ValueError("source debe ser único y seguro para rutas")
            seen.add(feed["source"])

    def _key(self, run_id, stage):
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", run_id) or run_id in {".", ".."}:
            raise ValueError("run_id no válido")
        return f"_control/runs/{run_id}/{stage}.json"

    def _load(self, run_id, stage):
        return read_json(self.store, self._key(run_id, stage))

    def _saved(self, run_id, stage):
        key = self._key(run_id, stage)
        return read_json(self.store, key) if self.store.exists(key) else None

    def _save(self, run_id, stage, value):
        write_json(self.store, self._key(run_id, stage), value)
        return value

    def ingest(self, run_id: str, fetcher=None) -> dict:
        saved = self._saved(run_id, "ingest")
        if saved is not None:
            return saved
        start = self._saved(run_id, "start")
        if start is None:
            parent = read_json(self.store, CURRENT) if self.store.exists(CURRENT) else None
            start = self._save(run_id, "start", {"ingested_at": now(), "parent": parent, "feeds": self.feeds})
        sources = []
        for feed in start["feeds"]:
            checkpoint = f"source-{feed['source']}"
            previous = self._saved(run_id, checkpoint)
            if previous is not None:
                sources.append(previous)
                continue
            entry = dict(feed, run_id=run_id, ingested_at=start["ingested_at"],
                         http_status=None, content_hash=None, bronze_key=None, item_count=0)
            try:
                status, raw = (fetcher or fetch_feed)(feed)
            except (URLError, TimeoutError, OSError) as error:
                entry.update(status="network_error", error=str(error))
            else:
                entry.update(http_status=status, content_hash=digest(raw))
                if not 200 <= status < 300:
                    entry.update(status="http_error", error=f"HTTP {status}")
                elif not raw.strip():
                    entry.update(status="empty", error="Respuesta vacía")
                else:
                    try:
                        items = parse_feed(raw)
                    except (ET.ParseError, DefusedXmlException, ValueError) as error:
                        entry.update(status="invalid_xml", error=str(error))
                    else:
                        key = (f"bronze/source={feed['source']}/ingestion_date={start['ingested_at'][:10]}"
                               f"/run_id={run_id}/response.xml")
                        self.store.write(key, raw)
                        entry.update(status="success", bronze_key=key, item_count=len(items))
                if entry["status"] != "success":
                    key = f"quarantine/run_id={run_id}/source={feed['source']}/response.bin"
                    self.store.write(key, raw)
                    entry["quarantine_key"] = key
            sources.append(self._save(run_id, checkpoint, entry))
        good = sum(e["status"] == "success" for e in sources)
        return self._save(run_id, "ingest", {
            "run_id": run_id, "ingested_at": start["ingested_at"], "sources": sources,
            "status": "complete" if good == len(sources) else "partial" if good else "failed",
            "parent_run_id": start["parent"]["run_id"] if start["parent"] else None,
        })

    def _read_table(self, manifest, name):
        rows = []
        for key in manifest["tables"][name]["files"]:
            table = pq.ParquetFile(pa.BufferReader(self.store.read(key))).read()
            partition = key.split("publication_date=", 1)[1].split("/", 1)[0]
            for row in table.to_pylist():
                row["publication_date"] = partition
                for field in TABLE_SCHEMAS[name]:
                    if pa.types.is_timestamp(field.type) and row[field.name] is not None:
                        row[field.name] = row[field.name].isoformat()
                rows.append(row)
        return rows

    def transform(self, run_id: str) -> dict:
        saved = self._saved(run_id, "transform")
        if saved is not None:
            return saved
        manifest = self._load(run_id, "ingest")
        if manifest["status"] == "failed":
            raise ValueError("Lote fallido: ninguna fuente RSS válida")
        parent = self._load(run_id, "start")["parent"]
        current = {r["news_id"]: r for r in self._read_table(parent, "news")} if parent else {}
        candidates, rejected = defaultdict(list), []
        metrics = {"received": 0, "new": 0, "updated": 0, "repeated": 0,
                   "duplicates_in_batch": 0, "rejected": 0, "unknown_date": 0}
        for source in manifest["sources"]:
            if source["status"] != "success":
                continue
            raw = self.store.read(source["bronze_key"])
            if digest(raw) != source["content_hash"]:
                raise ValueError("Bronze cambió después de ingesta; use otro run_id para una copia controlada")
            for index, record in enumerate(parse_feed(raw)):
                metrics["received"] += 1
                try:
                    title, description = clean(record["title"]), clean(record["description"])
                    if not title:
                        raise ValueError("missing_title")
                    link = canonical_link(record["link"])
                except ValueError as error:
                    rejected.append({"run_id": run_id, "bronze_key": source["bronze_key"],
                                     "source": source["source"], "item_index": index,
                                     "reason": str(error), "record": record})
                    continue
                published, date, date_status = parse_date(record["original_date"])
                text = "\n".join(part for part in (title, description) if part)
                row = dict(record, title=title, description=description, link=link,
                           news_id=digest(source["medium"] + "\0" + link),
                           medium=source["medium"], section=source["section"], source=source["source"],
                           language=source["language"], published_at=published, publication_date=date,
                           date_status=date_status, analyzed_text=text, text_hash=digest(text),
                           bronze_key=source["bronze_key"], run_id=run_id,
                           first_seen_at=manifest["ingested_at"], last_seen_at=manifest["ingested_at"],
                           analyzed_at=None, enrichment_status="pending", version=1)
                row["content_hash"] = digest(json.dumps([title, description, link, published,
                                                         record["original_date"], source["language"]], ensure_ascii=False))
                candidates[row["news_id"]].append(row)
        for identity, rows in sorted(candidates.items()):
            # One primary section: smallest (section, source); same-feed conflicts
            # prefer newest valid publication time then content hash, independently of XML order.
            rows.sort(key=lambda r: (r["section"], r["source"]))
            primary = (rows[0]["section"], rows[0]["source"])
            row = max((r for r in rows if (r["section"], r["source"]) == primary),
                      key=lambda r: (r["published_at"] or "", r["content_hash"]))
            metrics["duplicates_in_batch"] += len(rows) - 1
            old = current.get(identity)
            if old:
                row["first_seen_at"] = old["first_seen_at"]
                row["version"] = old["version"] + (old["content_hash"] != row["content_hash"])
                metrics["repeated" if old["content_hash"] == row["content_hash"] else "updated"] += 1
            else:
                metrics["new"] += 1
            current[identity] = row
        metrics["rejected"] = len(rejected)
        metrics["unknown_date"] = sum(r["date_status"] != "valid" for r in current.values())
        metrics["current_news"] = len(current)
        quarantine_key = f"quarantine/run_id={run_id}/records.json"
        write_json(self.store, quarantine_key, rejected)
        return self._save(run_id, "transform", {"run_id": run_id, "status": manifest["status"],
            "news": sorted(current.values(), key=lambda r: r["news_id"]),
            "metrics": metrics, "quarantine_key": quarantine_key})

    def _analysis(self, row):
        text, language = row["analyzed_text"], row["language"]
        if not text.strip():
            return {"status": "skipped_empty", "entities": [], "key_phrases": [], "analyzed_at": None}
        if language not in SUPPORTED_LANGUAGES:
            return {"status": "skipped_language", "entities": [], "key_phrases": [], "analyzed_at": None}
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            return {"status": "skipped_too_long", "entities": [], "key_phrases": [], "analyzed_at": None}
        namespace = getattr(self.enricher, "cache_namespace", type(self.enricher).__name__)
        key = f"_control/nlp_cache/{digest(namespace + chr(0) + language + chr(0) + text)}"
        if self.store.exists(key + "/result.json"):
            return read_json(self.store, key + "/result.json")
        def checkpoint(operation, invoke):
            operation_key = key + "/" + operation + ".json"
            if self.store.exists(operation_key):
                return read_json(self.store, operation_key)
            value = invoke()
            write_json(self.store, operation_key, value)
            return value
        if isinstance(self.enricher, ComprehendEnricher):
            result = self.enricher.analyze(text, language, checkpoint=checkpoint)
        else:
            result = self.enricher.analyze(text, language)
        if result["status"] == "completed" and not result.get("analyzed_at"):
            result["analyzed_at"] = now()
        write_json(self.store, key + "/result.json", result)
        return result

    def enrich(self, run_id: str) -> dict:
        saved = self._saved(run_id, "enrich")
        if saved is not None:
            return saved
        transformed = self._load(run_id, "transform")
        news, entities, phrases, statuses = [], [], [], Counter()
        for original in transformed["news"]:
            row = dict(original)
            result = self._analysis(row)
            row.update(enrichment_status=result["status"], analyzed_at=result.get("analyzed_at"))
            statuses[result["status"]] += 1
            dimensions = {k: row[k] for k in ("news_id", "section", "medium", "publication_date")}
            unique = {}
            for entity in result.get("entities", []):
                if entity["Type"] not in {"PERSON", "ORGANIZATION", "LOCATION"}:
                    continue
                identity = (entity["Text"].strip(), entity["Type"])
                if identity[0]:
                    unique[identity] = max(unique.get(identity, 0.0), float(entity["Score"]))
            entities.extend(dict(dimensions, entity=text, entity_type=kind, score=score)
                            for (text, kind), score in sorted(unique.items()))
            unique = {}
            for phrase in result.get("key_phrases", []):
                text = phrase["Text"].strip()
                if text:
                    unique[text] = max(unique.get(text, 0.0), float(phrase["Score"]))
            phrases.extend(dict(dimensions, phrase=text, score=score) for text, score in sorted(unique.items()))
            news.append(row)
        return self._save(run_id, "enrich", {"run_id": run_id,
            "tables": {"news": news, "news_entities": entities, "news_key_phrases": phrases},
            "enrichment_counts": dict(statuses), "metrics": transformed["metrics"]})

    def _write_table(self, run_id, name, rows):
        layer = "silver" if name in SILVER_TABLES else "gold"
        prefix = f"{layer}/snapshots/{run_id}/{name}/"
        groups = defaultdict(list)
        for row in rows:
            groups[row["publication_date"]].append(row)
        # A typed zero-row file preserves schemas for an empty table, without a fake row.
        if not groups:
            groups["1970-01-01"] = []
        schema = pa.schema([f for f in TABLE_SCHEMAS[name] if f.name != "publication_date"])
        files, checksums = [], {}
        for date, partition in sorted(groups.items()):
            prepared = []
            for original in partition:
                row = {f.name: original[f.name] for f in schema}
                for field in schema:
                    if pa.types.is_timestamp(field.type) and row[field.name] is not None:
                        row[field.name] = datetime.fromisoformat(row[field.name])
                prepared.append(row)
            sink = pa.BufferOutputStream()
            pq.write_table(pa.Table.from_pylist(prepared, schema=schema), sink,
                           compression="snappy", version="2.6")
            key = prefix + f"publication_date={date}/part-00000.parquet"
            data = sink.getvalue().to_pybytes()
            self.store.write(key, data)
            files.append(key)
            checksums[key] = digest(data)
        return {"prefix": prefix, "location": self.store.uri(prefix), "files": files,
                "partitions": sorted(groups), "row_count": len(rows), "checksums": checksums}

    def publish_silver(self, run_id: str) -> dict:
        saved = self._saved(run_id, "silver")
        if saved is not None:
            return saved
        enriched = self._load(run_id, "enrich")
        tables = {name: self._write_table(run_id, name, enriched["tables"][name]) for name in SILVER_TABLES}
        return self._save(run_id, "silver", {"run_id": run_id, "tables": tables})

    @staticmethod
    def _aggregate(tables):
        definitions = {
            "daily_news": ("news", ("medium", "section", "publication_date")),
            "entity_daily": ("news_entities", ("entity", "entity_type", "publication_date")),
            "section_phrases": ("news_key_phrases", ("section", "phrase", "publication_date")),
        }
        result = {}
        for name, (source, dimensions) in definitions.items():
            groups = defaultdict(set)
            for row in tables[source]:
                groups[tuple(row[k] for k in dimensions)].add(row["news_id"])
            result[name] = [dict(zip(dimensions, key), news_count=len(identities))
                            for key, identities in sorted(groups.items())]
        return result

    def build_gold(self, run_id: str) -> dict:
        saved = self._saved(run_id, "gold")
        if saved is not None:
            return saved
        silver = self._load(run_id, "silver")
        tables = {name: self._read_table(silver, name) for name in SILVER_TABLES}
        gold = {name: self._write_table(run_id, name, rows)
                for name, rows in self._aggregate(tables).items()}
        return self._save(run_id, "gold", {"run_id": run_id, "tables": gold})

    def validate(self, run_id: str) -> dict:
        ingestion = self._load(run_id, "ingest")
        if ingestion["status"] == "failed":
            raise ValueError("No se publica un lote sin fuentes válidas")
        silver, gold = self._load(run_id, "silver"), self._load(run_id, "gold")
        tables = dict(silver["tables"], **gold["tables"])
        manifest = {"run_id": run_id, "status": ingestion["status"], "tables": tables,
                    "parent_run_id": ingestion["parent_run_id"]}
        loaded = {}
        for name, metadata in tables.items():
            for key, checksum in metadata["checksums"].items():
                if digest(self.store.read(key)) != checksum:
                    raise ValueError(f"Checksum no válido: {key}")
            loaded[name] = self._read_table(manifest, name)
            if len(loaded[name]) != metadata["row_count"]:
                raise ValueError(f"Conteo no válido: {name}")
        news = loaded["news"]
        identities = {r["news_id"] for r in news}
        if len(identities) != len(news):
            raise ValueError("news_id duplicado")
        for row in news:
            if any(not row[k] for k in ("news_id", "title", "link", "medium", "section", "source", "bronze_key", "run_id")):
                raise ValueError("Campos obligatorios ausentes")
            canonical_link(row["link"])
            if row["date_status"] == "valid":
                if not row["published_at"] or datetime.fromisoformat(row["published_at"]).date().isoformat() != row["publication_date"]:
                    raise ValueError("Fecha/partición inconsistente")
            elif row["published_at"] is not None or row["publication_date"] != "1970-01-01":
                raise ValueError("Fecha desconocida sin partición centinela")
        by_id = {r["news_id"]: r for r in news}
        for table, identity_fields in (("news_entities", ("news_id", "entity", "entity_type")),
                                       ("news_key_phrases", ("news_id", "phrase"))):
            seen = set()
            for row in loaded[table]:
                key = tuple(row[f] for f in identity_fields)
                if key in seen or row["news_id"] not in identities:
                    raise ValueError(f"Duplicado o huérfano: {table}")
                seen.add(key)
                if not 0 <= row["score"] <= 1:
                    raise ValueError("Confianza fuera de rango")
                if any(row[k] != by_id[row["news_id"]][k] for k in ("medium", "section", "publication_date")):
                    raise ValueError("Dimensiones de enriquecimiento inconsistentes")
        expected = self._aggregate(loaded)
        for name in GOLD_TABLES:
            normalized = lambda rows: sorted(json.dumps(r, sort_keys=True) for r in rows)
            if normalized(expected[name]) != normalized(loaded[name]):
                raise ValueError(f"Conciliación Gold/Silver fallida: {name}")
        metrics = self._load(run_id, "transform")["metrics"]
        if metrics["received"] != sum(metrics[k] for k in ("new", "updated", "repeated", "duplicates_in_batch", "rejected")):
            raise ValueError("Conteos de entrada no conciliados")
        current = read_json(self.store, CURRENT) if self.store.exists(CURRENT) else None
        if current and current["run_id"] == run_id:
            # A replay never rewinds the pointer, nor mutates an already committed snapshot.
            return current
        historical = committed_manifest(self.store, run_id)
        if historical is not None:
            return historical
        parent = self._load(run_id, "start")["parent"]
        if current != parent:
            raise ValueError("Snapshot padre cambió; serialice las ejecuciones y genere otro lote")
        manifest.update(validated_at=now(), metrics=metrics,
                        enrichment_counts=self._load(run_id, "enrich")["enrichment_counts"])
        # Persist complete recoverable publication record before the single atomic commit.
        self._save(run_id, "validated", manifest)
        write_json(self.store, CURRENT, manifest)
        return manifest
