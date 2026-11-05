# Fase 2: rol IAM que usará la instancia EC2 de Airflow.
# Principio de mínimo privilegio: solo el bucket del data lake, la base de datos de Glue
# del proyecto, el workgroup de Athena y las operaciones síncronas de Comprehend.

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "airflow_ec2" {
  name               = "${local.name_prefix}-airflow-ec2"
  description        = "Rol de la instancia EC2 que ejecuta Airflow para el data lake de noticias"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

locals {
  # Zonas en las que el pipeline puede escribir, sobrescribir y borrar.
  mutable_zones = ["silver", "gold", "quarantine", "control", "athena-results", "tmp"]
}

data "aws_iam_policy_document" "airflow_pipeline" {
  statement {
    sid       = "S3ListarBucket"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation", "s3:ListBucketMultipartUploads"]
    resources = [aws_s3_bucket.data_lake.arn]
  }

  statement {
    sid = "S3ZonasMutables"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [for z in local.mutable_zones : "${aws_s3_bucket.data_lake.arn}/${z}/*"]
  }

  # Bronze conserva los datos originales: se puede leer y agregar lotes, pero no borrar.
  statement {
    sid       = "S3BronzeSoloAgregarYLeer"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.data_lake.arn}/bronze/*"]
  }

  statement {
    sid       = "S3BronzeSinBorrado"
    effect    = "Deny"
    actions   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${aws_s3_bucket.data_lake.arn}/bronze/*"]
  }

  # Código del pipeline publicado por Terraform: la instancia solo lo puede leer.
  statement {
    sid       = "S3CodigoDesplegadoSoloLectura"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data_lake.arn}/deploy/*"]
  }

  # Contraseña del admin de Airflow (SecureString con la llave administrada aws/ssm).
  statement {
    sid       = "SsmParametrosDeAirflow"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${local.region}:${local.account_id}:parameter/${var.project_name}/${var.environment}/airflow/*"]
  }

  # Comprehend no permite restringir las operaciones síncronas por recurso.
  statement {
    sid = "ComprehendAnalisisSincrono"
    actions = [
      "comprehend:DetectDominantLanguage",
      "comprehend:DetectEntities",
      "comprehend:DetectKeyPhrases",
      "comprehend:BatchDetectDominantLanguage",
      "comprehend:BatchDetectEntities",
      "comprehend:BatchDetectKeyPhrases",
    ]
    resources = ["*"]
  }

  statement {
    sid = "GlueCatalogoDelProyecto"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:UpdateTable",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
      "glue:CreatePartition",
      "glue:BatchCreatePartition",
      "glue:UpdatePartition",
      "glue:BatchUpdatePartition",
      "glue:DeletePartition",
      "glue:BatchDeletePartition",
    ]
    resources = [local.glue_catalog_arn, local.glue_database_arn, local.glue_tables_arn]
  }

  statement {
    sid = "AthenaWorkgroupDelProyecto"
    actions = [
      "athena:GetWorkGroup",
      "athena:StartQueryExecution",
      "athena:StopQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:BatchGetQueryExecution",
      "athena:ListQueryExecutions",
    ]
    resources = [local.athena_wg_arn]
  }
}

resource "aws_iam_policy" "airflow_pipeline" {
  name        = "${local.name_prefix}-airflow-pipeline"
  description = "Permisos mínimos del pipeline: S3 del data lake, Comprehend, Glue y Athena"
  policy      = data.aws_iam_policy_document.airflow_pipeline.json
}

resource "aws_iam_role_policy_attachment" "airflow_pipeline" {
  role       = aws_iam_role.airflow_ec2.name
  policy_arn = aws_iam_policy.airflow_pipeline.arn
}

# Acceso a la instancia con Session Manager: sin abrir el puerto 22 ni gestionar llaves SSH.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.airflow_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "airflow_ec2" {
  name = "${local.name_prefix}-airflow-ec2"
  role = aws_iam_role.airflow_ec2.name
}
