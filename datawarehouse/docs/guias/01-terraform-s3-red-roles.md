# 01 · Terraform, S3, red y roles

[Índice](../guia-operacion.md) · [Evidencias](../../evidencias/docEVIDENCIA/EVIDENCIAS.md) · [Infraestructura detallada](../../infra/README.md)

## Ejecutar únicamente S3

S3 es almacenamiento administrado: no se arranca un proceso, EC2 ni Airflow para esta fase. Se requiere AWS CLI v2, Terraform >=1.9,<2, conectividad AWS y credenciales vigentes con permisos para crear/configurar/consultar el bucket del proyecto (política, bloqueo público, cifrado, versionado, ownership, lifecycle y etiquetas). STS no acredita esos permisos; no hace falta otorgar AdministratorAccess. Python 3 y tar se usan en fases posteriores, no para crear S3.

**Desde esta sesión se puede preparar y ejecutar Terraform**, tras autorización explícita de creación/gasto y comprobación de credenciales vigentes. AWS CLI está en PATH; Terraform no, pero existe el ejecutable `../TallerAWS/.tools/terraform`. No se ha aplicado el plan ni desplegado S3: las comprobaciones históricas están en [validación](../../evidencias/validacion.md), no son un inventario AWS actualizado. Aquí no se ejecutan escrituras AWS.

Desde la raíz `DataLAKE_WAREHOUSE`, preparar herramientas y comprobar cuenta sin captura ni confirmación de acceso:

```bash
export PATH="$PWD/../TallerAWS/.tools:$PATH"
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1
# Si usa un perfil nombrado, exportar AWS_PROFILE con su nombre real.
aws sts get-caller-identity
aws configure list
umask 077
test -e datawarehouse/infra/terraform/terraform.tfvars || \
  cp datawarehouse/infra/terraform.tfvars.example datawarehouse/infra/terraform/terraform.tfvars
terraform -chdir=datawarehouse/infra/terraform init
terraform -chdir=datawarehouse/infra/terraform plan \
  -var=aws_region=us-east-1 \
  -var=enable_compute=false -var=enable_sources=false -var=enable_warehouse=false \
  -out=storage.tfplan
terraform -chdir=datawarehouse/infra/terraform show -no-color storage.tfplan
```

La cuenta observada anteriormente fue `241732001318`, usuario `user_cli`: contrastarla con la cuenta autorizada antes de continuar; si cambia, detenerse y aclarar el destino. Revisar estado/configuración existentes sin sobrescribirlos. En un estado nuevo, el plan esperado es **8 altas**: bucket, seis configuraciones S3 y random ID; **cero cambios y cero destrucciones**. No aplicar si aparecen VPC, EC2, IAM, bases, Redshift, modificaciones de recursos existentes o destrucciones. No usar `-target` ni importar/adoptar recursos ajenos para forzar ese resultado.

**Solo después de revisar el plan y obtener autorización explícita de despliegue/gasto**, ejecutar el mismo plan guardado:

```bash
terraform -chdir=datawarehouse/infra/terraform apply storage.tfplan
BUCKET="$(terraform -chdir=datawarehouse/infra/terraform output -raw raw_bucket)"
aws s3api get-public-access-block --bucket "$BUCKET" --region "$AWS_REGION"
aws s3api get-bucket-encryption --bucket "$BUCKET" --region "$AWS_REGION"
aws s3api get-bucket-versioning --bucket "$BUCKET" --region "$AWS_REGION"
aws s3api get-bucket-policy --bucket "$BUCKET" --region "$AWS_REGION" \
  --query Policy --output text
```

El nombre será `dw-raw-<sufijo>`; esperar bloqueo público completo, cifrado AES256, versionado Enabled y denegación con `aws:SecureTransport=false`. Mantener credenciales de mínimo privilegio y HTTPS. El bucket nace vacío: no ejecutar seed, extracción, pipeline ni uploads para obtener esta evidencia. El lifecycle actual solo aborta multipart incompletos tras un día; no borra automáticamente objetos ni versiones.

**Primera captura a solicitar:** una imagen legible **1.1**, `datawarehouse/evidencias/01-s3/02-s3.png`, con resumen real de plan/aplicación, nombre del bucket y salidas anteriores. Conservar las salidas completas saneadas como soporte textual; nunca capturar el plan binario, estado ni credenciales. Solicitar **«Captura 1.1 tomada»**, indicando el archivo, y pausar antes de habilitar otro servicio o retirar S3. No exigir imágenes por pestaña.

**Costos:** esta fase no crea cómputo, IPv4, red, bases ni Redshift. S3 factura almacenamiento, solicitudes y transferencias que correspondan; versiones e incompletos retenidos también cuentan. Un bucket vacío no implica tarifa fija de cómputo, pero no se garantiza costo cero ni Free Tier. Consultar [tarifas/supuestos registrados](../costos.md) y [precios oficiales S3](https://aws.amazon.com/s3/pricing/); el total depende de GB, solicitudes, transferencia y retención reales. Observabilidad adicional (access logging, eventos de datos CloudTrail y métricas CloudWatch) es recomendable fuera de esta captura mínima, revisando costo y destinos cifrados antes de habilitarla; no la crea este módulo.

Editar `terraform.tfvars` y generar **otro plan revisado** por cada fase; aplicar únicamente el archivo del plan revisado:

| Fase | enable_compute | enable_sources | enable_warehouse |
|---|---|---|---|
| S3 | false | false | false |
| Runtime | true | false | false |
| Fuentes | true | true | false |
| Warehouse | true | true | true |

```bash
terraform -chdir=datawarehouse/infra/terraform plan -out=fase.tfplan
terraform -chdir=datawarehouse/infra/terraform apply fase.tfplan
```

La red prevista tiene tres AZ, subredes públicas y privadas, endpoint gateway S3, sin NAT ni endpoints interface. EC2 usa IPv4 pública para salida, sin puertos entrantes; las fuentes y Redshift son privados. Reunir VPC/rutas/endpoint y rol EC2 con política S3/confianza en **una imagen 2.1**, con soporte textual completo. Confirmar VPC e IAM/EC2 usando ese mismo archivo. El rol COPY solo existe al habilitar warehouse: incluir confianza/política S3 en **6.1**, no adelantar su creación ni pedir otra imagen. Registrar ampliaciones de permisos a secretos en texto cuando se habiliten fuentes/warehouse. Fuentes y warehouse dependen del grupo de seguridad de compute. No presumir conectividad hasta comprobarla.

La comprobación EC2 3.1 de la guía 05 comparte esta imagen de runtime (`02-runtime/03-runtime.png`) con 2.1. Mantener una pausa y confirmación para VPC, IAM/EC2 y EC2, referenciando ese archivo, antes de habilitar la fase siguiente o retirar recursos.

El estado local y los planes pueden contener contraseñas: protegerlos, no subirlos ni capturarlos. No usar el bucket raw como backend de estado. Tras cada captura confirmada retirar solo recursos propios innecesarios si no son dependencias y delegar publicación a free-worker; de otro modo registrar su retención y costo. Ver [retiro](07-retiro-dependencias.md).
