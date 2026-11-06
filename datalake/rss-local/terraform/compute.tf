data "aws_ssm_parameter" "al2023" {
  count = var.enable_ec2 ? 1 : 0
  name  = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_vpc" "lake" {
  count                = var.enable_ec2 ? 1 : 0
  cidr_block           = "10.72.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${var.project_name}-vpc" }
}

resource "aws_subnet" "lake" {
  count                   = var.enable_ec2 ? 1 : 0
  vpc_id                  = aws_vpc.lake[0].id
  cidr_block              = "10.72.1.0/24"
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.project_name}-public-egress" }
}

resource "aws_internet_gateway" "lake" {
  count  = var.enable_ec2 ? 1 : 0
  vpc_id = aws_vpc.lake[0].id
}

resource "aws_route_table" "lake" {
  count  = var.enable_ec2 ? 1 : 0
  vpc_id = aws_vpc.lake[0].id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.lake[0].id
  }
}

resource "aws_route_table_association" "lake" {
  count          = var.enable_ec2 ? 1 : 0
  subnet_id      = aws_subnet.lake[0].id
  route_table_id = aws_route_table.lake[0].id
}

resource "aws_security_group" "lake" {
  count       = var.enable_ec2 ? 1 : 0
  name_prefix = "${var.project_name}-"
  description = "Sin entrada; administrar exclusivamente con Session Manager."
  vpc_id      = aws_vpc.lake[0].id
  # HTTPS para RSS, AWS APIs, paquetes y contenedores. No SSH ni puerto 8080.
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "airflow" {
  count                       = var.enable_ec2 ? 1 : 0
  ami                         = data.aws_ssm_parameter.al2023[0].value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.lake[0].id
  vpc_security_group_ids      = [aws_security_group.lake[0].id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.lake[0].name
  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/bootstrap.sh.tftpl", {
    bucket          = aws_s3_bucket.lake.bucket
    artifact_key    = var.deployment_artifact_key
    artifact_sha256 = var.deployment_artifact_sha256
    region          = var.aws_region
    database        = aws_glue_catalog_database.lake.name
    workgroup       = aws_athena_workgroup.lake.name
    compose_version = var.compose_version
  })
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "disabled"
  }
  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gib
    encrypted             = true
    delete_on_termination = true
  }
  credit_specification {
    cpu_credits = "standard"
  }
  tags = { Name = "${var.project_name}-airflow" }
  depends_on = [
    aws_route_table_association.lake,
    aws_iam_role_policy_attachment.pipeline,
    aws_iam_role_policy_attachment.ssm
  ]
  lifecycle {
    precondition {
      condition     = can(regex("^[a-fA-F0-9]{64}$", var.deployment_artifact_sha256))
      error_message = "Suba artifacts/lake.tar.gz y proporcione su SHA-256 antes de habilitar EC2."
    }
  }
}
