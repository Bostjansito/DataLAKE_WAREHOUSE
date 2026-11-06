# Fase 5: instancia EC2 con Apache Airflow.
# - Sin puertos de entrada: la administración y la interfaz web se usan por AWS Systems Manager
#   (Session Manager y reenvío de puertos), autenticado con IAM. Sin llaves SSH.
# - El código del pipeline (src/, dags/, config/) se empaqueta con Terraform y se publica en
#   s3://<bucket>/deploy/; la instancia lo descarga al arrancar y con /opt/datalake/deploy.sh.
# - La contraseña del usuario admin de Airflow se genera aleatoriamente y se guarda cifrada en SSM
#   Parameter Store (nunca en el repositorio ni en user_data).

locals {
  datalake_dir  = abspath("${path.module}/../..")
  deploy_key    = "deploy/datalake.zip"
  airflow_param = "/${var.project_name}/${var.environment}/airflow/admin-password"
  pycache_files = setunion(
    fileset(local.datalake_dir, "src/**/__pycache__/**"),
    fileset(local.datalake_dir, "dags/**/__pycache__/**"),
  )
}

data "archive_file" "datalake_code" {
  type        = "zip"
  source_dir  = local.datalake_dir
  output_path = "${path.module}/.build/datalake.zip"
  excludes = concat(
    [".venv", "infra", "tests", ".env", ".pytest_cache", "scripts", "sql", "docs", "evidencias", "README.md", "rss-local"],
    tolist(local.pycache_files),
  )
}

resource "aws_s3_object" "datalake_code" {
  bucket = aws_s3_bucket.data_lake.id
  key    = local.deploy_key
  source = data.archive_file.datalake_code.output_path
  etag   = data.archive_file.datalake_code.output_md5
}

resource "random_password" "airflow_admin" {
  length  = 24
  special = false
}

resource "aws_ssm_parameter" "airflow_admin_password" {
  name        = local.airflow_param
  description = "Contraseña del usuario admin de Airflow (laboratorio data lake)"
  type        = "SecureString"
  value       = random_password.airflow_admin.result
}

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
  filter {
    name   = "availability-zone"
    values = [var.airflow_availability_zone]
  }
}

resource "aws_security_group" "airflow" {
  name        = "${local.name_prefix}-airflow"
  description = "Airflow: sin entrada; salida a Internet para RSS y APIs de AWS"
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "HTTPS hacia RSS y APIs de AWS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    description = "HTTP para repositorios de paquetes del sistema"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "airflow" {
  ami                         = data.aws_ssm_parameter.al2023_ami.value
  instance_type               = var.airflow_instance_type
  subnet_id                   = data.aws_subnets.default.ids[0]
  vpc_security_group_ids      = [aws_security_group.airflow.id]
  iam_instance_profile        = aws_iam_instance_profile.airflow_ec2.name
  associate_public_ip_address = true # salida a Internet sin NAT Gateway (USD 0,045/h ahorrados)

  metadata_options {
    http_tokens   = "required" # IMDSv2
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.airflow_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  user_data = templatefile("${path.module}/templates/airflow_user_data.sh.tftpl", {
    bucket          = aws_s3_bucket.data_lake.id
    region          = var.aws_region
    deploy_key      = local.deploy_key
    airflow_param   = local.airflow_param
    airflow_version = var.airflow_version
    glue_database   = local.glue_database_name
    athena_wg       = local.athena_workgroup_name
  })
  user_data_replace_on_change = true

  tags = {
    Name = "${local.name_prefix}-airflow"
  }

  depends_on = [aws_s3_object.datalake_code, aws_ssm_parameter.airflow_admin_password]

  lifecycle {
    ignore_changes = [ami] # no reemplazar la instancia cuando AWS publique una AMI nueva
  }
}
