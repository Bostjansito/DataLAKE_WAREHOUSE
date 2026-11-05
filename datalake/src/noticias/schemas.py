"""Esquemas Parquet de Silver y Gold. Deben coincidir con las columnas de glue.tf
(la columna de partición published_date no va dentro del archivo)."""
import pyarrow as pa

TS = pa.timestamp("ms")

SILVER_NEWS = pa.schema([
    ("news_id", pa.string()), ("id_strategy", pa.string()), ("guid", pa.string()), ("link", pa.string()),
    ("title", pa.string()), ("description", pa.string()), ("media", pa.string()), ("section", pa.string()),
    ("sections", pa.list_(pa.string())), ("published_at_raw", pa.string()), ("published_at_utc", TS),
    ("date_status", pa.string()), ("content_hash", pa.string()), ("analyzed_text_hash", pa.string()),
    ("language", pa.string()), ("enrichment_status", pa.string()), ("version", pa.int32()),
    ("first_seen_at", TS), ("last_updated_at", TS), ("bronze_run_id", pa.string()),
    ("bronze_key", pa.string()), ("silver_run_id", pa.string()),
])

SILVER_ENTITIES = pa.schema([
    ("news_id", pa.string()), ("entity_type", pa.string()), ("entity_text", pa.string()),
    ("entity_text_normalized", pa.string()), ("score", pa.float64()), ("mentions", pa.int32()),
    ("analyzed_text_hash", pa.string()), ("language", pa.string()), ("analyzed_at", TS),
    ("silver_run_id", pa.string()),
])

SILVER_KEY_PHRASES = pa.schema([
    ("news_id", pa.string()), ("key_phrase", pa.string()), ("key_phrase_normalized", pa.string()),
    ("score", pa.float64()), ("mentions", pa.int32()), ("analyzed_text_hash", pa.string()),
    ("language", pa.string()), ("analyzed_at", TS), ("silver_run_id", pa.string()),
])

GOLD_NEWS_DAILY = pa.schema([
    ("media", pa.string()), ("section", pa.string()), ("news_count", pa.int64()),
    ("gold_run_id", pa.string()), ("built_at", TS),
])

GOLD_ENTITY_DAILY = pa.schema([
    ("entity_type", pa.string()), ("entity_text_normalized", pa.string()), ("entity_text", pa.string()),
    ("news_count", pa.int64()), ("gold_run_id", pa.string()), ("built_at", TS),
])

GOLD_KEY_PHRASES_DAILY = pa.schema([
    ("section", pa.string()), ("key_phrase_normalized", pa.string()), ("key_phrase", pa.string()),
    ("news_count", pa.int64()), ("gold_run_id", pa.string()), ("built_at", TS),
])

SILVER_TABLES = {
    "silver_news": ("silver/news", SILVER_NEWS),
    "silver_news_entities": ("silver/news_entities", SILVER_ENTITIES),
    "silver_news_key_phrases": ("silver/news_key_phrases", SILVER_KEY_PHRASES),
}

GOLD_TABLES = {
    "gold_news_daily": ("gold/news_daily", GOLD_NEWS_DAILY),
    "gold_entity_daily": ("gold/entity_daily", GOLD_ENTITY_DAILY),
    "gold_key_phrases_daily": ("gold/key_phrases_daily", GOLD_KEY_PHRASES_DAILY),
}
