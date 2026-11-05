variable "vpc_id" {
  type = string
}
variable "public_subnets" {
  type = list(string)
}
variable "aws_region" {
  type = string
}
variable "raw_bucket" {
  type = string
}
variable "raw_bucket_arn" {
  type = string
}
