-- Consultas de exploración usadas en las evidencias de las fases 6, 7 y 8.
-- Workgroup: datalake-noticias-lab-wg · Base: datalake_noticias_lab
-- Siempre filtrar por partición (published_date / ingestion_date) para escanear menos.

-- 6.2 Metadatos de un lote de Bronze
SELECT run_id, source_id, http_status, status, items_received,
       content_bytes, substr(content_hash, 1, 16) AS sha256_inicio, bronze_key, ingestion_ts
FROM control_batches
WHERE ingestion_date = '2026-11-05' AND batch_type = 'extraction'
ORDER BY source_id;

-- 7.1 Noticias limpias de Silver
SELECT published_date, section, news_id, id_strategy, substr(title, 1, 55) AS titulo,
       published_at_utc, date_status, version, enrichment_status
FROM silver_news
WHERE published_date = '2026-11-04'
ORDER BY section, news_id
LIMIT 10;

-- 7.3 Entidades de Comprehend (sección Política)
SELECT n.section, e.news_id, e.entity_type, e.entity_text, round(e.score, 4) AS score,
       e.mentions, e.language, e.analyzed_at, substr(e.analyzed_text_hash, 1, 12) AS text_hash
FROM silver_news_entities e
JOIN silver_news n ON n.news_id = e.news_id AND n.published_date = e.published_date
WHERE e.published_date = '2026-11-04' AND n.section = 'Política'
ORDER BY e.news_id, e.entity_type, e.score DESC
LIMIT 12;

-- 7.3 Frases clave de Comprehend (sección Economía)
SELECT n.section, k.news_id, k.key_phrase, k.key_phrase_normalized, round(k.score, 4) AS score
FROM silver_news_key_phrases k
JOIN silver_news n ON n.news_id = k.news_id AND n.published_date = k.published_date
WHERE k.published_date = '2026-11-04' AND n.section = 'Economía'
ORDER BY k.news_id, k.score DESC
LIMIT 12;

-- 8.1 Pregunta 1: noticias por día, medio y sección
SELECT published_date, media, section, news_count, gold_run_id, built_at
FROM gold_news_daily
ORDER BY published_date, section;

-- 8.2 Pregunta 2: entidades en más noticias distintas
SELECT entity_type, entity_text, sum(news_count) AS noticias, count(DISTINCT published_date) AS dias
FROM gold_entity_daily
GROUP BY entity_type, entity_text
ORDER BY noticias DESC, entity_text
LIMIT 12;

-- 8.3 Pregunta 3: frases clave más frecuentes por sección (top 4)
SELECT section, key_phrase, news_count
FROM (
  SELECT section, key_phrase, sum(news_count) AS news_count,
         row_number() OVER (PARTITION BY section ORDER BY sum(news_count) DESC, key_phrase) AS rk
  FROM gold_key_phrases_daily
  GROUP BY section, key_phrase
)
WHERE rk <= 4
ORDER BY section, news_count DESC;
