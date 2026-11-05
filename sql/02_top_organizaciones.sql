-- Una organización cuenta una sola vez por noticia, no por mención textual.
-- No se resuelven alias; la cadena exacta devuelta por Comprehend es la entidad.
SELECT entity AS organizacion, COUNT(DISTINCT news_id) AS noticias_distintas
FROM news_entities
WHERE publication_date BETWEEN '2026-10-20' AND '2026-10-22'
  AND entity_type = 'ORGANIZATION'
GROUP BY entity
ORDER BY noticias_distintas DESC, organizacion
LIMIT 10;
