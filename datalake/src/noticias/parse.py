"""Interpretación del XML de Bronze, limpieza, validación e identificación de noticias."""
from __future__ import annotations

import email.utils
import hashlib
import html
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from defusedxml import ElementTree as SafeET

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
# El Tiempo termina la URL de cada artículo con su identificador numérico: ...-3598523
ARTICLE_ID_RE = re.compile(r"-(\d{6,})/?$")
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|mc_)", re.I)


def clean_text(value: str | None) -> str:
    """Quita etiquetas HTML y entidades, y normaliza espacios."""
    if not value:
        return ""
    text = html.unescape(value)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return SPACE_RE.sub(" ", text).strip()


def normalize_key(value: str) -> str:
    """Minúsculas, sin tildes ni puntuación de borde: clave para agrupar entidades y frases.
    La ñ se conserva porque cambia el significado ("años" no es "anos")."""
    text = unicodedata.normalize("NFC", value.lower()).replace("ñ", "\x00")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).replace("\x00", "ñ")
    text = SPACE_RE.sub(" ", text).strip(" \t\n\"'“”‘’.,;:¡!¿?()[]{}«»-")
    return text


def normalize_link(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def parse_pubdate(raw: str | None, now: datetime | None = None) -> tuple[datetime | None, str]:
    """Convierte la fecha a UTC. Acepta ISO 8601 (ítems) y RFC 822 (canal). Devuelve (fecha, estado)."""
    if not raw or not raw.strip():
        return None, "missing_date"
    value = raw.strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None, "unparseable_date"
    status = "ok"
    if dt.tzinfo is None:
        dt, status = dt.replace(tzinfo=timezone.utc), "naive_assumed_utc"
    dt = dt.astimezone(timezone.utc)
    now = now or datetime.now(timezone.utc)
    if dt > now + timedelta(days=1):
        return None, "future_date"
    if dt.year < 2000:
        return None, "too_old_date"
    return dt, status


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def derive_news_id(media: str, guid: str | None, link: str | None, title: str, published_raw: str | None) -> tuple[str, str]:
    """Estrategia de identificación, de la más estable a la menos estable.

    1. article_id: número de artículo al final del enlace o del GUID (estable aunque cambie el título).
    2. guid: hash del GUID.
    3. link: hash del enlace normalizado.
    4. title_date: hash del título + fecha (último recurso; cambia si se edita el título).
    """
    media_key = normalize_key(media).replace(" ", "")
    for candidate in (link, guid):
        if candidate:
            match = ARTICLE_ID_RE.search(urlsplit(candidate).path if "://" in candidate else candidate)
            if match:
                return f"{media_key}-{match.group(1)}", "article_id"
    if guid:
        return f"{media_key}-g{sha256(guid.strip())[:16]}", "guid"
    if link:
        return f"{media_key}-l{sha256(link)[:16]}", "link"
    return f"{media_key}-t{sha256(normalize_key(title) + '|' + (published_raw or ''))[:16]}", "title_date"


@dataclass
class ParsedItem:
    index: int
    news_id: str
    id_strategy: str
    guid: str | None
    link: str
    title: str
    description: str
    published_at_raw: str | None
    published_at_utc: datetime | None
    date_status: str
    content_hash: str
    analyzed_text: str
    analyzed_text_hash: str

    @property
    def published_date(self) -> str:
        return self.published_at_utc.strftime("%Y-%m-%d") if self.published_at_utc else "sin_fecha"


@dataclass
class Rejected:
    index: int
    reasons: list[str]
    raw: dict = field(default_factory=dict)


def _child_text(item, tag: str) -> str | None:
    """Texto completo del elemento, incluido el que queda dentro de HTML sin escapar (<b>, <p>...)."""
    el = item.find(tag)
    if el is None:
        return None
    text = "".join(el.itertext())
    return text if text.strip() else None


def parse_feed(xml_bytes: bytes, media: str) -> tuple[list[ParsedItem], list[Rejected]]:
    root = SafeET.fromstring(xml_bytes)
    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else []
    valid: list[ParsedItem] = []
    rejected: list[Rejected] = []
    now = datetime.now(timezone.utc)

    for idx, item in enumerate(items):
        raw = {k: _child_text(item, k) for k in ("title", "link", "guid", "pubDate", "description")}
        title = clean_text(raw["title"])
        description = clean_text(raw["description"])
        link = normalize_link(raw["link"])
        guid = (raw["guid"] or "").strip() or None

        reasons = []
        if not title:
            reasons.append("missing_title")
        if not raw["link"]:
            reasons.append("missing_link")
        elif not link:
            reasons.append("invalid_link")
        if reasons:
            rejected.append(Rejected(idx, reasons, raw))
            continue

        published, date_status = parse_pubdate(raw["pubDate"], now)
        news_id, strategy = derive_news_id(media, guid, link, title, raw["pubDate"])
        analyzed_text = f"{title}. {description}".strip() if description else title
        content_hash = sha256(json.dumps([title, description, link, raw["pubDate"]], ensure_ascii=False))
        valid.append(ParsedItem(
            index=idx, news_id=news_id, id_strategy=strategy, guid=guid, link=link, title=title,
            description=description, published_at_raw=raw["pubDate"], published_at_utc=published,
            date_status=date_status, content_hash=content_hash, analyzed_text=analyzed_text,
            analyzed_text_hash=sha256(analyzed_text),
        ))
    return valid, rejected
