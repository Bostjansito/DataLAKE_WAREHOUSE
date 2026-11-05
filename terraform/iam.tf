locals {
  arn_prefix = "arn:${data.aws_partition.current.partition}"
  glue_arns = concat([
    "${local.arn_prefix}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
    aws_glue_catalog_database.lake.arn
  ], [for table in aws_glue_catalog_table.lake : table.arn])
}

resource "aws_iam_policy" "pipeline" {
  name        = "${var.project_name}-pipeline"
  description = "Acceso del pipeline únicamente a este lago, catálogo y workgroup."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "BucketMetadata"
        Effect   = "Allow"
        Action   = ["s3:GetBucketLocation"]
        Resource = aws_s3_bucket.lake.arn
      },
      {
        Sid       = "ListLakePrefixes"
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = aws_s3_bucket.lake.arn
        Condition = { StringLike = { "s3:prefix" = ["bronze/*", "silver/*", "gold/*", "quarantine/*", "_control/*", "athena-results/*", "artifacts/*"] } }
      },
      {
        Sid      = "ReadWritePipelineData"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = [for prefix in ["bronze", "silver", "gold", "quarantine", "_control", "athena-results"] : "${aws_s3_bucket.lake.arn}/${prefix}/*"]
      },
      {
        Sid      = "ReadDeploymentArtifact"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.lake.arn}/${var.deployment_artifact_key}"
      },
      {
        Sid      = "PublishCatalogSnapshots"
        Effect   = "Allow"
        Action   = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:UpdateTable", "glue:GetPartition", "glue:GetPartitions", "glue:BatchGetPartition", "glue:CreatePartition", "glue:BatchCreatePartition", "glue:UpdatePartition", "glue:BatchUpdatePartition", "glue:DeletePartition", "glue:BatchDeletePartition"]
        Resource = local.glue_arns
      },
      {
        Sid      = "AthenaLimitedWorkgroup"
        Effect   = "Allow"
        Action   = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults", "athena:StopQueryExecution", "athena:GetWorkGroup"]
        Resource = aws_athena_workgroup.lake.arn
      },
      {
        Sid    = "SynchronousTextEnrichment"
        Effect = "Allow"
        # Estas API no admiten permisos por recurso; limitar región.
        Action    = ["comprehend:DetectEntities", "comprehend:DetectKeyPhrases"]
        Resource  = "*"
        Condition = { StringEquals = { "aws:RequestedRegion" = var.aws_region } }
      }
    ]
  })
}

resource "aws_iam_role" "ec2" {
  count = var.enable_ec2 ? 1 : 0
  name  = "${var.project_name}-ec2"
  # EC2 no aporta SourceArn/SourceAccount al asumir un instance profile.
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "pipeline" {
  count      = var.enable_ec2 ? 1 : 0
  role       = aws_iam_role.ec2[0].name
  policy_arn = aws_iam_policy.pipeline.arn
}

resource "aws_iam_role_policy_attachment" "ssm" {
  count      = var.enable_ec2 ? 1 : 0
  role       = aws_iam_role.ec2[0].name
  policy_arn = "${local.arn_prefix}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "lake" {
  count = var.enable_ec2 ? 1 : 0
  name  = "${var.project_name}-ec2"
  role  = aws_iam_role.ec2[0].name
}
