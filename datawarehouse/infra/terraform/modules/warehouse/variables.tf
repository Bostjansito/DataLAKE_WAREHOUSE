variable "vpc_id" {
  type = string
}

variable "private_subnets" {
  type = list(string)
}

variable "raw_bucket_arn" {
  type = string
}

variable "compute_sg_id" {
  type = string
}