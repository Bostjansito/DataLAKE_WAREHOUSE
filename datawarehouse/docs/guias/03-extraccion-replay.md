# 03 · Extracción S3 y replay

[Índice](../guia-operacion.md) · [Evidencias](../../evidencias/docEVIDENCIA/EVIDENCIAS.md)

Cada entidad se guarda como **CSV con cabecera**, incluso DocumentDB: `reviews` y `navigation_events` contienen columnas aplanadas y `document_json` con el documento serializado. Esto permite COPY CSV en Redshift sin perder la representación documental. MySQL exporta `customers`, `products`, `orders`, `order_items`. Las claves son `raw/<fuente>/<entidad>/batch_id=<id>/<uuid>/data.csv` y `raw/<fuente>/batch_id=<id>/manifest.json`; cada fuente publica su manifiesto con fecha, lote, selección, columnas, conteos, bytes y checksum.

El lote 0 captura todas las filas. N=1..365 captura dimensiones completas y los tres IDs de hechos producidos por `append --batch-id N`; no es un extractor genérico por watermark. El manifiesto publicado se reutiliza y su escritura condicional evita reemplazarlo silenciosamente; una captura interrumpida puede dejar payloads no publicados. Los datos de ambos manifiestos y sus objetos deben permanecer para replay.

Tras seed y con toda la infraestructura funcionando, desde EC2:

```bash
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli pipeline --batch-id 0
# Tras append del lote 1 y, si corresponde, simulate-changes ANTES de la captura:
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli pipeline --batch-id 1
# Recuperación de un lote ya capturado, sin consultar fuentes:
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli pipeline --batch-id 1 --replay
```

`--replay` necesita ambos manifiestos, S3 y Redshift; no crea una captura faltante. Un lote `pending` se recupera sin volver a fuentes incluso sin `--replay`. Un lote `succeeded` es no-op: no consulta fuentes ni vuelve a mutar el warehouse. No disparar lotes simultáneos; terminar el pendiente antes del siguiente.

Guardar rutas y manifiestos reales como salidas textuales reproducibles, sin contenido sensible; no requieren imagen adicional. Pausar y esperar confirmación de la evidencia de extracción. Mantener el bucket mientras se necesiten replay o evidencia; después de confirmar, retirar únicamente recursos propios innecesarios según [retiro](07-retiro-dependencias.md) y delegar publicación de fase a free-worker.
