-- Incluye días sin presencia (cero); LAG compara días consecutivos del calendario.
-- Ajustar las dos fechas y el nombre/tipo exactos de la entidad.
WITH calendario AS (
    SELECT CAST(dia AS varchar) AS publication_date
    FROM UNNEST(sequence(DATE '2026-10-20', DATE '2026-10-22', INTERVAL '1' DAY)) AS t(dia)
), presencia AS (
    SELECT publication_date, SUM(news_count) AS noticias
    FROM entity_daily
    WHERE publication_date BETWEEN '2026-10-20' AND '2026-10-22'
      AND entity = 'Colombia'
      AND entity_type = 'LOCATION'
    GROUP BY publication_date
), serie AS (
    SELECT c.publication_date, COALESCE(p.noticias, 0) AS noticias
    FROM calendario c
    LEFT JOIN presencia p ON c.publication_date = p.publication_date
)
SELECT publication_date, noticias,
       noticias - LAG(noticias) OVER (ORDER BY publication_date) AS cambio_diario
FROM serie
ORDER BY publication_date;
