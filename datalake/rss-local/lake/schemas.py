"""Esquemas públicos; publication_date es partición y no se escribe en Parquet."""
import pyarrow as pa

S = pa.string()
T = pa.timestamp("us", tz="UTC")
TABLE_SCHEMAS = {
    "news": pa.schema([
        ("news_id", S), ("title", S), ("description", S), ("link", S),
        ("medium", S), ("section", S), ("source", S), ("published_at", T),
        ("publication_date", S), ("original_date", S), ("date_status", S),
        ("guid", S), ("first_seen_at", T), ("last_seen_at", T),
        ("version", pa.int64()), ("content_hash", S), ("text_hash", S),
        ("bronze_key", S), ("run_id", S), ("enrichment_status", S),
        ("analyzed_text", S), ("language", S), ("analyzed_at", T),
    ]),
    "news_entities": pa.schema([
        ("news_id", S), ("entity", S), ("entity_type", S), ("score", pa.float64()),
        ("section", S), ("medium", S), ("publication_date", S),
    ]),
    "news_key_phrases": pa.schema([
        ("news_id", S), ("phrase", S), ("score", pa.float64()),
        ("section", S), ("medium", S), ("publication_date", S),
    ]),
    "daily_news": pa.schema([
        ("medium", S), ("section", S), ("news_count", pa.int64()), ("publication_date", S),
    ]),
    "entity_daily": pa.schema([
        ("entity", S), ("entity_type", S), ("news_count", pa.int64()), ("publication_date", S),
    ]),
    "section_phrases": pa.schema([
        ("section", S), ("phrase", S), ("news_count", pa.int64()), ("publication_date", S),
    ]),
}
SILVER_TABLES = ("news", "news_entities", "news_key_phrases")
GOLD_TABLES = ("daily_news", "entity_daily", "section_phrases")
