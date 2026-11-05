output "vpc_id" {
  value = try(module.vpc[0].vpc_id, null)
}

output "public_subnets" {
  value = try(module.vpc[0].public_subnets, null)
}

output "private_subnets" {
  value = try(module.vpc[0].private_subnets, null)
}

output "raw_bucket" {
  value = module.storage.raw_bucket
}

output "raw_bucket_arn" {
  value = module.storage.raw_bucket_arn
}

output "mysql_endpoint" {
  sensitive = true
  value = try(module.database[0].mysql_endpoint, null)
}

output "docdb_endpoint" {
  sensitive = true
  value = try(module.database[0].docdb_endpoint, null)
}

output "mysql_secret_arn" {
  value = try(module.database[0].mysql_secret_arn, null)
}

output "docdb_secret_arn" {
  value = try(module.database[0].docdb_secret_arn, null)
}

output "redshift_endpoint" {
  sensitive = true
  value = try(module.warehouse[0].redshift_endpoint, null)
}

output "redshift_database" {
  value = try(module.warehouse[0].redshift_database, null)
}

output "redshift_username" {
  sensitive = true
  value = try(module.warehouse[0].redshift_username, null)
}

output "redshift_copy_role_arn" {
  value = try(module.warehouse[0].redshift_copy_role_arn, null)
}

output "redshift_secret_arn" {
  value = try(module.warehouse[0].redshift_secret_arn, null)
}

output "ec2_public_ip" {
  value = try(module.compute[0].ec2_public_ip, null)
}

output "ec2_instance_id" {
  value = try(module.compute[0].ec2_instance_id, null)
}

output "runtime_config" {
  value = {
    AWS_REGION = var.aws_region
    S3_BUCKET = module.storage.raw_bucket
    MYSQL_SECRET_ARN = try(module.database[0].mysql_secret_arn, null)
    MONGO_SECRET_ARN = try(module.database[0].docdb_secret_arn, null)
    REDSHIFT_SECRET_ARN = try(module.warehouse[0].redshift_secret_arn, null)
    REDSHIFT_COPY_ROLE_ARN = try(module.warehouse[0].redshift_copy_role_arn, null)
  }
}
