resource "aws_security_group" "ec2" {
  name_prefix = "dw-ec2-"
  description = "Airflow/dbt: no inbound ports; outbound packages and SSM"
  vpc_id = var.vpc_id
  egress {
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_iam_role" "ec2" {
  name_prefix = "dw-ec2-"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" } }]
  })
}
resource "aws_iam_role_policy_attachment" "ssm" {
  role = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "s3" {
  role = aws_iam_role.ec2.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:ListBucket", "s3:GetBucketLocation"], Resource = var.raw_bucket_arn },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${var.raw_bucket_arn}/*" }
    ]
  })
}
resource "aws_iam_instance_profile" "ec2" {
  name_prefix = "dw-ec2-"
  role = aws_iam_role.ec2.name
}
data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners = ["amazon"]
  filter {
    name = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
  filter {
    name = "virtualization-type"
    values = ["hvm"]
  }
}
resource "aws_instance" "airflow" {
  ami = data.aws_ami.amazon_linux_2023.id
  instance_type = "t3.medium"
  subnet_id = var.public_subnets[0]
  associate_public_ip_address = true
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile = aws_iam_instance_profile.ec2.name
  user_data = templatefile("${path.module}/user_data.sh.tftpl", { region = var.aws_region })
  user_data_replace_on_change = true
  metadata_options {
    http_endpoint = "enabled"
    http_tokens = "required"
    http_put_response_hop_limit = 1
  }
  root_block_device {
    encrypted = true
    volume_type = "gp3"
    volume_size = 30
    delete_on_termination = true
  }
  credit_specification {
    cpu_credits = "standard"
  }
  tags = { Name = "dw-airflow-dbt" }
}
output "ec2_public_ip" {
  value = aws_instance.airflow.public_ip
}
output "ec2_instance_id" {
  value = aws_instance.airflow.id
}
output "compute_sg_id" {
  value = aws_security_group.ec2.id
}
output "role_name" {
  value = aws_iam_role.ec2.name
}
