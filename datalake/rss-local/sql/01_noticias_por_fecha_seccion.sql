-- Ejecutar en el catálogo AwsDataCatalog y base indicada por Terraform.
-- Sustituir fechas/sección por valores presentes en el snapshot vigente.
-- publication_date es STRING ISO y permite poda de particiones.
SELECT news_id, title, link, medium, section, published_at, version,
       enrichment_status
FROM news
WHERE publication_date BETWEEN '2026-10-20' AND '2026-10-22'
  AND section = 'economia'
ORDER BY published_at DESC, news_id;
