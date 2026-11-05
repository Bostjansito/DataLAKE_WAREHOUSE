# Fase 4: workgroup de Athena.
# - Resultados en el mismo bucket (athena-results/, expiran a los 7 días).
# - Configuración forzada: ningún usuario puede cambiar la ubicación ni quitar el límite.
# - Límite de bytes escaneados por consulta para evitar consultas costosas por error.

resource "aws_athena_workgroup" "data_lake" {
  name          = local.athena_workgroup_name
  description   = "Consultas del data lake de noticias"
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.athena_bytes_scanned_cutoff

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }

    result_configuration {
      output_location = "s3://${aws_s3_bucket.data_lake.bucket}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
