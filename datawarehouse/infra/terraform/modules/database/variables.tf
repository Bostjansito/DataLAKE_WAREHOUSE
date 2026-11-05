variable "vpc_id" {
  type = string
}
variable "private_subnets" {
  type = list(string)
}
variable "compute_sg_id" {
  type = string
}
variable "deletion_protection" {
  type = bool
}
variable "mysql_final_snapshot_identifier" {
  type = string
}
variable "docdb_final_snapshot_identifier" {
  type = string
}
