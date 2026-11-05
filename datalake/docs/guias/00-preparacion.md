# Fase 0 – Preparación del entorno

Objetivo: dejar listas las herramientas, la cuenta de AWS y la base de Terraform antes de crear recursos.

## Requisitos locales (WSL Ubuntu 24.04)

| Herramienta | Versión usada | Verificación |
|---|---|---|
| AWS CLI v2 | – | `aws --version` |
| Terraform | 1.17.0 | `terraform version` |
| Docker | 29.9.2 | `docker --version` (solo para pruebas locales de Airflow) |
| uv / uvx | 0.13.7 | `uvx --version` (para el MCP de AWS, opcional) |

## Qué hacer en AWS

1. Tener un usuario IAM con permisos para crear los recursos del taller. En este laboratorio se usa
   `sebastian-admin` (política `AdministratorAccess`) en la cuenta `387512138242`.
2. Configurar sus claves en WSL:
   ```bash
   aws configure          # Access key, Secret key, región us-east-1, formato json
   aws sts get-caller-identity
   ```
   La salida debe mostrar la cuenta y el ARN del usuario esperado.
3. **(Recomendado)** Activar una alerta de presupuesto para no exceder el costo del laboratorio.
   Se crea con Terraform definiendo `budget_alert_email` (ver abajo). AWS Budgets incluye 2 presupuestos gratuitos.

## Qué hacer con Terraform

Estructura del código:

```text
datalake/infra/terraform/
├── versions.tf               # Proveedor AWS, región y etiquetas por defecto
├── variables.tf              # Variables del proyecto
├── budget.tf                 # Alerta de costos (opcional)
├── s3.tf                     # Bucket del data lake (Fase 1)
├── outputs.tf                # Valores de salida
└── terraform.tfvars.example  # Plantilla de variables, sin secretos
```

1. Crear el archivo de variables a partir de la plantilla:
   ```bash
   cd datalake/infra/terraform
   cp terraform.tfvars.example terraform.tfvars
   ```
2. (Opcional) Para la alerta de costos, editar `terraform.tfvars`:
   ```hcl
   budget_limit_usd   = 10
   budget_alert_email = "tu-correo@ejemplo.com"
   ```
3. Inicializar y validar:
   ```bash
   terraform init
   terraform fmt -check
   terraform validate
   ```

## Decisiones

- **Estado local** (`terraform.tfstate`): evita crear un bucket y una tabla DynamoDB solo para el backend.
  El archivo está en `.gitignore` y no se sube al repositorio.
- **Etiquetas por defecto** en todos los recursos (`Project`, `Environment`, `ManagedBy`, `Course`) para
  identificarlos en la consola y en el explorador de costos.
- **Sin secretos en el repositorio:** `terraform.tfvars`, `.env` y `*.pem` están en `.gitignore`.

## Evidencias

Ver [EVIDENCIAS.md – sección 0](../../evidencias/docEVIDENCIA/EVIDENCIAS.md#0-acceso-a-aws).
