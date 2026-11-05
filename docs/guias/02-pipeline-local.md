# 02 — Pipeline local

## Objetivo

Ejecutar el pipeline con almacenamiento local antes de habilitar servicios AWS. No necesita bucket, Glue, Athena, EC2 ni llamadas pagas. El enriquecedor local debe identificarse como deshabilitado y no fabricar entidades.

## Procedimiento reproducible

1. Desde la raíz del repositorio, cree un entorno virtual e instale dependencias de desarrollo:

   ```bash
   python -m venv .venv
   . .venv/bin/activate
   python -m pip install -e '.[test]'
   ```

2. Para reproducir el smoke aislado (tests con dependencias opcionales instaladas), ejecute desde la raíz con el entorno virtual activo:

   ```bash
   python scripts/smoke.py
   ```

   El script genera `evidence/local-smoke.json` y `evidence/test-results.xml`, usa fixtures/checkpoints locales, desactiva NLP y fuerza bucket vacío. El smoke no llama a AWS.

3. En las órdenes manuales locales especifique `--bucket '' --enrichment disabled`. Si `LAKE_BUCKET` existe en el entorno, `--root` por sí solo no impide usar S3. Ejecución sintética desconectada:

   ```bash
   rss-lake check --root /tmp/rss-lake-local --bucket '' --enrichment disabled
   rss-lake run --root /tmp/rss-lake-local --bucket '' --enrichment disabled \
     --run-id initial --fixture-dir tests/fixtures/initial
   rss-lake status --root /tmp/rss-lake-local --bucket '' --enrichment disabled
   ```
   `tests/fixtures/initial/` contiene XML sintético, no respuestas de El Tiempo; incluye duplicado y registro inválido. Para consultar feeds reales por HTTPS, omita `--fixture-dir`, conserve las opciones de bucket vacío/NLP deshabilitado y utilice un `run_id` nuevo.


   ```bash
   rss-lake run --root /tmp/rss-lake-local --bucket '' --enrichment disabled --run-id live-01
   ```

   Esta última corrida requiere red al medio, pero no AWS.

4. Para demostrar fallo controlado y recuperación, ejecute el primer comando (debe fallar intencionalmente) y después reintente el mismo lote sin la bandera de fallo:

   ```bash
   rss-lake run --root /tmp/rss-lake-local --bucket '' --enrichment disabled \
     --run-id recovery-01 --fixture-dir tests/fixtures/initial \
     --fail-after publish_silver
   rss-lake run --root /tmp/rss-lake-local --bucket '' --enrichment disabled \
     --run-id recovery-01
   ```

   Los checkpoints evitan volver a descargar las fuentes y las etapas pendientes terminan la publicación local.

5. Para reconstruir desde las respuestas Bronze en un `run_id` destino nuevo, sin HTTP:

   ```bash
   rss-lake run --root /tmp/rss-lake-local --bucket '' --enrichment disabled \
     --run-id rebuild-01 --from-bronze initial
   ```

   El comando referencia las claves Bronze existentes, transforma de nuevo y reutiliza caché. `--replay` sin `--from-bronze` recupera checkpoints del mismo lote; no es reconstrucción. No borre checkpoints de snapshots publicados.

6. Inspeccione `.local-lake/smoke/`, `/tmp/rss-lake-local/`, cuarentena, snapshots Silver/Gold y `_control/current.json`. Registre versión de Python, comandos y salidas reales en `evidence/`.

## Interpretación

El test local prueba código, formatos y persistencia local. No prueba IAM ni integración AWS. El estado `skipped_disabled` significa que no se llamó a Comprehend y no constituye evidencia del servicio. Una ejecución local exitosa no demuestra que Glue haya registrado particiones ni que Athena consulte los datos.

## Evidencia

El orquestador ejecutó 11 pruebas locales, todas aprobadas (`evidence/local-smoke.json`; JUnit XML en `evidence/test-results.xml`). También ejecutó una lectura real de los tres RSS por HTTPS (`evidence/live-feeds.json`): 30 registros recibidos/nuevos, cero rechazos/duplicados/fechas inválidas, estado `complete`; `skipped_disabled` para las 30 noticias significa que no se usó Comprehend. Esto es evidencia local, no prueba de servicios AWS.
