terraform {
  required_version = ">= 1.9.0, < 2.0.0"
  required_providers {
    aws = {
      source = "hashicorp/aws"
      version = "~> 5.100"
    }
    random = {
      source = "hashicorp/random"
      version = "~> 3.7"
    }
  }
}
provider "aws" {
  region = var.aws_region
  default_tags {
    tags = { Project = "ecommerce-dw" }
  }
}
locals {
  enable_network = var.enable_compute || var.enable_sources || var.enable_warehouse
}
module "storage" {
  source = "./modules/storage"
}
module "vpc" {
  source = "./modules/vpc"
  count = local.enable_network ? 1 : 0
  aws_region = var.aws_region
}
module "compute" {
  source = "./modules/compute"
  count = var.enable_compute ? 1 : 0
  vpc_id = module.vpc[0].vpc_id
  public_subnets = module.vpc[0].public_subnets
  raw_bucket = module.storage.raw_bucket
  raw_bucket_arn = module.storage.raw_bucket_arn
  aws_region = var.aws_region
}
module "database" {
  source = "./modules/database"
  count = var.enable_sources ? 1 : 0
  vpc_id = module.vpc[0].vpc_id
  private_subnets = module.vpc[0].private_subnets
  compute_sg_id = try(module.compute[0].compute_sg_id, null)
  deletion_protection = var.sources_deletion_protection
  mysql_final_snapshot_identifier = var.mysql_final_snapshot_identifier
  docdb_final_snapshot_identifier = var.docdb_final_snapshot_identifier
}
module "warehouse" {
  source = "./modules/warehouse"
  count = var.enable_warehouse ? 1 : 0
  vpc_id = module.vpc[0].vpc_id
  private_subnets = module.vpc[0].private_subnets
  raw_bucket_arn = module.storage.raw_bucket_arn
  compute_sg_id = try(module.compute[0].compute_sg_id, null)
}
# Separate policy prevents a compute -> database -> compute dependency cycle.
resource "aws_iam_role_policy" "runtime_secrets" {
  count = var.enable_compute && (var.enable_sources || var.enable_warehouse) ? 1 : 0
  name = "runtime-secrets"
  role = module.compute[0].role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = concat(
        var.enable_sources ? [module.database[0].mysql_secret_arn, module.database[0].docdb_secret_arn] : [],
        var.enable_warehouse ? [module.warehouse[0].redshift_secret_arn] : []
      )
    }]
  })
}
