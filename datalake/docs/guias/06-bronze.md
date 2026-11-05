# Fase 6 – Capa Bronze (extracción de los RSS)

Objetivo: guardar la respuesta original de cada RSS, sin modificarla, con los metadatos del lote, para
poder reprocesar Silver y Gold sin volver a consultar los medios.

## Qué se construye

| Archivo | Para qué |
|---|---|
| [`datalake/config/sources.json`](../../config/sources.json) | Fuentes configurables: id, medio, sección, URL e idioma (agregar una fuente no cambia el código) |
| [`datalake/src/noticias/ingest.py`](../../src/noticias/ingest.py) | Descarga, clasifica la respuesta y escribe en Bronze |
| [`datalake/src/noticias/control.py`](../../src/noticias/control.py) | Registro del lote en `control/batches/` (tabla `control_batches`) |
| [`datalake/scripts/run_local.sh`](../../scripts/run_local.sh) | Ejecuta el pipeline desde WSL (crea el `.venv` con `uv` la primera vez) |

Fuentes usadas: El Tiempo, secciones Política, Economía y Deportes (`https://www.eltiempo.com/rss/<sección>.xml`).

## Organización en S3

```text
bronze/source=<fuente>/ingestion_date=<AAAA-MM-DD>/run_id=<AAAAMMDDTHHMMSSZ>/
    feed.xml          ← bytes exactos devueltos por el RSS
    _manifest.json    ← se escribe al final: marca el lote como completo
control/batches/ingestion_date=<fecha>/<run_id>__<fuente>.json
control/runs/run_id=<run_id>/extract.json
```

- **Inmutable:** la política IAM del pipeline niega `s3:DeleteObject` sobre `bronze/*`. Un nuevo lote nunca
  sobrescribe otro, porque cada uno tiene su `run_id`.
- **Idempotente:** si se repite una extracción con el mismo `run_id` y ya existe el manifiesto, se reutiliza
  y no se vuelve a escribir.
- **Metadatos:** run_id, fuente, URL, estado HTTP, SHA-256 del contenido, bytes, ruta en S3, fecha UTC, estado
  e ítems recibidos.

## Clasificación de la respuesta

| Estado | Cuándo |
|---|---|
| `success` | HTTP 2xx y XML RSS válido con ítems |
| `empty` | XML válido pero sin `<item>` |
| `http_error` | Código distinto de 2xx o error de red |
| `empty_response` | Cuerpo vacío |
| `malformed_xml` | No se puede interpretar como XML o no es un RSS |

El lote queda **complete** (todas las fuentes OK), **partial** (al menos una falló) o **failed** (ninguna).
Que falle una fuente no detiene a las demás.

## Cómo ejecutar

```bash
cd ~/INGDATA/dataLAKE_WAREHOUSE
datalake/scripts/run_local.sh test       # pruebas unitarias sin AWS
datalake/scripts/run_local.sh extract    # nueva extracción, run_id automático
datalake/scripts/run_local.sh extract --source eltiempo_politica   # una sola fuente
```

Las credenciales salen del perfil local de AWS. En EC2 (Fase 5) salen del rol `datalake-noticias-lab-airflow-ec2`.

## Qué revisar en la consola de AWS

1. **S3 → bucket → `bronze/`:** una carpeta por fuente; dentro, `ingestion_date=…/run_id=…/` con `feed.xml`
   y `_manifest.json`.
2. **Athena:** los metadatos del lote se consultan en `control_batches`. La consulta está en
   [`datalake/sql/01_exploracion.sql`](../../sql/01_exploracion.sql).

## Costo

Solo hay PUT/GET a S3, unos 13 KB por feed: fracciones de centavo.

## Evidencias

Ver [EVIDENCIAS.md – sección 6](../../evidencias/docEVIDENCIA/EVIDENCIAS.md#6-capa-bronze).
