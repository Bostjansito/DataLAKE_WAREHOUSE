variable "aws_region" {
  description = "Región única para el lago y Comprehend."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "rss-lake"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,29}$", var.project_name))
    error_message = "Use entre 3 y 30 caracteres: minúsculas, números y guiones."
  }
}

variable "bucket_name" {
  description = "Nombre globalmente único; no se crean buckets adicionales."
  type        = string
}

variable "glue_database_name" {
  type    = string
  default = "rss_lake"
  validation {
    condition     = can(regex("^[a-zA-Z_][a-zA-Z0-9_]*$", var.glue_database_name))
    error_message = "Use un identificador de base válido: letra o guion bajo inicial, seguido de letras, números o guiones bajos."
  }
}

variable "athena_scan_limit_bytes" {
  description = "Límite por consulta; no es un presupuesto mensual ni garantiza coste cero."
  type        = number
  default     = 10485760
  validation {
    condition     = var.athena_scan_limit_bytes >= 10485760 && floor(var.athena_scan_limit_bytes) == var.athena_scan_limit_bytes
    error_message = "Athena requiere un límite entero de al menos 10 MiB."
  }
}

variable "enable_ec2" {
  description = "Activar solamente después de subir y verificar el artefacto de despliegue."
  type        = bool
  default     = false
}

variable "instance_type" {
  description = "Instancia x86_64 burstable para Airflow; verificar disponibilidad y precio regional."
  type        = string
  default     = "t3.medium"
  validation {
    condition     = can(regex("^t3(a)?\\.", var.instance_type))
    error_message = "El bootstrap usa x86_64 y créditos standard: seleccione t3 o t3a."
  }
}

variable "root_volume_gib" {
  type    = number
  default = 30
}

variable "deployment_artifact_key" {
  type    = string
  default = "artifacts/lake.tar.gz"
  validation {
    condition     = startswith(var.deployment_artifact_key, "artifacts/") && !strcontains(var.deployment_artifact_key, "'") && !strcontains(var.deployment_artifact_key, "\n")
    error_message = "El artefacto debe estar bajo artifacts/ y no contener comillas simples ni saltos de línea."
  }
}

variable "deployment_artifact_sha256" {
  description = "SHA-256 del tar.gz; obligatorio al habilitar EC2. No es un secreto."
  type        = string
  default     = ""
}

variable "compose_version" {
  description = "Versión fija del plugin Docker Compose descargado del repositorio oficial."
  type        = string
  default     = "v2.32.4"
  validation {
    condition     = can(regex("^v[0-9]+\\.[0-9]+\\.[0-9]+$", var.compose_version))
    error_message = "Use una versión exacta como v2.32.4."
  }
}
