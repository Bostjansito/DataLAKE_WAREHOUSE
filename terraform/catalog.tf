locals {
  # publication_date pertenece exclusivamente a partition_keys, no al Parquet.
  table_schemas = {
    news = {
      layer = "silver"
      columns = [
        { name = "news_id", type = "string" },
        { name = "title", type = "string" },
        { name = "description", type = "string" },
        { name = "link", type = "string" },
        { name = "medium", type = "string" },
        { name = "section", type = "string" },
        { name = "source", type = "string" },
        { name = "published_at", type = "timestamp" },
        { name = "original_date", type = "string" },
        { name = "first_seen_at", type = "timestamp" },
        { name = "last_seen_at", type = "timestamp" },
        { name = "version", type = "bigint" },
        { name = "content_hash", type = "string" },
        { name = "text_hash", type = "string" },
        { name = "bronze_key", type = "string" },
        { name = "run_id", type = "string" },
        { name = "enrichment_status", type = "string" },
        { name = "analyzed_text", type = "string" },
        { name = "language", type = "string" },
        { name = "analyzed_at", type = "timestamp" },
        { name = "date_status", type = "string" },
        { name = "guid", type = "string" }
      ]
    }
    news_entities = {
      layer = "silver"
      columns = [
        { name = "news_id", type = "string" },
        { name = "entity", type = "string" },
        { name = "entity_type", type = "string" },
        { name = "score", type = "double" },
        { name = "section", type = "string" },
        { name = "medium", type = "string" }
      ]
    }
    news_key_phrases = {
      layer = "silver"
      columns = [
        { name = "news_id", type = "string" },
        { name = "phrase", type = "string" },
        { name = "score", type = "double" },
        { name = "section", type = "string" },
        { name = "medium", type = "string" }
      ]
    }
    daily_news = {
      layer = "gold"
      columns = [
        { name = "medium", type = "string" },
        { name = "section", type = "string" },
        { name = "news_count", type = "bigint" }
      ]
    }
    entity_daily = {
      layer = "gold"
      columns = [
        { name = "entity", type = "string" },
        { name = "entity_type", type = "string" },
        { name = "news_count", type = "bigint" }
      ]
    }
    section_phrases = {
      layer = "gold"
      columns = [
        { name = "section", type = "string" },
        { name = "phrase", type = "string" },
        { name = "news_count", type = "bigint" }
      ]
    }
  }
}

resource "aws_glue_catalog_database" "lake" {
  name        = var.glue_database_name
  description = "Noticias RSS: snapshots vigentes Silver y Gold."
}

resource "aws_glue_catalog_table" "lake" {
  for_each      = local.table_schemas
  name          = each.key
  database_name = aws_glue_catalog_database.lake.name
  table_type    = "EXTERNAL_TABLE"
  parameters = {
    EXTERNAL       = "TRUE"
    classification = "parquet"
  }
  partition_keys {
    name = "publication_date"
    type = "string"
  }
  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lake.bucket}/${each.value.layer}/snapshots/unpublished/${each.key}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }
    dynamic "columns" {
      for_each = each.value.columns
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
  lifecycle {
    # lake.catalog cambia la ubicación al publicar; Terraform conserva el esquema.
    # Las particiones son recursos runtime: NO declararlas con aws_glue_partition.
    ignore_changes = [storage_descriptor[0].location, parameters]
  }
}

resource "aws_athena_workgroup" "lake" {
  name          = var.project_name
  force_destroy = true
  configuration {
    enforce_workgroup_configuration    = true
    bytes_scanned_cutoff_per_query     = var.athena_scan_limit_bytes
    publish_cloudwatch_metrics_enabled = false
    engine_version {
      selected_engine_version = "Athena engine version 3"
    }
    result_configuration {
      output_location       = "s3://${aws_s3_bucket.lake.bucket}/athena-results/"
      expected_bucket_owner = data.aws_caller_identity.current.account_id
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
