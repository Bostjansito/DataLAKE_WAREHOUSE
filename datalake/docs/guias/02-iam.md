# Fase 2 – Rol IAM para la EC2 de Airflow

Objetivo: crear la identidad con la que Airflow (en EC2) accede a AWS, **sin llaves de acceso
guardadas en la instancia** y con el mínimo de permisos necesarios.

## Qué se crea

Archivo: [`datalake/infra/terraform/iam.tf`](../../infra/terraform/iam.tf)

| Recurso | Nombre | Propósito |
|---|---|---|
| `aws_iam_role` | `datalake-noticias-lab-airflow-ec2` | Rol que asume la instancia EC2 |
| `aws_iam_policy` | `datalake-noticias-lab-airflow-pipeline` | Permisos del pipeline |
| `aws_iam_role_policy_attachment` (×2) | – | Adjunta la política del pipeline y `AmazonSSMManagedInstanceCore` |
| `aws_iam_instance_profile` | `datalake-noticias-lab-airflow-ec2` | Permite asociar el rol a la EC2 (Fase 5) |

### Permisos de la política del pipeline

| Servicio | Acciones | Alcance |
|---|---|---|
| S3 | Listar el bucket | Solo `datalake-noticias-…` |
| S3 | Leer, escribir, borrar | `silver/`, `gold/`, `quarantine/`, `control/`, `athena-results/`, `tmp/` |
| S3 | Leer y escribir | `bronze/` |
| S3 | **Deny** `DeleteObject` | `bronze/`: los datos originales no se pueden borrar desde el pipeline |
| Comprehend | `Detect*` y `BatchDetect*` (idioma, entidades, frases clave) | `*` (Comprehend no admite restricción por recurso en llamadas síncronas) |
| Glue | Leer base y tablas; crear, actualizar y borrar particiones; `UpdateTable` | Solo la base `datalake_noticias_lab` y sus tablas |
| Athena | Ejecutar y consultar queries | Solo el workgroup `datalake-noticias-lab-wg` |
| SSM | Política administrada `AmazonSSMManagedInstanceCore` | Para entrar a la EC2 con Session Manager |

## Qué hacer con Terraform

```bash
cd datalake/infra
./scripts/tf_apply_evidencia.sh 02-iam \
  aws_iam_role.airflow_ec2 aws_iam_policy.airflow_pipeline \
  aws_iam_role_policy_attachment.airflow_pipeline aws_iam_role_policy_attachment.ssm_core \
  aws_iam_instance_profile.airflow_ec2
# Plan: 5 to add -> Apply complete! Resources: 5 added
```

El script ejecuta `fmt`, `validate`, `plan` y `apply`, y guarda las salidas en `datalake/evidencias/02-iam/`.
Sin el script, el equivalente es `terraform plan -target=... -out=fase.tfplan` y luego `terraform apply fase.tfplan`.

Verificación por CLI:

```bash
aws iam list-attached-role-policies --role-name datalake-noticias-lab-airflow-ec2
aws iam get-instance-profile --instance-profile-name datalake-noticias-lab-airflow-ec2
```

## Qué revisar en la consola de AWS

1. **IAM → Roles → `datalake-noticias-lab-airflow-ec2` → Permisos:** 2 políticas adjuntas.
2. **Relaciones de confianza:** solo `ec2.amazonaws.com` puede asumir el rol.
3. **IAM → Políticas → `datalake-noticias-lab-airflow-pipeline`:** una denegación explícita (S3 `bronze/`)
   y 4 servicios permitidos (Athena, Comprehend, Glue y S3).

## Decisiones

- **Rol de instancia en lugar de llaves de acceso:** las credenciales son temporales y AWS las rota solo;
  no hay secretos en la EC2 ni en el repositorio.
- **Session Manager en lugar de SSH:** no se abre el puerto 22 ni se gestionan llaves `.pem`.
- **Bronze sin borrado:** refuerza que la capa original sea inmutable y que todo se pueda reprocesar desde ella.
- **Costo:** IAM no tiene costo.

## Evidencias

Ver [EVIDENCIAS.md – sección 2](../../evidencias/docEVIDENCIA/EVIDENCIAS.md#2-iam).
