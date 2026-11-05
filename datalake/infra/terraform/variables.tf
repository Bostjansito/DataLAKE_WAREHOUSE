variable "aws_region" {
  description = "Región de AWS donde se despliega el data lake."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefijo usado para nombrar los recursos."
  type        = string
  default     = "datalake-noticias"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,30}$", var.project_name))
    error_message = "Solo minúsculas, números y guiones (3 a 30 caracteres)."
  }
}

variable "environment" {
  description = "Nombre del entorno."
  type        = string
  default     = "lab"
}

variable "data_lake_zones" {
  description = "Prefijos (zonas) del data lake dentro del único bucket."
  type        = list(string)
  default     = ["bronze", "silver", "gold", "quarantine", "control", "athena-results", "tmp"]
}

variable "athena_results_retention_days" {
  description = "Días que se conservan los resultados de consultas de Athena."
  type        = number
  default     = 7
}

variable "tmp_retention_days" {
  description = "Días que se conservan los archivos temporales de escritura (staging)."
  type        = number
  default     = 1
}

variable "force_destroy_bucket" {
  description = "Permite que terraform destroy elimine el bucket aunque tenga objetos. Útil en el laboratorio."
  type        = bool
  default     = true
}

variable "athena_bytes_scanned_cutoff" {
  description = "Máximo de bytes que puede escanear una consulta de Athena (mínimo 10 MB). 100 MB por defecto."
  type        = number
  default     = 104857600
}

variable "budget_limit_usd" {
  description = "Límite mensual en USD para la alerta de presupuesto."
  type        = number
  default     = 10
}

variable "budget_alert_email" {
  description = "Correo que recibe las alertas de presupuesto. Vacío = no se crea el presupuesto."
  type        = string
  default     = ""
}

variable "airflow_instance_type" {
  description = "Tipo de instancia de Airflow. t3.medium (2 vCPU, 4 GB) ~USD 0,0416/h en us-east-1."
  type        = string
  default     = "t3.medium"
}

variable "airflow_volume_gb" {
  description = "Tamaño del disco gp3 de la instancia de Airflow."
  type        = number
  default     = 20
}

variable "airflow_availability_zone" {
  description = "Zona de disponibilidad de la subred por defecto donde se crea la instancia."
  type        = string
  default     = "us-east-1a"
}

variable "airflow_version" {
  description = "Versión de Apache Airflow instalada con pip y su archivo de constraints oficial."
  type        = string
  default     = "2.10.5"
}
