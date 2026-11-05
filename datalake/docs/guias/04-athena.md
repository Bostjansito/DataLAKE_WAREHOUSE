# Fase 4 – Workgroup de Amazon Athena

Objetivo: tener un espacio de consultas controlado, con resultados en el bucket del data lake y un
límite que evite consultas costosas por error.

## Qué se crea

Archivo: [`datalake/infra/terraform/athena.tf`](../../infra/terraform/athena.tf)

| Configuración | Valor | Por qué |
|---|---|---|
| Nombre | `datalake-noticias-lab-wg` | Separa las consultas del taller del workgroup `primary` |
| Motor | Athena engine version 3 | Versión actual (Trino) |
| Resultados | `s3://…/athena-results/` | Mismo bucket; la regla de ciclo de vida los borra a los 7 días |
| Cifrado de resultados | SSE-S3 | Sin costo adicional |
| Forzar configuración | Activado | Ningún cliente puede cambiar la ubicación de resultados ni quitar el límite |
| Límite por consulta | **100 MB** escaneados | Una consulta que lea más se cancela sola |
| Métricas en CloudWatch | Activado | Permite ver bytes escaneados por consulta |

## Qué hacer con Terraform

```bash
cd datalake/infra
./scripts/tf_apply_evidencia.sh 04-athena aws_athena_workgroup.data_lake
# Plan: 1 to add -> Apply complete! Resources: 1 added
```

El límite se puede cambiar con la variable `athena_bytes_scanned_cutoff` en `terraform.tfvars`
(el mínimo de AWS es 10 MB).

## Qué hacer en la consola de AWS

1. **Athena → Administración → Grupos de trabajo → `datalake-noticias-lab-wg`:** revisar ubicación de
   resultados, cifrado SSE_S3, "Invalidar la configuración del cliente: Activado" y, en *Controles de
   ejecución*, "Data scanned limit: 100 MB".
2. **Editor de consultas:** seleccionar el workgroup `datalake-noticias-lab-wg` (arriba a la derecha) y la
   base `datalake_noticias_lab`. Las 7 tablas aparecen en el panel izquierdo.
3. Las consultas del taller (Fase 10) se ejecutarán siempre en este workgroup.

## Costo

Athena cobra USD 5 por TB escaneado, con un mínimo de 10 MB por consulta (unos USD 0,00005).
Con Parquet, particiones por fecha y el límite de 100 MB, cada consulta del taller cuesta fracciones de centavo.

## Evidencias

Ver [EVIDENCIAS.md – sección 4](../../evidencias/docEVIDENCIA/EVIDENCIAS.md#4-amazon-athena).
