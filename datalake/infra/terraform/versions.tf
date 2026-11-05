terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Estado local para el laboratorio: evita crear un bucket y una tabla DynamoDB
  # adicionales solo para el backend remoto. No subir terraform.tfstate al repositorio.
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Course      = "arquitecturas-de-datos"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
