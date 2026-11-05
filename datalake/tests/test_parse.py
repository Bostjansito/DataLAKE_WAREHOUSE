"""Pruebas sin AWS de la interpretación, limpieza, validación e identificación."""
from datetime import datetime, timezone

from noticias.ingest import classify_response
from noticias.parse import clean_text, derive_news_id, normalize_key, normalize_link, parse_feed, parse_pubdate

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>T</title>
<item><title>Petro &amp; el <b>Congreso</b></title><pubDate>2026-11-04T18:58:05-05:00</pubDate>
  <link>https://www.eltiempo.com/politica/congreso/nota-3598523?utm_source=rss</link>
  <guid>https://www.eltiempo.com/politica/congreso/nota-3598523</guid>
  <description>&lt;p&gt;Texto   con  HTML&lt;/p&gt;</description></item>
<item><title>Repetida</title><pubDate>Wed, 04 Nov 2026 19:21:39 -0500</pubDate>
  <link>https://www.eltiempo.com/politica/congreso/nota-3598523</link><description>x</description></item>
<item><title></title><link>https://www.eltiempo.com/a-1234567</link></item>
<item><title>Sin enlace</title></item>
<item><title>Enlace raro</title><link>javascript:alert(1)</link></item>
<item><title>Sin fecha</title><link>https://www.eltiempo.com/otra-7654321</link><description>d</description></item>
</channel></rss>"""


def test_clean_text_removes_html_and_entities():
    assert clean_text("<p>Hola&nbsp; <b>mundo</b></p>") == "Hola mundo"
    assert clean_text("&lt;p&gt;Texto   con  HTML&lt;/p&gt;") == "Texto con HTML"
    assert clean_text(None) == ""


def test_normalize_link_drops_tracking_and_fragment():
    assert normalize_link("HTTPS://WWW.ElTiempo.com/a-1234567/?utm_source=x&id=2#top") == \
        "https://www.eltiempo.com/a-1234567?id=2"
    assert normalize_link("javascript:alert(1)") is None
    assert normalize_link("") is None


def test_parse_pubdate_formats_and_invalid_values():
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    iso_dt, status = parse_pubdate("2026-11-04T18:58:05-05:00", now)
    assert status == "ok" and iso_dt == datetime(2026, 11, 4, 23, 58, 5, tzinfo=timezone.utc)
    rfc_dt, status = parse_pubdate("Wed, 04 Nov 2026 19:21:39 -0500", now)
    assert status == "ok" and rfc_dt.hour == 0 and rfc_dt.day == 5
    assert parse_pubdate(None, now) == (None, "missing_date")
    assert parse_pubdate("ayer", now) == (None, "unparseable_date")
    assert parse_pubdate("2030-01-01T00:00:00Z", now) == (None, "future_date")
    assert parse_pubdate("2026-11-04T10:00:00", now)[1] == "naive_assumed_utc"


def test_news_id_prefers_article_number():
    assert derive_news_id("El Tiempo", None, "https://www.eltiempo.com/x/titulo-3598523", "T", None) == \
        ("eltiempo-3598523", "article_id")
    nid, strategy = derive_news_id("El Tiempo", "abc-guid", "https://www.eltiempo.com/sin-numero", "T", None)
    assert strategy == "guid" and nid.startswith("eltiempo-g")


def test_parse_feed_validates_and_identifies():
    valid, rejected = parse_feed(FEED, "El Tiempo")
    assert [r.reasons for r in rejected] == [["missing_title"], ["missing_link"], ["invalid_link"]]
    assert [v.news_id for v in valid] == ["eltiempo-3598523", "eltiempo-3598523", "eltiempo-7654321"]
    first = valid[0]
    assert first.title == "Petro & el Congreso"
    assert first.description == "Texto con HTML"
    assert first.link == "https://www.eltiempo.com/politica/congreso/nota-3598523"
    assert first.published_date == "2026-11-04"
    assert valid[2].published_date == "sin_fecha" and valid[2].date_status == "missing_date"


def test_same_text_same_hash_regardless_of_date():
    valid, _ = parse_feed(FEED, "El Tiempo")
    assert valid[0].analyzed_text == "Petro & el Congreso. Texto con HTML"
    assert valid[0].content_hash != valid[1].content_hash


def test_classify_response():
    assert classify_response(404, b"x")[0] == "http_error"
    assert classify_response(200, b"   ")[0] == "empty_response"
    assert classify_response(200, b"<rss><channel><item>")[0] == "malformed_xml"
    assert classify_response(200, b"<html><body/></html>")[0] == "malformed_xml"
    assert classify_response(200, b"<rss><channel></channel></rss>") == ("empty", None, 0)
    assert classify_response(200, FEED)[0] == "success"


def test_normalize_key():
    assert normalize_key("  Banco de la República. ") == "banco de la republica"
    assert normalize_key("13 Años") == "13 años"
