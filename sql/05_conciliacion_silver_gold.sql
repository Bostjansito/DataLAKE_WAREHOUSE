-- Resultado esperado: CERO filas. Ejecutar sin escritores concurrentes y después
-- de catalog sync completo. Incluye fecha centinela 1970-01-01: no perder rechazos
-- de fecha en las métricas. No confundir cero noticias con enriquecimiento omitido.
-- Se contrastan las tres agregaciones con COUNT(DISTINCT news_id), no COUNT(*).
WITH silver AS (
    SELECT 'daily_news' AS tabla, publication_date,
           medium AS clave_1, section AS clave_2,
           COUNT(DISTINCT news_id) AS noticias
    FROM news
    GROUP BY publication_date, medium, section
    UNION ALL
    SELECT 'entity_daily', publication_date, entity, entity_type,
           COUNT(DISTINCT news_id)
    FROM news_entities
    GROUP BY publication_date, entity, entity_type
    UNION ALL
    SELECT 'section_phrases', publication_date, section, phrase,
           COUNT(DISTINCT news_id)
    FROM news_key_phrases
    GROUP BY publication_date, section, phrase
), gold AS (
    SELECT 'daily_news' AS tabla, publication_date,
           medium AS clave_1, section AS clave_2,
           SUM(news_count) AS noticias, COUNT(*) AS filas_clave
    FROM daily_news
    GROUP BY publication_date, medium, section
    UNION ALL
    SELECT 'entity_daily', publication_date, entity, entity_type,
           SUM(news_count), COUNT(*)
    FROM entity_daily
    GROUP BY publication_date, entity, entity_type
    UNION ALL
    SELECT 'section_phrases', publication_date, section, phrase,
           SUM(news_count), COUNT(*)
    FROM section_phrases
    GROUP BY publication_date, section, phrase
)
SELECT COALESCE(s.tabla, g.tabla) AS tabla,
       COALESCE(s.publication_date, g.publication_date) AS publication_date,
       COALESCE(s.clave_1, g.clave_1) AS clave_1,
       COALESCE(s.clave_2, g.clave_2) AS clave_2,
       s.noticias AS silver_noticias_distintas,
       g.noticias AS gold_noticias,
       g.filas_clave AS gold_filas_clave,
       COALESCE(g.noticias, 0) - COALESCE(s.noticias, 0) AS diferencia
FROM silver s
FULL OUTER JOIN gold g
  ON s.tabla = g.tabla
 AND s.publication_date = g.publication_date
 AND s.clave_1 IS NOT DISTINCT FROM g.clave_1
 AND s.clave_2 IS NOT DISTINCT FROM g.clave_2
WHERE s.noticias IS NULL OR g.noticias IS NULL
   OR s.noticias <> g.noticias OR g.filas_clave <> 1
ORDER BY tabla, publication_date, clave_1, clave_2;
