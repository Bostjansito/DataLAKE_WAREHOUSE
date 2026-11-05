-- Experimento A: sin poda de particiones. Mismo snapshot y workgroup que B.
-- Desactivar ResultReuseConfiguration al enviarla y conservar QueryExecutionId.
-- Leer Statistics.DataScannedInBytes mediante athena get-query-execution.
-- COUNT(title) fuerza lectura de una columna, no sólo metadatos de filas.
SELECT section, COUNT(title) AS noticias_con_titulo
FROM news
GROUP BY section
ORDER BY section;
