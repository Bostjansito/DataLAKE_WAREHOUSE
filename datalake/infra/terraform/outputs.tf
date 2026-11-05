output "account_id" {
  description = "Cuenta de AWS donde se desplegó."
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  value = data.aws_region.current.name
}

output "data_lake_bucket" {
  description = "Nombre del bucket único del data lake."
  value       = aws_s3_bucket.data_lake.bucket
}

output "data_lake_bucket_arn" {
  value = aws_s3_bucket.data_lake.arn
}

output "data_lake_zones" {
  description = "Rutas S3 de cada zona."
  value       = { for z in var.data_lake_zones : z => "s3://${aws_s3_bucket.data_lake.bucket}/${z}/" }
}

output "airflow_ec2_role_arn" {
  value = aws_iam_role.airflow_ec2.arn
}

output "airflow_ec2_instance_profile" {
  value = aws_iam_instance_profile.airflow_ec2.name
}

output "glue_database" {
  value = aws_glue_catalog_database.data_lake.name
}

output "glue_tables" {
  value = sort(keys(aws_glue_catalog_table.tables))
}

output "athena_workgroup" {
  value = aws_athena_workgroup.data_lake.name
}

output "budget_created" {
  value = length(aws_budgets_budget.monthly) > 0
}

output "airflow_instance_id" {
  value = aws_instance.airflow.id
}

output "airflow_admin_password_parameter" {
  description = "Parámetro SecureString con la contraseña del usuario admin de Airflow"
  value       = aws_ssm_parameter.airflow_admin_password.name
}

output "airflow_tunnel_command" {
  description = "Abre la interfaz de Airflow en http://localhost:8081 a través de Session Manager"
  value       = "aws ssm start-session --target ${aws_instance.airflow.id} --document-name AWS-StartPortForwardingSession --parameters portNumber=8080,localPortNumber=8081"
}

output "datalake_code_object" {
  value = "s3://${aws_s3_bucket.data_lake.id}/${aws_s3_object.datalake_code.key}"
}
