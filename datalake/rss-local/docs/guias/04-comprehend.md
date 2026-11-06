# 04 — Enriquecimiento con Amazon Comprehend

## Objetivo

Analizar título y descripción RSS con el servicio real y distinguir el resultado AWS del modo local sin servicio.

## Procedimiento de ejecución guiada

1. Confirme autorización de uso, región, idioma admitido y límites de caracteres vigentes en la documentación de [detección de entidades](https://docs.aws.amazon.com/comprehend/latest/dg/how-entities.html) y [frases clave](https://docs.aws.amazon.com/comprehend/latest/dg/how-key-phrases.html).
2. Use solo el texto RSS permitido. No envíe páginas enlazadas ni datos ajenos al conjunto de noticias.
3. Ejecute desde una terminal con AWS CLI/perfil configurado **o** dentro del contenedor Airflow en EC2. Comprobación local de servicios y corrida:

   ```bash
   rss-lake check --bucket BUCKET --region REGION \
     --database rss_lake --workgroup rss-lake --enrichment comprehend
   rss-lake run --bucket BUCKET --region REGION \
     --enrichment comprehend --run-id RUN_ID
   ```

   En EC2, desde `/opt/lake`, use el binario instalado en el contenedor `scheduler` (no existe en el host):

   ```bash
   sudo docker compose --env-file .env -f docker-compose.yml exec scheduler rss-lake check --enrichment comprehend
   sudo docker compose --env-file .env -f docker-compose.yml exec scheduler rss-lake run --enrichment comprehend --run-id RUN_ID
   ```

   Sustituya los valores de ejemplo. `check` confirma acceso a bucket, Glue y workgroup; no llama a Comprehend. El enriquecimiento durante `run` solo analiza textos elegibles que aún no están en caché. Capture manifiesto y estado, sin exponer texto innecesario.
4. Compruebe que el resultado conserva hash del texto, idioma, fecha de análisis, entidades/tipos/confianzas y frases/confianzas según el esquema.
5. Reprocese el mismo texto con un `run_id` nuevo y compare hash/costos: la caché debe evitar nuevas llamadas. Cambie controladamente el texto de una fixture y ejecútela bajo un ID nuevo; solo el nuevo hash requiere análisis.
6. Inspeccione los estados `skipped_empty`, `skipped_too_long` (más de 5000 bytes UTF-8), `skipped_language` (no `es`/`en`) y `skipped_disabled`. Comprehend se omite con estado, no se trunca texto ni se simulan resultados; una respuesta vacía de entidades también puede ser una respuesta válida del servicio.

## Limitaciones

Comprehend detecta menciones, no resuelve alias, no garantiza verdad factual y no comprende el artículo completo. Las puntuaciones de confianza no equivalen a certeza. Mantenga la ruta local marcada como deshabilitada; no cree respuestas de ejemplo que parezcan salidas del servicio.

No se han realizado llamadas facturables desde este trabajo. Las capturas/resultados quedan pendientes de ejecución autorizada. Consulte [costos](../costos.md) y precios vigentes antes de procesar lotes.
