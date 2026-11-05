# 07 — Despliegue y limpieza con Terraform

## Principio

Terraform crea recursos declarados por el proyecto; el recurso EC2 es optativo y desactivado por defecto. No se ejecutaron `plan`, `apply` o destroy como parte de este trabajo. Un plan no es autorización para aplicar. Revise el directorio `terraform/` y sus variables/outputs reales antes de usar esta guía; mantenga estado de Terraform protegido y persistente.

La configuración Terraform está en `terraform/`, requiere Terraform `>=1.5,<2.0` y AWS provider `~>5.0`; `bucket_name` es obligatorio. Confirme perfil/región y use un bucket globalmente único.

Si no existe `terraform/terraform.tfvars`, cree uno a partir del ejemplo:

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

Reemplace en `terraform/terraform.tfvars` el nombre de bucket de ejemplo por uno globalmente único y confirme `enable_ec2 = false`.

```bash
terraform -chdir=terraform init
terraform -chdir=terraform validate
terraform -chdir=terraform plan -out=tfplan
```

El fichero del plan se crea en el directorio de trabajo de Terraform. Revíselo localmente y no lo publique si contiene detalles del entorno. Tras aprobación explícita, aplique exactamente el plan revisado con `terraform -chdir=terraform apply tfplan`. No use estos comandos hasta confirmar el perfil AWS activo y la región.

### Publicar el artefacto y habilitar EC2

Primero aplique la infraestructura con `enable_ec2=false` y un nombre real en `terraform.tfvars` (puede copiar `terraform/terraform.tfvars.example`; reemplace allí el nombre de bucket de ejemplo). Solo después del primer `apply`, desde la raíz del repositorio, empaquete los archivos que el bootstrap requiere, incluido `.dockerignore` para excluir `.env` del contexto de construcción Docker; publique el artefacto bajo el URI del output de Terraform.

El comando excluye bytecode/cachés de Python y fija orden, fecha, propietario y cabecera gzip; para los mismos archivos y permisos produce el mismo artefacto:

```bash
tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
  --wildcards --wildcards-match-slash --exclude='*/__pycache__' --exclude='*.pyc' \
  -cf - .dockerignore docker-compose.yml Dockerfile pyproject.toml lake config dags \
  | gzip -n > /tmp/lake.tar.gz
sha256sum /tmp/lake.tar.gz
aws s3 cp /tmp/lake.tar.gz \
  "$(terraform -chdir=terraform output -raw deployment_artifact_uri)" \
  --region REGION_AWS
```

Anote el SHA-256 de ese archivo exacto. En `terraform/terraform.tfvars`, establezca `deployment_artifact_sha256` con el hash real y cambie `enable_ec2 = true`; vuelva a generar y revisar un plan antes de aplicarlo. El bootstrap comprueba el hash y la estructura, extrae a `/opt/lake` y genera contraseña administrativa de Airflow, clave de sesión, contraseña de PostgreSQL y clave Fernet aleatorias dentro de `/opt/lake/.env` con permisos `0600`. No incluya ese `.env` en el archivo ni en evidencia. Output `ssm_port_forward_command` provee el comando de túnel `8080` cuando EC2 está habilitada; requiere AWS Session Manager Plugin local.


## Limpieza responsable

1. Pause el DAG y espere que no haya tareas activas. Exporte y verifique los datos/evidencias/versiones S3 que deban conservarse y haga respaldo del estado Terraform fuera del bucket del proyecto.
2. En `terraform/terraform.tfvars`, establezca `enable_ec2 = false`. Desde la raíz, genere, revise y aplique el plan autorizado que elimina únicamente los recursos opcionales:

   ```bash
   terraform -chdir=terraform plan -out=disable-ec2.tfplan
   terraform -chdir=terraform show disable-ec2.tfplan
   terraform -chdir=terraform apply disable-ec2.tfplan
   ```

3. Confirme quién escribe y qué bucket se va a vaciar: pause todos los productores locales/Airflow y compare `aws sts get-caller-identity` y `terraform -chdir=terraform output -raw bucket_name` con la cuenta y bucket aprobados. Terraform configura `force_destroy = false`; el pipeline role no tiene `s3:ListBucketVersions` ni `s3:DeleteObjectVersion`. Pida una identidad administrativa autorizada para vaciar versiones y marcadores; no amplíe el rol del pipeline.
4. Solo después del respaldo y aprobación, ejecute este ejemplo con el perfil administrativo correcto. **Elimina permanentemente** todos los objetos, versiones y delete markers de un bucket completo. Compara el nombre con el output Terraform, muestra el recuento y requiere confirmación textual exacta; no lo use en un bucket compartido. Requiere permiso para listar y borrar versiones.

   ```bash
   python - <<'PY'
   import boto3

   def main():
       expected = input("Pegue el bucket_name de Terraform: ").strip()
       bucket = input("Nombre exacto del bucket que se vaciará: ").strip()
       if not expected or bucket != expected:
           raise SystemExit("El bucket no coincide con Terraform; no se borró nada.")

       s3 = boto3.client("s3")
       paginator = s3.get_paginator("list_object_versions")

       def object_versions(page):
           return [
               {"Key": item["Key"], "VersionId": item["VersionId"]}
               for item in page.get("Versions", []) + page.get("DeleteMarkers", [])
           ]

       count = sum(
           len(object_versions(page))
           for page in paginator.paginate(Bucket=bucket)
       )
       print(f"Se borrarán permanentemente {count} versiones/marcadores de {bucket}.")
       if input(f"Escriba BORRAR {bucket} para continuar: ").strip() != f"BORRAR {bucket}":
           raise SystemExit("Confirmación incorrecta; no se borró nada.")

       deleted = 0
       for page in paginator.paginate(Bucket=bucket):
           objects = object_versions(page)
           for start in range(0, len(objects), 1000):
               batch = objects[start:start + 1000]
               result = s3.delete_objects(
                   Bucket=bucket, Delete={"Objects": batch}
               )
               if result.get("Errors"):
                   raise RuntimeError("S3 no pudo borrar todas las versiones; revise el estado antes de continuar.")
               deleted += len(result.get("Deleted", []))
       if deleted != count:
           raise RuntimeError("El recuento cambió durante el vaciado; deténgase y vuelva a revisar el bucket.")
       print(f"Se borraron {deleted} versiones/marcadores.")

   if __name__ == "__main__":
       main()
   PY
   ```

   La operación no se ha ejecutado como parte de esta guía. Si hay multipart uploads incompletos, la regla S3 aborta los uploads tras 1 día; espere a esa expiración o abórtelos antes de destruir el bucket.
5. Con el bucket vacío, cree y revise un plan completo de destrucción. Aplique solo ese plan después de aprobación explícita:

   ```bash
   terraform -chdir=terraform plan -destroy -out=destroy.tfplan
   terraform -chdir=terraform show destroy.tfplan
   terraform -chdir=terraform apply destroy.tfplan
   ```

6. Conserve el estado Terraform respaldado según política. Eliminar archivos de estado local no elimina recursos; confirme en la consola que EC2, EBS, IPv4, bucket, Glue, workgroup y recursos restantes ya no existen.

## Capturas recomendadas

Plan revisado; bucket y configuración de seguridad; Glue/workgroup; EC2 opcional con grupo sin ingreso y sesión SSM; revisión de plan de eliminación. Redacte cuenta/ARN donde sea necesario y no capture secretos.
