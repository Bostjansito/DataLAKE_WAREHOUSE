# Fase 3: AWS Glue Data Catalog.
# Tablas definidas explícitamente (sin crawlers): el esquema es parte del código, no tiene
# costo por DPU y el pipeline registra cada partición nueva con la API de Glue.
#
# Publicación atómica: cada partición apunta a una carpeta versionada por ejecución
#   s3://<bucket>/<capa>/<tabla>/published_date=AAAA-MM-DD/v=<write_id>/   (la partición apunta a la versión vigente)
# El pipeline escribe la carpeta nueva completa y solo al final cambia la ubicación de la
# partición en Glue. Athena nunca ve archivos parciales ni duplicados de una reejecución.

locals {
  parquet_format = {
    input_format   = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    serde          = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    classification = "parquet"
  }

  json_format = {
    input_format   = "org.apache.hadoop.mapred.TextInputFormat"
    output_format  = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
    serde          = "org.openx.data.jsonserde.JsonSerDe"
    classification = "json"
  }

  # Noticias sin fecha de publicación válida van a la partición published_date = 'sin_fecha'.
  date_partition = [{ name = "published_date", type = "string", comment = "Fecha de publicación UTC (AAAA-MM-DD) o 'sin_fecha'" }]

  glue_tables = {
    # ---------------- SILVER ----------------
    silver_news = {
      description = "Silver: una fila por noticia vigente, limpia y enriquecida"
      path        = "silver/news/"
      format      = "parquet"
      partitions  = local.date_partition
      columns = [
        { name = "news_id", type = "string", comment = "Identificador estable: medio + id de artículo, o hash del GUID/enlace" },
        { name = "id_strategy", type = "string", comment = "article_id | guid | link | title_date" },
        { name = "guid", type = "string", comment = "GUID del RSS, si existe" },
        { name = "link", type = "string", comment = "Enlace normalizado" },
        { name = "title", type = "string", comment = "Título sin HTML" },
        { name = "description", type = "string", comment = "Descripción sin HTML" },
        { name = "media", type = "string", comment = "Medio de comunicación" },
        { name = "section", type = "string", comment = "Sección del primer feed donde apareció" },
        { name = "sections", type = "array<string>", comment = "Todas las secciones donde apareció la noticia" },
        { name = "published_at_raw", type = "string", comment = "Fecha original del RSS" },
        { name = "published_at_utc", type = "timestamp", comment = "Fecha de publicación normalizada a UTC" },
        { name = "date_status", type = "string", comment = "ok | missing_date | unparseable_date | future_date | too_old_date | naive_assumed_utc" },
        { name = "content_hash", type = "string", comment = "Hash del contenido de la noticia" },
        { name = "analyzed_text_hash", type = "string", comment = "Hash del texto enviado a Comprehend" },
        { name = "language", type = "string", comment = "Idioma usado en Comprehend" },
        { name = "enrichment_status", type = "string", comment = "ok | reused | empty_text | text_too_long | unsupported_language | error" },
        { name = "version", type = "int", comment = "Versión vigente de la noticia (1 = original)" },
        { name = "first_seen_at", type = "timestamp", comment = "Primera vez que se ingirió" },
        { name = "last_updated_at", type = "timestamp", comment = "Última vez que cambió su contenido" },
        { name = "bronze_run_id", type = "string", comment = "Lote de Bronze de la versión vigente" },
        { name = "bronze_key", type = "string", comment = "Archivo de Bronze de la versión vigente" },
        { name = "silver_run_id", type = "string", comment = "Ejecución que publicó la fila" },
      ]
    }

    silver_news_entities = {
      description = "Silver: una fila por entidad distinta detectada en cada noticia vigente"
      path        = "silver/news_entities/"
      format      = "parquet"
      partitions  = local.date_partition
      columns = [
        { name = "news_id", type = "string", comment = "Noticia asociada" },
        { name = "entity_type", type = "string", comment = "PERSON | ORGANIZATION | LOCATION" },
        { name = "entity_text", type = "string", comment = "Texto de la entidad (forma más frecuente)" },
        { name = "entity_text_normalized", type = "string", comment = "Texto en minúsculas y sin tildes, para agrupar" },
        { name = "score", type = "double", comment = "Máxima confianza devuelta por Comprehend" },
        { name = "mentions", type = "int", comment = "Menciones dentro del texto (no se usa para contar presencia)" },
        { name = "analyzed_text_hash", type = "string", comment = "Hash del texto analizado" },
        { name = "language", type = "string", comment = "Idioma del análisis" },
        { name = "analyzed_at", type = "timestamp", comment = "Fecha del análisis" },
        { name = "silver_run_id", type = "string", comment = "Ejecución que publicó la fila" },
      ]
    }

    silver_news_key_phrases = {
      description = "Silver: una fila por frase clave distinta detectada en cada noticia vigente"
      path        = "silver/news_key_phrases/"
      format      = "parquet"
      partitions  = local.date_partition
      columns = [
        { name = "news_id", type = "string", comment = "Noticia asociada" },
        { name = "key_phrase", type = "string", comment = "Frase clave (forma más frecuente)" },
        { name = "key_phrase_normalized", type = "string", comment = "Frase en minúsculas y sin tildes" },
        { name = "score", type = "double", comment = "Máxima confianza devuelta por Comprehend" },
        { name = "mentions", type = "int", comment = "Menciones dentro del texto" },
        { name = "analyzed_text_hash", type = "string", comment = "Hash del texto analizado" },
        { name = "language", type = "string", comment = "Idioma del análisis" },
        { name = "analyzed_at", type = "timestamp", comment = "Fecha del análisis" },
        { name = "silver_run_id", type = "string", comment = "Ejecución que publicó la fila" },
      ]
    }

    # ---------------- GOLD ----------------
    gold_news_daily = {
      description = "Gold: noticias publicadas por día, medio y sección"
      path        = "gold/news_daily/"
      format      = "parquet"
      partitions  = local.date_partition
      columns = [
        { name = "media", type = "string", comment = "Medio" },
        { name = "section", type = "string", comment = "Sección" },
        { name = "news_count", type = "bigint", comment = "Noticias distintas vigentes" },
        { name = "gold_run_id", type = "string", comment = "Ejecución que construyó la fila" },
        { name = "built_at", type = "timestamp", comment = "Fecha de construcción" },
      ]
    }

    gold_entity_daily = {
      description = "Gold: presencia diaria de cada entidad (noticias distintas que la mencionan)"
      path        = "gold/entity_daily/"
      format      = "parquet"
      partitions  = local.date_partition
      columns = [
        { name = "entity_type", type = "string", comment = "PERSON | ORGANIZATION | LOCATION" },
        { name = "entity_text_normalized", type = "string", comment = "Clave de agrupación" },
        { name = "entity_text", type = "string", comment = "Forma de visualización" },
        { name = "news_count", type = "bigint", comment = "Noticias distintas con la entidad" },
        { name = "gold_run_id", type = "string", comment = "Ejecución que construyó la fila" },
        { name = "built_at", type = "timestamp", comment = "Fecha de construcción" },
      ]
    }

    gold_key_phrases_daily = {
      description = "Gold: frecuencia diaria de frases clave por sección"
      path        = "gold/key_phrases_daily/"
      format      = "parquet"
      partitions  = local.date_partition
      columns = [
        { name = "section", type = "string", comment = "Sección" },
        { name = "key_phrase_normalized", type = "string", comment = "Clave de agrupación" },
        { name = "key_phrase", type = "string", comment = "Forma de visualización" },
        { name = "news_count", type = "bigint", comment = "Noticias distintas con la frase" },
        { name = "gold_run_id", type = "string", comment = "Ejecución que construyó la fila" },
        { name = "built_at", type = "timestamp", comment = "Fecha de construcción" },
      ]
    }

    # ---------------- CUARENTENA ----------------
    quarantine_news = {
      description = "Cuarentena: ítems RSS rechazados, con motivo y referencia a Bronze"
      path        = "quarantine/news/"
      format      = "json"
      partitions  = [{ name = "ingestion_date", type = "string", comment = "Fecha de ingesta UTC (AAAA-MM-DD)" }]
      columns = [
        { name = "run_id", type = "string", comment = "Lote de Bronze de origen" },
        { name = "source_id", type = "string", comment = "Fuente RSS" },
        { name = "bronze_key", type = "string", comment = "Archivo original en Bronze" },
        { name = "item_index", type = "int", comment = "Posición del ítem dentro del RSS" },
        { name = "reasons", type = "array<string>", comment = "Motivos del rechazo" },
        { name = "raw_title", type = "string", comment = "Título original" },
        { name = "raw_link", type = "string", comment = "Enlace original" },
        { name = "raw_guid", type = "string", comment = "GUID original" },
        { name = "raw_pubdate", type = "string", comment = "Fecha original" },
        { name = "raw_description", type = "string", comment = "Descripción original" },
        { name = "quarantined_at", type = "string", comment = "Fecha y hora del rechazo UTC (ISO 8601)" },
      ]
    }

    # ---------------- CONTROL ----------------
    control_batches = {
      description = "Control: registro por lote y fuente con conteos y estado del procesamiento"
      path        = "control/batches/"
      format      = "json"
      partitions  = [{ name = "ingestion_date", type = "string", comment = "Fecha de ingesta UTC (AAAA-MM-DD)" }]
      columns = [
        { name = "run_id", type = "string", comment = "Identificador de la ejecución" },
        { name = "batch_type", type = "string", comment = "extraction | reprocess" },
        { name = "source_id", type = "string", comment = "Fuente RSS" },
        { name = "media", type = "string", comment = "Medio" },
        { name = "section", type = "string", comment = "Sección" },
        { name = "url", type = "string", comment = "URL consultada" },
        { name = "http_status", type = "int", comment = "Estado HTTP" },
        { name = "content_hash", type = "string", comment = "Hash SHA-256 del contenido original" },
        { name = "content_bytes", type = "bigint", comment = "Tamaño de la respuesta" },
        { name = "bronze_key", type = "string", comment = "Ubicación del archivo original en S3" },
        { name = "ingestion_ts", type = "string", comment = "Fecha y hora de ingesta UTC (ISO 8601)" },
        { name = "status", type = "string", comment = "success | empty | http_error | malformed_xml | failed" },
        { name = "error_message", type = "string", comment = "Detalle del error, si aplica" },
        { name = "items_received", type = "int", comment = "Ítems en el RSS" },
        { name = "items_valid", type = "int", comment = "Ítems válidos" },
        { name = "items_rejected", type = "int", comment = "Ítems enviados a cuarentena" },
        { name = "items_duplicate_in_batch", type = "int", comment = "Repetidos dentro del lote" },
        { name = "items_new", type = "int", comment = "Noticias nuevas" },
        { name = "items_updated", type = "int", comment = "Noticias con contenido modificado" },
        { name = "items_unchanged", type = "int", comment = "Noticias ya conocidas sin cambios" },
        { name = "processed_at", type = "string", comment = "Fecha y hora del procesamiento a Silver (UTC)" },
        { name = "processing_run_id", type = "string", comment = "Ejecución de Silver que procesó el lote" },
      ]
    }
  }
}

resource "aws_glue_catalog_database" "data_lake" {
  name        = local.glue_database_name
  description = "Data lake de noticias RSS: tablas Silver, Gold y de control"
}

resource "aws_glue_catalog_table" "tables" {
  for_each = local.glue_tables

  name          = each.key
  database_name = aws_glue_catalog_database.data_lake.name
  description   = each.value.description
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL              = "TRUE"
    classification        = each.value.format == "parquet" ? local.parquet_format.classification : local.json_format.classification
    "parquet.compression" = each.value.format == "parquet" ? "SNAPPY" : null
  }

  dynamic "partition_keys" {
    for_each = each.value.partitions
    content {
      name    = partition_keys.value.name
      type    = partition_keys.value.type
      comment = partition_keys.value.comment
    }
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.bucket}/${each.value.path}"
    input_format  = each.value.format == "parquet" ? local.parquet_format.input_format : local.json_format.input_format
    output_format = each.value.format == "parquet" ? local.parquet_format.output_format : local.json_format.output_format

    ser_de_info {
      serialization_library = each.value.format == "parquet" ? local.parquet_format.serde : local.json_format.serde
      parameters            = each.value.format == "json" ? { "ignore.malformed.json" = "FALSE" } : { "serialization.format" = "1" }
    }

    dynamic "columns" {
      for_each = each.value.columns
      content {
        name    = columns.value.name
        type    = columns.value.type
        comment = columns.value.comment
      }
    }
  }
}
