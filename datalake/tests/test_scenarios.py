"""Pruebas sin AWS de las copias controladas y del estado intermedio entre tareas."""
from datetime import datetime

from noticias.jobs import _decode, _encode
from noticias.parse import parse_feed
from noticias.scenarios import mutate

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>T</title>
<item><title>Uno</title><pubDate>2026-11-04T18:58:05-05:00</pubDate>
  <link>https://www.eltiempo.com/politica/uno-3598523</link><description>Texto uno</description></item>
<item><title>Dos</title><pubDate>2026-11-04T17:00:00-05:00</pubDate>
  <link>https://www.eltiempo.com/politica/dos-3598524</link><description>Texto dos</description></item>
</channel></rss>"""


def test_mutate_modificado_changes_text_of_first_and_only_date_of_second():
    before, _ = parse_feed(FEED, "El Tiempo")
    body, changes = mutate(FEED, "modificado", "20261105T120000Z")
    after, rejected = parse_feed(body, "El Tiempo")
    assert not rejected and len(changes) == 2
    assert [a.news_id for a in after] == [b.news_id for b in before]
    assert after[0].analyzed_text_hash != before[0].analyzed_text_hash
    assert after[1].analyzed_text_hash == before[1].analyzed_text_hash
    assert after[1].content_hash != before[1].content_hash
    assert after[1].published_at_utc == before[1].published_at_utc


def test_mutate_defectuosos_adds_known_defects():
    body, _ = mutate(FEED, "defectuosos", "20261105T120000Z")
    valid, rejected = parse_feed(body, "El Tiempo")
    assert [r.reasons for r in rejected] == [["missing_title"], ["missing_link"], ["invalid_link"]]
    dates = {v.news_id: (v.published_date, v.date_status) for v in valid}
    assert dates["eltiempo-9000002"] == ("sin_fecha", "missing_date")
    assert dates["eltiempo-9000003"] == ("sin_fecha", "unparseable_date")
    assert [v.news_id for v in valid].count("eltiempo-3598523") == 2  # duplicado dentro del lote


def test_job_state_roundtrip_keeps_datetimes():
    state = {"news": [{"news_id": "x", "published_at_utc": datetime(2026, 11, 4, 23, 58, 5),
                       "first_seen_at": datetime(2026, 11, 5, 0, 33, 25, 123000), "sections": ["Política"]}],
             "entities": {"x": [{"analyzed_at": None}]}}
    assert _decode(_encode(state)) == state
