locals {
  name_prefix = "${var.project_name}-${var.environment}"
  account_id  = data.aws_caller_identity.current.account_id
  region      = var.aws_region

  # Nombres compartidos entre fases (IAM los usa antes de que existan los recursos).
  glue_database_name    = replace("${var.project_name}_${var.environment}", "-", "_")
  athena_workgroup_name = "${local.name_prefix}-wg"

  glue_catalog_arn  = "arn:aws:glue:${local.region}:${local.account_id}:catalog"
  glue_database_arn = "arn:aws:glue:${local.region}:${local.account_id}:database/${local.glue_database_name}"
  glue_tables_arn   = "arn:aws:glue:${local.region}:${local.account_id}:table/${local.glue_database_name}/*"
  athena_wg_arn     = "arn:aws:athena:${local.region}:${local.account_id}:workgroup/${local.athena_workgroup_name}"
}
