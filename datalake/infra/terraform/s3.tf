# Fase 1: bucket único del data lake.
# Todas las zonas (bronze, silver, gold, quarantine, control, athena-results, tmp)
# son prefijos dentro de este mismo bucket.

locals {
  bucket_name = "${var.project_name}-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
}

resource "aws_s3_bucket" "data_lake" {
  bucket        = local.bucket_name
  force_destroy = var.force_destroy_bucket
}

# Sin ACL: el dueño del bucket es dueño de todos los objetos.
resource "aws_s3_bucket_ownership_controls" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Bucket privado: bloquea cualquier acceso público.
resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Cifrado en reposo con SSE-S3 (sin costo adicional, a diferencia de SSE-KMS).
resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Versionado deshabilitado a propósito: evita pagar por versiones antiguas.
# La recuperación se basa en que Bronze es inmutable y se puede reprocesar.
resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  versioning_configuration {
    status = "Disabled"
  }
}

# Ciclo de vida para minimizar almacenamiento innecesario.
resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    id     = "abortar-cargas-multiparte-incompletas"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  rule {
    id     = "expirar-resultados-athena"
    status = "Enabled"
    filter {
      prefix = "athena-results/"
    }
    expiration {
      days = var.athena_results_retention_days
    }
  }

  rule {
    id     = "expirar-staging-temporal"
    status = "Enabled"
    filter {
      prefix = "tmp/"
    }
    expiration {
      days = var.tmp_retention_days
    }
  }
}

# Solo se permiten conexiones cifradas (HTTPS).
data "aws_iam_policy_document" "data_lake_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    resources = [
      aws_s3_bucket.data_lake.arn,
      "${aws_s3_bucket.data_lake.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  policy = data.aws_iam_policy_document.data_lake_tls_only.json

  depends_on = [aws_s3_bucket_public_access_block.data_lake]
}

# Marcadores vacíos para que cada zona sea visible en la consola desde el inicio.
resource "aws_s3_object" "zone_markers" {
  for_each = toset(var.data_lake_zones)

  bucket       = aws_s3_bucket.data_lake.id
  key          = "${each.value}/"
  content      = ""
  content_type = "application/x-directory"

  depends_on = [aws_s3_bucket_server_side_encryption_configuration.data_lake]
}
