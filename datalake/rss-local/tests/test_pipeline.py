"""Controlled RSS and NLP doubles: tests never invoke AWS or assert real NLP results."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.error import URLError

import pytest

from lake import Pipeline, LocalStore, DisabledEnricher
from lake.core import CURRENT, ComprehendEnricher, digest, parse_feed
from lake.storage import read_json, write_json

FEEDS = json.loads(Path("config/feeds.json").read_text())
FIXTURES = Path("tests/fixtures/initial")


def initial(feed):
    return 200, (FIXTURES / f"{feed['source']}.xml").read_bytes()


def rss(items):
    from xml.sax.saxutils import escape
    body = "".join("<item>" + "".join(f"<{k}>{escape(v)}</{k}>" for k, v in row.items()) + "</item>" for row in items)
    return f"<rss version='2.0'><channel><title>Control</title>{body}</channel></rss>".encode()


def article(title="Título", link="https://www.eltiempo.com/lab/new", date="Fri, 23 Oct 2026 09:00:00 -0500"):
    return {"guid": "controlled", "title": title, "link": link, "description": "Descripción Bogotá ONU", "pubDate": date}


class CountingNLP:
    cache_namespace = "test-controlled-nlp-v1"

    def __init__(self):
        self.calls = 0

    def analyze(self, text, language):
        self.calls += 1
        return {"status": "completed", "entities": [
            {"Text": "ONU", "Type": "ORGANIZATION", "Score": .95},
            {"Text": "ONU", "Type": "ORGANIZATION", "Score": .99},
            {"Text": "Bogotá", "Type": "LOCATION", "Score": .98},
            {"Text": "Ana Pérez", "Type": "PERSON", "Score": .93}],
            "key_phrases": [{"Text": "balance", "Score": .91}, {"Text": "balance", "Score": .97}]}


def complete(p, run, fetcher=initial):
    p.ingest(run, fetcher)
    p.transform(run)
    p.enrich(run)
    p.publish_silver(run)
    p.build_gold(run)
    return p.validate(run)


def test_end_to_end_scenarios(tmp_path):
    store, nlp = LocalStore(tmp_path), CountingNLP()
    p = Pipeline(store, FEEDS, nlp)
    first = complete(p, "initial")
    assert first["status"] == "complete"
    assert first["metrics"] == {"received": 6, "new": 4, "updated": 0, "repeated": 0,
        "duplicates_in_batch": 1, "rejected": 1, "unknown_date": 1, "current_news": 4}
    assert nlp.calls == 4
    assert first["tables"]["news_entities"]["row_count"] == 12
    assert first["tables"]["news_key_phrases"]["row_count"] == 4
    assert "1970-01-01" in first["tables"]["news"]["partitions"]
    assert read_json(store, "quarantine/run_id=initial/records.json")[0]["reason"] == "missing_title"
    originals = store.list("bronze/")

    def forbidden(feed):
        raise AssertionError("Replay no debe consultar red")

    replay = complete(p, "initial", forbidden)
    assert replay == first and nlp.calls == 4 and store.list("bronze/") == originals
    second = complete(p, "repeat")
    assert second["metrics"]["repeated"] == 4 and second["metrics"]["new"] == 0
    assert nlp.calls == 4

    def incremental(feed):
        return 200, rss([article()]) if feed["section"] == "politica" else rss([])

    third = complete(p, "incremental", incremental)
    assert third["metrics"]["new"] == 1 and third["tables"]["news"]["row_count"] == 5
    assert "2026-10-23" in third["tables"]["news"]["partitions"] and nlp.calls == 5

    def changed(feed):
        return 200, rss([article("Título cambiado")]) if feed["section"] == "politica" else rss([])

    fourth = complete(p, "changed", changed)
    assert fourth["metrics"]["updated"] == 1 and nlp.calls == 6
    current = p._read_table(fourth, "news")
    assert next(r for r in current if r["title"] == "Título cambiado")["version"] == 2

    def date_only(feed):
        return 200, rss([article("Título cambiado", date="Sat, 24 Oct 2026 09:00:00 -0500")]) if feed["section"] == "politica" else rss([])

    fifth = complete(p, "date-only", date_only)
    assert fifth["metrics"]["updated"] == 1 and nlp.calls == 6
    assert "2026-10-24" in fifth["tables"]["news"]["partitions"]
    assert "2026-10-23" not in fifth["tables"]["news"]["partitions"]

    # Controlled crash after Silver: old pointer stays visible; retry finishes same checkpoint.
    p.ingest("failure", incremental)
    p.transform("failure")
    p.enrich("failure")
    p.publish_silver("failure")
    assert read_json(store, CURRENT)["run_id"] == "date-only"
    resumed = complete(p, "failure", forbidden)
    assert resumed["tables"]["news"]["row_count"] == 5
    assert nlp.calls == 6  # old text reused from durable cache
    assert complete(p, "initial", forbidden) == first
    assert read_json(store, CURRENT)["run_id"] == "failure"

    # Reconstruction in clean store from original Bronze and its ingestion/start manifests.
    restored_store = LocalStore(tmp_path / "restored")
    for key in originals:
        restored_store.write(key, store.read(key))
    for stage in ("ingest", "start"):
        key = f"_control/runs/initial/{stage}.json"
        restored_store.write(key, store.read(key))
    restored = complete(Pipeline(restored_store, FEEDS, DisabledEnricher()), "initial", forbidden)
    assert restored["tables"]["news"]["row_count"] == 4
    assert len(restored_store.list("bronze/")) == 3


def test_partial_failed_http_xml_empty_and_network(tmp_path):
    p = Pipeline(LocalStore(tmp_path), FEEDS, DisabledEnricher())
    responses = {"politica": (503, b"unavailable"), "economia": (200, b"<rss>"), "deportes": initial(FEEDS[2])}
    result = complete(p, "partial", lambda f: responses[f["section"]])
    assert result["status"] == "partial"
    states = {s["status"] for s in read_json(p.store, "_control/runs/partial/ingest.json")["sources"]}
    assert states == {"http_error", "invalid_xml", "success"}
    failed = p.ingest("failed", lambda f: (200, b""))
    assert failed["status"] == "failed" and all(s["status"] == "empty" for s in failed["sources"])
    with pytest.raises(ValueError):
        p.transform("failed")
    def network(feed):
        raise URLError("controlled network failure")
    assert p.ingest("network", network)["sources"][0]["status"] == "network_error"
    empty = complete(p, "valid-empty", lambda f: (200, rss([])))
    assert empty["status"] == "complete" and empty["tables"]["news"]["row_count"] == 1


def test_nlp_explicit_states_and_xml_safety(tmp_path):
    p = Pipeline(LocalStore(tmp_path), FEEDS, DisabledEnricher())
    assert p._analysis({"analyzed_text": "", "language": "es"})["status"] == "skipped_empty"
    assert p._analysis({"analyzed_text": "test", "language": "fr"})["status"] == "skipped_language"
    assert p._analysis({"analyzed_text": "á" * 2501, "language": "es"})["status"] == "skipped_too_long"
    assert p._analysis({"analyzed_text": "test", "language": "es"})["status"] == "skipped_disabled"
    from defusedxml.common import DefusedXmlException
    with pytest.raises(DefusedXmlException):
        parse_feed(b'<!DOCTYPE rss [<!ENTITY secret SYSTEM "file:///etc/passwd">]><rss><channel><item><title>&secret;</title></item></channel></rss>')


def test_comprehend_operation_cache_recovers_failed_second_call(tmp_path):
    class Client:
        entity_calls = 0
        phrase_calls = 0
        def detect_entities(self, **kwargs):
            self.entity_calls += 1
            return {"Entities": []}
        def detect_key_phrases(self, **kwargs):
            self.phrase_calls += 1
            if self.phrase_calls == 1:
                raise RuntimeError("controlled service failure")
            return {"KeyPhrases": []}
    enricher = object.__new__(ComprehendEnricher)
    enricher.client, enricher.cache_namespace = Client(), "comprehend-test"
    p = Pipeline(LocalStore(tmp_path), FEEDS, enricher)
    row = {"analyzed_text": "Texto controlado", "language": "es"}
    with pytest.raises(RuntimeError):
        p._analysis(row)
    assert p._analysis(row)["status"] == "completed"
    assert enricher.client.entity_calls == 1 and enricher.client.phrase_calls == 2


def test_tampering_and_conflicting_parent_rejected(tmp_path):
    store = LocalStore(tmp_path)
    p = Pipeline(store, FEEDS, DisabledEnricher())
    p.ingest("tamper", initial)
    manifest = read_json(store, "_control/runs/tamper/ingest.json")
    store.write(manifest["sources"][0]["bronze_key"], b"tampered")
    with pytest.raises(ValueError, match="Bronze"):
        p.transform("tamper")
    complete(p, "first")
    p.ingest("stale", initial)
    complete(p, "second")
    p.transform("stale"); p.enrich("stale"); p.publish_silver("stale"); p.build_gold("stale")
    with pytest.raises(ValueError, match="padre"):
        p.validate("stale")


def test_storage_path_traversal_rejected(tmp_path):
    store = LocalStore(tmp_path)
    for key in ("../escape", "/absolute", "a/../../escape"):
        with pytest.raises(ValueError):
            store.write(key, b"no")


def test_http_transient_retry_before_terminal_checkpoint(monkeypatch):
    from io import BytesIO
    from urllib.error import HTTPError
    import lake.core as core
    calls, sleeps = [], []
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return rss([])
    def recover(request, timeout):
        calls.append(request.full_url)
        if len(calls) < 3:
            raise HTTPError(request.full_url, 503, "temporary", {}, BytesIO(b"temporary"))
        return Response()
    monkeypatch.setattr(core, "urlopen", recover)
    monkeypatch.setattr(core.time, "sleep", sleeps.append)
    assert core.fetch_feed(FEEDS[0]) == (200, rss([]))
    assert len(calls) == 3 and sleeps == [.5, 1.0]
    calls.clear()
    def permanent(request, timeout):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 404, "missing", {}, BytesIO(b"missing"))
    monkeypatch.setattr(core, "urlopen", permanent)
    assert core.fetch_feed(FEEDS[0]) == (404, b"missing") and len(calls) == 1
