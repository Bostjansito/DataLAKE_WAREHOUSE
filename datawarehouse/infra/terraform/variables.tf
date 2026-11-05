variable "aws_region" {
  type = string
  default = "us-east-1"
}
variable "enable_compute" {
  type = bool
  default = false
}
variable "enable_sources" {
  type = bool
  default = false
  validation {
    condition = !var.enable_sources || var.enable_compute
    error_message = "enable_sources requires enable_compute for the database security group."
  }
}
variable "enable_warehouse" {
  type = bool
  default = false
  validation {
    condition = !var.enable_warehouse || var.enable_compute
    error_message = "enable_warehouse requires enable_compute for the warehouse security group."
  }
}

variable "sources_deletion_protection" {
  type = bool
  default = true
}
variable "mysql_final_snapshot_identifier" {
  type = string
  default = "dw-mysql-final"
}
variable "docdb_final_snapshot_identifier" {
  type = string
  default = "dw-docdb-final"
}
