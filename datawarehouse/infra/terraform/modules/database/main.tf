resource "aws_db_subnet_group" "main" {
  name       = "dw-db-subnet-group"
  subnet_ids = var.private_subnets
  tags = {
    Name = "dw-db-subnet-group"
  }
}

resource "aws_docdb_subnet_group" "main" {
  count      = var.enable_docdb ? 1 : 0
  name       = "dw-docdb-subnet-group"
  subnet_ids = var.private_subnets
}

resource "aws_db_parameter_group" "mysql" {
  name   = "dw-mysql-params"
  family = "mysql8.4"
  parameter {
    name  = "require_secure_transport"
    value = "1"
  }
}

# Security group for RDS MySQL
resource "aws_security_group" "rds" {
  name        = "dw-rds-sg"
  description = "Security group for RDS MySQL"
  vpc_id      = var.vpc_id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "dw-rds-sg"
  }
}

# Security group for DocumentDB
resource "aws_security_group" "docdb" {
  count       = var.enable_docdb ? 1 : 0
  name        = "dw-docdb-sg"
  description = "Security group for DocumentDB"
  vpc_id      = var.vpc_id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "dw-docdb-sg"
  }
}


# Allow compute SG to access RDS and DocumentDB
resource "aws_security_group_rule" "rds_ingress_from_compute" {
  type                     = "ingress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  source_security_group_id = var.compute_sg_id
  security_group_id        = aws_security_group.rds.id
}

resource "aws_security_group_rule" "docdb_ingress_from_compute" {
  type                     = "ingress"
  count                    = var.enable_docdb ? 1 : 0
  from_port                = 27017
  to_port                  = 27017
  protocol                 = "tcp"
  source_security_group_id = var.compute_sg_id
  security_group_id        = aws_security_group.docdb[0].id
}

resource "aws_db_instance" "mysql" {
  identifier                  = "dw-mysql"
  engine                      = "mysql"
  engine_version              = "8.4"
  engine_lifecycle_support    = "open-source-rds-extended-support-disabled"
  instance_class              = "db.t3.micro"
  allocated_storage           = 20
  storage_type                = "gp3"
  backup_retention_period     = 1
  multi_az                    = false
  auto_minor_version_upgrade  = true
  storage_encrypted           = true
  db_name                     = "ecommerce"
  username                    = "admin"
  manage_master_user_password = true
  parameter_group_name        = aws_db_parameter_group.mysql.name
  db_subnet_group_name        = aws_db_subnet_group.main.name
  vpc_security_group_ids      = [aws_security_group.rds.id]
  skip_final_snapshot         = false
  final_snapshot_identifier   = var.mysql_final_snapshot_identifier
  deletion_protection         = var.deletion_protection
  publicly_accessible         = false
  tags = {
    Name = "dw-mysql"
  }
}

resource "aws_docdb_cluster_parameter_group" "docdb" {
  family = "docdb5.0"
  count  = var.enable_docdb ? 1 : 0
  name   = "dw-docdb-params"
  parameter {
    name  = "tls"
    value = "enabled"
  }
}

resource "aws_docdb_cluster" "main" {
  count                           = var.enable_docdb ? 1 : 0
  cluster_identifier              = "dw-docdb"
  engine                          = "docdb"
  engine_version                  = "5.0.0"
  master_username                 = "dwadmin"
  manage_master_user_password     = true
  db_subnet_group_name            = aws_docdb_subnet_group.main[0].name
  db_cluster_parameter_group_name = aws_docdb_cluster_parameter_group.docdb[0].name
  vpc_security_group_ids          = [aws_security_group.docdb[0].id]
  port                            = 27017
  storage_encrypted               = true
  backup_retention_period         = 1
  skip_final_snapshot             = false
  final_snapshot_identifier       = var.docdb_final_snapshot_identifier
  deletion_protection             = var.deletion_protection
  apply_immediately               = true
  tags = {
    Name = "dw-docdb"
  }
}

resource "aws_docdb_cluster_instance" "main" {
  count              = var.enable_docdb ? 1 : 0
  identifier         = "dw-docdb-instance"
  cluster_identifier = aws_docdb_cluster.main[0].id
  instance_class     = "db.t3.medium"
  apply_immediately  = true
}



output "mysql_endpoint" {
  value = aws_db_instance.mysql.address
}

output "docdb_endpoint" {
  value = try(aws_docdb_cluster.main[0].endpoint, null)
}

output "mysql_secret_arn" {
  value = aws_db_instance.mysql.master_user_secret[0].secret_arn
}

output "docdb_secret_arn" {
  value = try(aws_docdb_cluster.main[0].master_user_secret[0].secret_arn, null)
}