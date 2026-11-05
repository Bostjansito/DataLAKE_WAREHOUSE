# Fase 3 – AWS Glue Data Catalog

Objetivo: registrar las tablas de Silver, Gold y control para poder consultarlas con Athena.

## Qué se crea

Archivo: [`datalake/infra/terraform/glue.tf`](../../infra/terraform/glue.tf)

Base de datos: **`datalake_noticias_lab`**

| Tabla | Capa | Formato | Ubicación | Partición | Granularidad |
|---|---|---|---|---|---|
| `silver_news` | Silver | Parquet | `silver/news/` | `published_date` | Una fila por noticia vigente |
| `silver_news_entities` | Silver | Parquet | `silver/news_entities/` | `published_date` | Una fila por entidad distinta en cada noticia vigente |
| `silver_news_key_phrases` | Silver | Parquet | `silver/news_key_phrases/` | `published_date` | Una fila por frase clave distinta en cada noticia vigente |
| `gold_news_daily` | Gold | Parquet | `gold/news_daily/` | `published_date` | Día × medio × sección |
| `gold_entity_daily` | Gold | Parquet | `gold/entity_daily/` | `published_date` | Día × entidad |
| `gold_key_phrases_daily` | Gold | Parquet | `gold/key_phrases_daily/` | `published_date` | Día × sección × frase clave |
| `control_batches` | Control | JSON | `control/batches/` | `ingestion_date` | Una fila por lote y fuente |

Las columnas, tipos y comentarios de cada tabla están en `glue.tf` y se ven en la consola de Glue.
Son la base del diccionario de datos.

### Partición por fecha

- `published_date` (texto `AAAA-MM-DD`) es la fecha de publicación en UTC. Las consultas del taller filtran
  por fecha, así que Athena solo lee las carpetas de los días pedidos.
- **Noticias sin fecha válida:** van a la partición `published_date = 'sin_fecha'`. No se descartan y no se
  mezclan con días reales; Gold las reporta aparte.

## Cómo se actualizan los metadatos (particiones nuevas)

Se usan **tablas explícitas en lugar de crawlers**:

1. El esquema queda versionado en Terraform; un crawler podría inferir tipos distintos según los datos.
2. No hay costo por DPU de crawler.
3. **Publicación atómica:** cada ejecución escribe una carpeta nueva y completa
   (`…/published_date=2026-11-04/run_id=<id>/`). Cuando termina, el DAG registra o actualiza la
   partición en Glue (`BatchCreatePartition` / `BatchUpdatePartition`) para que apunte a esa carpeta.
   Athena solo ve la versión anterior completa o la nueva completa, nunca archivos a medio escribir ni
   duplicados de una reejecución.
4. Las carpetas de versiones anteriores se pueden borrar después; no afectan las consultas porque ninguna
   partición apunta a ellas.

> Un crawler no reemplaza las validaciones de calidad ni las transformaciones: solo describe archivos.

## Qué hacer con Terraform

```bash
cd datalake/infra
./scripts/tf_apply_evidencia.sh 03-glue aws_glue_catalog_database.data_lake aws_glue_catalog_table.tables
# Plan: 8 to add -> Apply complete! Resources: 8 added
```

Verificación por CLI:

```bash
aws glue get-tables --database-name datalake_noticias_lab \
  --query 'TableList[].[Name,StorageDescriptor.Location,PartitionKeys[0].Name]' --output table
```

## Qué revisar en la consola de AWS

1. **AWS Glue → Data Catalog → Databases → `datalake_noticias_lab`:** 7 tablas, 6 en Parquet y 1 en JSON.
2. **Tabla `silver_news`:** ubicación en S3, clasificación Parquet, 21 columnas con comentario y la
   partición `published_date`.
3. **Pestaña Partitions:** vacía hasta que el pipeline cargue datos (Fases 7 y 8).

## Costo

Glue Data Catalog es gratis hasta 1 millón de objetos (tablas y particiones) y 1 millón de solicitudes al mes.
Este laboratorio queda muy por debajo.

## Evidencias

Ver [EVIDENCIAS.md – sección 3](../../evidencias/docEVIDENCIA/EVIDENCIAS.md#3-aws-glue-data-catalog).
