# Fase 1 – Bucket S3 del data lake

Objetivo: crear con Terraform **un solo bucket** que contenga todas las zonas del data lake
(arquitectura medallón), privado, cifrado y con reglas para minimizar costos.

## Qué se crea

Archivo: [`datalake/infra/terraform/s3.tf`](../../infra/terraform/s3.tf)

| Recurso Terraform | Propósito |
|---|---|
| `aws_s3_bucket.data_lake` | Bucket `datalake-noticias-<cuenta>-<región>` |
| `aws_s3_bucket_ownership_controls` | Desactiva ACL; el dueño del bucket es dueño de todos los objetos |
| `aws_s3_bucket_public_access_block` | Bloquea todo acceso público |
| `aws_s3_bucket_server_side_encryption_configuration` | Cifrado SSE-S3 (AES256) sin costo adicional |
| `aws_s3_bucket_versioning` | Versionado deshabilitado (ver decisiones) |
| `aws_s3_bucket_lifecycle_configuration` | Limpieza automática de temporales y resultados de Athena |
| `aws_s3_bucket_policy` | Rechaza conexiones sin HTTPS |
| `aws_s3_object.zone_markers` | Una carpeta vacía por zona, visible en la consola |

### Zonas

```text
s3://datalake-noticias-387512138242-us-east-1/
├── bronze/          # RSS originales: source=<fuente>/ingestion_date=AAAA-MM-DD/run_id=<id>/
├── silver/          # news, news_entities, news_key_phrases (Parquet)
├── gold/            # Agregados (Parquet)
├── quarantine/      # Registros inválidos con motivo
├── control/         # Manifiestos y estado de lotes
├── athena-results/  # Resultados de Athena (expiran a los 7 días)
└── tmp/             # Staging de escrituras (expira a 1 día)
```

## Qué hacer con Terraform

```bash
cd datalake/infra/terraform
terraform plan -out=fase1.tfplan     # Debe indicar: Plan: 14 to add, 0 to change, 0 to destroy.
terraform apply fase1.tfplan
terraform output data_lake_bucket
```

Verificación por CLI:

```bash
B=$(terraform output -raw data_lake_bucket)
aws s3 ls s3://$B/
aws s3api get-public-access-block --bucket $B
aws s3api get-bucket-encryption --bucket $B
aws s3api get-bucket-lifecycle-configuration --bucket $B
```

## Qué revisar en la consola de AWS

1. **S3 → Buckets → `datalake-noticias-…` → Objetos:** deben aparecer las 7 carpetas.
2. **Permisos:** "Bloquear todo el acceso público" en *Activado*, y la política con `DenyInsecureTransport`.
3. **Propiedades:** cifrado predeterminado SSE-S3 y etiquetas `ManagedBy = terraform`.
4. **Administración:** 3 reglas de ciclo de vida en estado *Enabled*.

## Decisiones y costos

- **Un solo bucket:** requisito del taller. Las zonas se separan por prefijo, y los permisos de IAM se
  podrán limitar por prefijo en fases siguientes.
- **SSE-S3 en lugar de SSE-KMS:** cifrado en reposo sin costo por solicitudes a KMS.
- **Sin versionado:** evita pagar por versiones antiguas. La recuperación se apoya en que Bronze es
  inmutable y en que Silver y Gold se pueden reconstruir desde Bronze.
- **Ciclo de vida:** `tmp/` y `athena-results/` expiran solos; las cargas multiparte incompletas se abortan.
- **`force_destroy = true`:** permite que `terraform destroy` elimine el bucket con datos al terminar el
  laboratorio. En producción se dejaría en `false`.
- **Costo estimado:** con unos pocos MB de RSS y Parquet, el almacenamiento S3 cuesta menos de USD 0,01 al mes.

## Eliminación

```bash
terraform destroy
```

## Evidencias

Ver [EVIDENCIAS.md – sección 1](../../evidencias/docEVIDENCIA/EVIDENCIAS.md#1-infraestructura-base-terraform).
