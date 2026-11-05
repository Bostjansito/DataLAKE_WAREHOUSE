"""Enriquecimiento con Amazon Comprehend (entidades y frases clave) con caché por hash del texto.

- Un texto ya analizado (mismo hash e idioma) NO se envía de nuevo a Comprehend: se reutiliza el
  resultado guardado en control/comprehend_cache/. Esto también abarata el reprocesamiento desde Bronze.
- Textos vacíos, demasiado largos o en idiomas no contemplados reciben un estado explícito y no se envían.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import boto3

from .settings import iso, utc_now
from .storage import BOTO_CONFIG, S3Store

log = logging.getLogger("noticias.enrich")

ENTITY_TYPES = {"PERSON", "ORGANIZATION", "LOCATION"}
BATCH_SIZE = 25  # máximo de documentos por llamada Batch* de Comprehend


@dataclass
class Doc:
    text_hash: str
    text: str
    language: str


@dataclass
class EnrichStats:
    analyzed: int = 0
    reused: int = 0
    skipped: dict = field(default_factory=dict)
    errors: int = 0
    api_calls: int = 0
    chars_sent: int = 0


def cache_key(language: str, text_hash: str) -> str:
    return f"control/comprehend_cache/language={language}/{text_hash[:2]}/{text_hash}.json"


class Enricher:
    def __init__(self, s3: S3Store, region: str, supported_languages: tuple[str, ...], max_text_bytes: int):
        self.s3 = s3
        self.client = boto3.client("comprehend", region_name=region, config=BOTO_CONFIG)
        self.supported = set(supported_languages)
        self.max_bytes = max_text_bytes
        self.stats = EnrichStats()

    def _skip(self, doc: Doc, status: str) -> dict:
        self.stats.skipped[status] = self.stats.skipped.get(status, 0) + 1
        return {"status": status, "language": doc.language, "analyzed_at": None, "entities": [], "key_phrases": []}

    def enrich(self, docs: list[Doc]) -> dict[str, dict]:
        """Devuelve {text_hash: resultado}. El estado es ok | reused | empty_text | text_too_long |
        unsupported_language | error."""
        results: dict[str, dict] = {}
        pending: list[Doc] = []
        for doc in {d.text_hash: d for d in docs}.values():
            if not doc.text.strip():
                results[doc.text_hash] = self._skip(doc, "empty_text")
            elif doc.language not in self.supported:
                results[doc.text_hash] = self._skip(doc, "unsupported_language")
            elif len(doc.text.encode("utf-8")) > self.max_bytes:
                results[doc.text_hash] = self._skip(doc, "text_too_long")
            elif self.s3.exists(cache_key(doc.language, doc.text_hash)):
                cached = self.s3.get_json(cache_key(doc.language, doc.text_hash))
                results[doc.text_hash] = {**cached, "status": "reused"}
                self.stats.reused += 1
            else:
                pending.append(doc)

        for language in sorted({d.language for d in pending}):
            group = [d for d in pending if d.language == language]
            for i in range(0, len(group), BATCH_SIZE):
                results.update(self._analyze_batch(group[i:i + BATCH_SIZE], language))

        log.info("task=enrich analyzed=%d reused=%d skipped=%s errors=%d api_calls=%d chars_sent=%d",
                 self.stats.analyzed, self.stats.reused, self.stats.skipped, self.stats.errors,
                 self.stats.api_calls, self.stats.chars_sent)
        return results

    def _analyze_batch(self, batch: list[Doc], language: str) -> dict[str, dict]:
        texts = [d.text for d in batch]
        ents = self.client.batch_detect_entities(TextList=texts, LanguageCode=language)
        phrases = self.client.batch_detect_key_phrases(TextList=texts, LanguageCode=language)
        self.stats.api_calls += 2
        self.stats.chars_sent += 2 * sum(len(t) for t in texts)

        failed = {e["Index"] for e in ents.get("ErrorList", [])} | {e["Index"] for e in phrases.get("ErrorList", [])}
        ent_by_idx = {r["Index"]: r["Entities"] for r in ents.get("ResultList", [])}
        kp_by_idx = {r["Index"]: r["KeyPhrases"] for r in phrases.get("ResultList", [])}
        analyzed_at = iso(utc_now())

        out: dict[str, dict] = {}
        for idx, doc in enumerate(batch):
            if idx in failed:
                self.stats.errors += 1
                out[doc.text_hash] = {"status": "error", "language": language, "analyzed_at": analyzed_at,
                                      "entities": [], "key_phrases": []}
                continue
            result = {
                "status": "ok", "language": language, "analyzed_at": analyzed_at, "text_hash": doc.text_hash,
                "entities": [{"type": e["Type"], "text": e["Text"], "score": round(e["Score"], 6)}
                             for e in ent_by_idx.get(idx, []) if e["Type"] in ENTITY_TYPES],
                "key_phrases": [{"text": k["Text"], "score": round(k["Score"], 6)} for k in kp_by_idx.get(idx, [])],
            }
            self.s3.put_json(cache_key(language, doc.text_hash), result)
            self.stats.analyzed += 1
            out[doc.text_hash] = result
        return out
