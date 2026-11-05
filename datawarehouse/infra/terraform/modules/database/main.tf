resource "aws_db_subnet_group" "main" {
  name       = "dw-db-subnet-group"
  subnet_ids = var.private_subnets
  tags = {
    Name = "dw-db-subnet-group"
  }
}

resource "aws_docdb_subnet_group" "main" {
  name = "dw-docdb-subnet-group"
  subnet_ids = var.private_subnets
}

resource "aws_db_parameter_group" "mysql" {
  name = "dw-mysql-params"
  family = "mysql8.0"
  parameter {
    name = "require_secure_transport"
    value = "ON"
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
  type              = "ingress"
  from_port         = 3306
  to_port           = 3306
  protocol          = "tcp"
  source_security_group_id = var.compute_sg_id
  security_group_id = aws_security_group.rds.id
}

resource "aws_security_group_rule" "docdb_ingress_from_compute" {
  type              = "ingress"
  from_port         = 27017
  to_port           = 27017
  protocol          = "tcp"
  source_security_group_id = var.compute_sg_id
  security_group_id = aws_security_group.docdb.id
}

resource "aws_db_instance" "mysql" {
  identifier             = "dw-mysql"
  engine                 = "mysql"
  engine_version         = "8.0"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  storage_encrypted      = true
  db_name                = "ecommerce"
  username               = "admin"
  password               = random_password.mysql.result
  parameter_group_name   = aws_db_parameter_group.mysql.name
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = false
  final_snapshot_identifier = var.mysql_final_snapshot_identifier
  deletion_protection    = var.deletion_protection
  publicly_accessible    = false
  tags = {
    Name = "dw-mysql"
  }
}

resource "aws_docdb_cluster_parameter_group" "docdb" {
  family = "docdb5.0"
  name   = "dw-docdb-params"
  parameter {
    name  = "tls"
    value = "enabled"
  }
}

resource "aws_docdb_cluster" "main" {
  cluster_identifier      = "dw-docdb"
  engine                  = "docdb"
  engine_version          = "5.0.0"
  master_username         = "admin"
  master_password         = random_password.docdb.result
  db_subnet_group_name    = aws_docdb_subnet_group.main.name
  db_cluster_parameter_group_name = aws_docdb_cluster_parameter_group.docdb.name
  vpc_security_group_ids  = [aws_security_group.docdb.id]
  port                    = 27017
  storage_encrypted       = true
  skip_final_snapshot     = false
  final_snapshot_identifier = var.docdb_final_snapshot_identifier
  deletion_protection     = var.deletion_protection
  apply_immediately       = true
  tags = {
    Name = "dw-docdb"
  }
}

resource "aws_docdb_cluster_instance" "main" {
  identifier         = "dw-docdb-instance"
  cluster_identifier = aws_docdb_cluster.main.id
  instance_class     = "db.t3.medium"
  apply_immediately  = true
}

resource "aws_secretsmanager_secret" "mysql" {
  name = "dw/mysql/credentials"
}

resource "aws_secretsmanager_secret_version" "mysql" {
  secret_id = aws_secretsmanager_secret.mysql.id
  secret_string = jsonencode({
    host     = aws_db_instance.mysql.address
    port     = 3306
    username = "admin"
    password = random_password.mysql.result
    database = "ecommerce"
  })
}

resource "aws_secretsmanager_secret" "docdb" {
  name = "dw/docdb/credentials"
}

resource "aws_secretsmanager_secret_version" "docdb" {
  secret_id = aws_secretsmanager_secret.docdb.id
  secret_string = jsonencode({
    uri      = "mongodb://admin:${random_password.docdb.result}@${aws_docdb_cluster.main.endpoint}:27017/?tls=true&replicaSet=rs0&readPreference=secondaryPreferred&retryWrites=false"
    database = "ecommerce"
  })
}

resource "random_password" "mysql" {
  length  = 32
  special = false
}

resource "random_password" "docdb" {
  length  = 32
  special = false
}


output "mysql_endpoint" {
  value     = aws_db_instance.mysql.address
  sensitive = true
}

output "docdb_endpoint" {
  value     = aws_docdb_cluster.main.endpoint
  sensitive = true
}

output "mysql_secret_arn" {
  value = aws_secretsmanager_secret.mysql.arn
}

output "docdb_secret_arn" {
  value = aws_secretsmanager_secret.docdb.arn
}