-- Consultas entregables del taller (sección 4.4 "Consumo con Athena" y 4.5 "Calidad").
-- Workgroup: datalake-noticias-lab-wg · Base: datalake_noticias_lab
-- Las tablas están particionadas por published_date (Silver/Gold) o ingestion_date (control, cuarentena):
-- filtrar por la partición hace que Athena lea solo esas carpetas.

-- 10.1 Noticias por fecha y sección (detalle desde Silver, versión vigente)
SELECT published_date, section, count(*) AS noticias,
       array_join(slice(array_agg(substr(title, 1, 60) ORDER BY published_at_utc DESC), 1, 3), ' | ') AS ultimas
FROM silver_news
WHERE published_date BETWEEN '2026-11-04' AND '2026-11-05'
GROUP BY published_date, section
ORDER BY published_date, section;

-- 10.2 Las diez organizaciones presentes en más noticias (noticias distintas, no menciones)
SELECT entity_text AS organizacion, sum(news_count) AS noticias, count(DISTINCT published_date) AS dias
FROM gold_entity_daily
WHERE entity_type = 'ORGANIZATION'
GROUP BY entity_text
ORDER BY noticias DESC, organizacion
LIMIT 10;

-- 10.3 Presencia de una entidad entre días (con variación contra el día anterior)
WITH dias AS (
  SELECT DISTINCT published_date FROM gold_news_daily WHERE published_date <> 'sin_fecha'
),
entidad AS (
  SELECT published_date, sum(news_count) AS noticias
  FROM gold_entity_daily
  WHERE entity_text_normalized = 'gobierno'
  GROUP BY published_date
),
total AS (
  SELECT published_date, sum(news_count) AS total_noticias FROM gold_news_daily GROUP BY published_date
)
SELECT d.published_date, coalesce(e.noticias, 0) AS noticias_con_entidad, t.total_noticias,
       round(100.0 * coalesce(e.noticias, 0) / t.total_noticias, 1) AS pct_del_dia,
       coalesce(e.noticias, 0) - lag(coalesce(e.noticias, 0)) OVER (ORDER BY d.published_date) AS variacion
FROM dias d
JOIN total t ON t.published_date = d.published_date
LEFT JOIN entidad e ON e.published_date = d.published_date
ORDER BY d.published_date;

-- 10.4 Frases clave más frecuentes por sección (top 5)
SELECT section, key_phrase, news_count
FROM (
  SELECT section, key_phrase, sum(news_count) AS news_count,
         row_number() OVER (PARTITION BY section ORDER BY sum(news_count) DESC, key_phrase) AS rk
  FROM gold_key_phrases_daily
  GROUP BY section, key_phrase
)
WHERE rk <= 5
ORDER BY section, news_count DESC;

-- 10.5 Conciliación de Gold contra Silver (debe devolver diferencia = 0 en todas las filas)
WITH s AS (
  SELECT published_date, media, section, count(DISTINCT news_id) AS silver
  FROM silver_news GROUP BY 1, 2, 3
),
g AS (
  SELECT published_date, media, section, sum(news_count) AS gold
  FROM gold_news_daily GROUP BY 1, 2, 3
)
SELECT coalesce(s.published_date, g.published_date) AS published_date,
       coalesce(s.section, g.section) AS section,
       coalesce(s.silver, 0) AS silver, coalesce(g.gold, 0) AS gold,
       coalesce(s.silver, 0) - coalesce(g.gold, 0) AS diferencia
FROM s FULL OUTER JOIN g
  ON s.published_date = g.published_date AND s.media = g.media AND s.section = g.section
ORDER BY 1, 2;

-- 10.6 Escaneo CON filtro de partición (lee solo la carpeta de una fecha)
SELECT section, count(*) AS frases
FROM silver_news_key_phrases k
JOIN silver_news n ON n.news_id = k.news_id AND n.published_date = k.published_date
WHERE k.published_date = '2026-11-05' AND n.published_date = '2026-11-05'
GROUP BY section;

-- 10.7 La misma consulta SIN filtro de partición (lee todas las fechas)
SELECT section, count(*) AS frases
FROM silver_news_key_phrases k
JOIN silver_news n ON n.news_id = k.news_id AND n.published_date = k.published_date
GROUP BY section;

-- 7.2 / 11.2 Cuarentena: rechazos con motivo y trazabilidad hasta Bronze
SELECT ingestion_date, run_id, source_id, item_index, reasons,
       coalesce(raw_title, '(vacío)') AS titulo, coalesce(raw_link, '(sin enlace)') AS enlace, bronze_key
FROM quarantine_news
WHERE ingestion_date = '2026-11-05'
ORDER BY run_id, item_index;

-- 11.x Conteos por lote: recibidos vs noticias únicas (nuevas, actualizadas, sin cambios, rechazadas)
SELECT run_id, batch_type, source_id, status, items_received AS recibidos, items_rejected AS rechazados,
       items_duplicate_in_batch AS repetidos_lote, items_new AS nuevas, items_updated AS actualizadas,
       items_unchanged AS sin_cambios, processing_run_id
FROM control_batches
WHERE ingestion_date = '2026-11-05'
ORDER BY run_id, source_id, batch_type;

-- 11.5 Versiones de una noticia modificada (la vigente tiene la versión más alta)
SELECT news_id, version, bronze_run_id, silver_run_id, enrichment_status,
       substr(description, length(description) - 80) AS final_descripcion
FROM silver_news
WHERE version > 1
ORDER BY news_id;
