output "bucket_name" {
  value = aws_s3_bucket.lake.bucket
}

output "glue_database_name" {
  value = aws_glue_catalog_database.lake.name
}

output "athena_workgroup" {
  value = aws_athena_workgroup.lake.name
}

output "athena_results_location" {
  value = "s3://${aws_s3_bucket.lake.bucket}/athena-results/"
}

output "pipeline_policy_arn" {
  description = "Política para un rol existente de ejecución local (no concede confianza por sí sola)."
  value       = aws_iam_policy.pipeline.arn
}

output "deployment_artifact_uri" {
  value = "s3://${aws_s3_bucket.lake.bucket}/${var.deployment_artifact_key}"
}

output "ec2_instance_id" {
  value = try(aws_instance.airflow[0].id, null)
}

output "ssm_port_forward_command" {
  description = "Requiere Session Manager Plugin local y autorización del operador para StartSession."
  value       = var.enable_ec2 ? "aws ssm start-session --region ${var.aws_region} --target ${aws_instance.airflow[0].id} --document-name AWS-StartPortForwardingSession --parameters '{\"portNumber\":[\"8080\"],\"localPortNumber\":[\"8080\"]}'" : null
}
