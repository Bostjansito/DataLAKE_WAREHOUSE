-- Experimento B: misma proyección/agregación que A, añadiendo una partición.
-- Usar una fecha con datos; para demostrar reducción deben existir >=2 fechas.
-- Mantener constante el snapshot, workgroup, motor y desactivar result reuse.
-- Comparar Statistics.DataScannedInBytes reales de ambos QueryExecutionId:
-- ahorro_pct = 100 * (bytes_A - bytes_B) / bytes_A, si bytes_A > 0.
-- Los resultados A/B cubren distinto rango; esta prueba compara escaneo, no totales.
-- Una sola partición, tablas vacías o tamaños mínimos pueden no mostrar ahorro.
SELECT section, COUNT(title) AS noticias_con_titulo
FROM news
WHERE publication_date = '2026-10-22'
GROUP BY section
ORDER BY section;
