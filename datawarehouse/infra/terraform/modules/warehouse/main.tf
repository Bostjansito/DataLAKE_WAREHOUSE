resource "aws_redshiftserverless_workgroup" "main" {
  workgroup_name       = "dw-workgroup"
  namespace_name       = aws_redshiftserverless_namespace.main.namespace_name
  base_capacity        = 8
  enhanced_vpc_routing = true
  subnet_ids           = var.private_subnets
  security_group_ids   = [aws_security_group.redshift.id]
  publicly_accessible  = false
  tags = {
    Name = "dw-redshift-workgroup"
  }
}

resource "aws_redshiftserverless_namespace" "main" {
  namespace_name        = "dw-namespace"
  admin_username        = "admin"
  manage_admin_password = true
  db_name               = "ecommerce_dw"
  iam_roles             = [aws_iam_role.redshift_copy.arn]
  default_iam_role_arn  = aws_iam_role.redshift_copy.arn
  tags = {
    Name = "dw-redshift-namespace"
  }
}


resource "aws_security_group" "redshift" {
  name        = "dw-redshift-sg"
  description = "Security group for Redshift Serverless"
  vpc_id      = var.vpc_id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "dw-redshift-sg"
  }
}

# Allow compute instance to connect to Redshift
resource "aws_security_group_rule" "redshift_ingress_from_compute" {
  type                     = "ingress"
  from_port                = 5439
  to_port                  = 5439
  protocol                 = "tcp"
  source_security_group_id = var.compute_sg_id
  security_group_id        = aws_security_group.redshift.id
}

resource "aws_iam_role" "redshift_copy" {
  name = "dw-redshift-copy-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = ["redshift.amazonaws.com", "redshift-serverless.amazonaws.com"]
      }
    }]
  })
}

resource "aws_iam_policy" "redshift_s3_read" {
  name = "dw-redshift-s3-read"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = [
        "s3:GetObject",
        "s3:ListBucket"
      ]
      Effect = "Allow"
      Resource = [
        var.raw_bucket_arn,
        "${var.raw_bucket_arn}/*"
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "redshift_s3_read" {
  role       = aws_iam_role.redshift_copy.name
  policy_arn = aws_iam_policy.redshift_s3_read.arn
}




output "redshift_endpoint" {
  value = aws_redshiftserverless_workgroup.main.endpoint[0].address
}

output "redshift_database" {
  value = aws_redshiftserverless_namespace.main.db_name
}

output "redshift_username" {
  value = aws_redshiftserverless_namespace.main.admin_username
}

output "redshift_copy_role_arn" {
  value = aws_iam_role.redshift_copy.arn
}

output "redshift_secret_arn" {
  value = aws_redshiftserverless_namespace.main.admin_password_secret_arn
}