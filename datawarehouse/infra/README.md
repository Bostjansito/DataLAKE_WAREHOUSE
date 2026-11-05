# Infraestructura del warehouse (Terraform)

## Estado y límites

Este código no demuestra un despliegue ni una ejecución del pipeline. Comprobar identidad AWS, perfil y región antes de operar, **sin captura ni confirmación de acceso**. La primera evidencia es S3/Terraform (1.1); seguir los [pasos para ejecutar únicamente S3](../docs/guias/01-terraform-s3-red-roles.md#ejecutar-únicamente-s3). Crear recursos requiere autorización explícita de despliegue y gasto. Después de cada servicio, pausar para confirmar su evidencia antes de avanzar o retirar recursos. No hay destrucción automática ni limpieza de recursos ajenos.

Prerequisitos locales: AWS CLI v2 con sesión válida, Python 3, tar y Terraform >=1.9,<2 en PATH. Si se usa un binario fuera del PATH, añadir su directorio al PATH antes de usar los scripts. Terraform fija AWS provider ~>5.100 y random ~>3.7; conservar el lockfile generado por init.

Desde la raíz del repositorio:

```bash
aws sts get-caller-identity
export AWS_REGION=us-east-1
```

## Fases explícitas

Los tres flags predeterminados son false. La fase inicial crea **solo el bucket S3** y su configuración (bloqueo público, ACL deshabilitadas, SSE-S3, versionado y denegación HTTP). No crea VPC ni EC2. No se promete gratuidad.

```bash
umask 077
cp datawarehouse/infra/terraform.tfvars.example datawarehouse/infra/terraform/terraform.tfvars
terraform -chdir=datawarehouse/infra/terraform init
terraform -chdir=datawarehouse/infra/terraform plan -out=storage.tfplan
# Solo tras revisar plan, cuenta, región y autorización:
terraform -chdir=datawarehouse/infra/terraform apply storage.tfplan
```

Editar terraform.tfvars, revisar un plan nuevo y aplicar solo el plan revisado para cada fase:

| Fase | enable_compute | enable_sources | enable_warehouse |
|---|---|---|---|
| S3 | false | false | false |
| Runtime | true | false | false |
| Fuentes | true | true | false |
| Warehouse | true | true | true |

Sources y warehouse requieren compute porque sus grupos de seguridad autorizan exclusivamente el SG real de EC2. Los outputs de módulos deshabilitados usan try(..., null); Terraform puede omitir outputs null. raw_bucket_arn existe en root.

La VPC tiene tres AZ con subred privada y pública por AZ; RDS, DocumentDB y Redshift son privados. Las rutas privadas tienen acceso S3 mediante **gateway endpoint**, necesario para COPY con enhanced VPC routing. No se crean NAT ni endpoints interface adicionales. EC2 sí recibe IPv4 pública para paquetes, SSM y Secrets Manager por HTTPS; no tiene ningún puerto entrante ni clave SSH. No equivale a una EC2 sin Internet. IMDSv2 obligatorio, EBS cifrado gp3 y créditos T3 standard (sin cobro por créditos unlimited; puede limitar CPU).

MySQL exige transporte seguro. DocumentDB usa sus propios subnet group y cluster parameter group con TLS habilitado, replicaSet=rs0 y retryWrites=false. Redshift workgroup referencia namespace_name; el namespace tiene iam_roles/default_iam_role_arn y el rol COPY confía en redshift y redshift-serverless. El endpoint de conexión es endpoint[0].address.

## Estado, credenciales y permisos

El backend predeterminado es local: **tfstate y planes contienen contraseñas**, aunque la consola diga sensitive. El .gitignore raíz excluye tfstate, planes, tfvars, .terraform, .env y .build. Usar umask 077, almacenamiento local privado/cifrado y no subir state a evidencias o al bundle. Para colaboración configurar previamente un backend remoto privado cifrado con bloqueo; el bucket raw no es un backend de estado.

EC2 usa AmazonSSMManagedInstanceCore; las políticas de datos solo permiten el bucket de este stack y GetSecretValue en los ARN concretos de secretos habilitados. No tiene Secrets Manager wildcard ni Redshift Data API general. El wildcard de objetos se limita al bucket propio; la política administrada SSM conserva los permisos que necesita el agente. No hay claves AWS estáticas ni contraseñas en user data. runtime.py consulta secretos al iniciar scheduler/CLI y los pasa por entorno, sin escribir un .env de secretos ni imprimirlos. Reiniciar scheduler después de rotar credenciales. El administrador de EC2/SSM puede acceder a esos procesos; restringir ese acceso.

## Bundle y despliegue reproducible por SSM

Después de habilitar las fases necesarias y esperar la instancia gestionada por SSM:

```bash
bash datawarehouse/infra/scripts/upload-bundle.sh
terraform -chdir=datawarehouse/infra/terraform output -raw ec2_instance_id
# Usar el ID anterior y la URI EXACTA de bundle impresa por upload:
bash datawarehouse/infra/scripts/remote-deploy.sh "$INSTANCE_ID" "$BUNDLE_URI"
# La salida anterior es COMMAND_ID. Revisar sin volver a ejecutar:
aws ssm get-command-invocation --instance-id "$INSTANCE_ID" --command-id "$COMMAND_ID" --region "$AWS_REGION"
```

upload-bundle.sh empaqueta únicamente src, dags, dbt, metadatos/dependencias e infra/scripts; excluye paquetes dbt descargados, cachés, target y logs. Sube deploy/bundle-TIMESTAMP.tar.gz y deploy/runtime.json, este último contiene región, bucket y ARN, **no contraseñas**. No empaqueta Terraform/state/.env. No modifica nada fuera del stack.

User data instala Python 3.11 y las CA oficiales; no obtiene secretos ni ejecuta el pipeline. remote-deploy.sh espera cloud-init, descarga el bundle explícito y la configuración y ejecuta deploy-instance.sh. Este instala la aplicación en /opt/ecommerce/app y tres venv separados:

- runtime: requirements.txt y paquete aws_dw real;
- airflow-venv: Airflow 2.10.5 con constraints oficiales Python 3.11;
- dbt: dbt-core/dbt-redshift 1.9.4; dbt deps resuelve los paquetes declarados.

Se migra la base local SQLite de Airflow y se inician scheduler y webserver como unidades systemd independientes, SequentialExecutor, sin ejemplos, con único DAG ecommerce_dw_pipeline. El webserver escucha **solo en 127.0.0.1:8080**, con un worker y usuario admin generado con contraseña aleatoria. Es un runtime docente de un nodo, no alta disponibilidad ni instalación productiva. Actualizar bundle detiene ambos servicios; no hacerlo durante una carga activa. SSM requiere permisos del operador para SendCommand/GetCommandInvocation/StartSession y PassRole al provisionar según corresponda; no se amplían automáticamente sus permisos.

## Airflow UI y captura del DAG

El bootstrap crea admin una única vez; conserva la contraseña en /opt/ecommerce/airflow/admin-password con modo 0600, propiedad ecommerce. La creación usa FAB dentro del proceso (no pasa contraseñas por argumentos CLI) y retiene salida/errores sin publicarlos; nunca ejecutar con bash -x, imprimir el archivo ni incluir la contraseña en evidencias. Un operador root/SSM puede acceder al archivo. No se almacena en git, Terraform, S3 ni user data.

Abrir el túnel desde la estación local (AWS CLI y Session Manager plugin):

```bash
aws ssm start-session --target "$INSTANCE_ID" --region "$AWS_REGION" --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["8080"],"localPortNumber":["8080"]}'
```

Mantener esa terminal abierta y visitar http://127.0.0.1:8080. Para obtener la contraseña **sin texto claro en logs SSM**, cifrarla hacia una clave RSA efímera de la estación local:

```bash
# LOCAL: guardar la privada exclusivamente aquí; no subirla a EC2.
umask 077
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out ui-private.pem
openssl pkey -in ui-private.pem -pubout -out ui-public.pem
base64 -w0 ui-public.pem
# Copiar esta salida pública para el siguiente comando remoto.
```

En otra sesión SSM interactiva, pegar únicamente la clave PÚBLICA anterior:

```bash
printf '%s' 'PEGAR_PUBLICA_BASE64' | base64 -d > /tmp/ui-public.pem
sudo openssl pkeyutl -encrypt -pubin -inkey /tmp/ui-public.pem -in /opt/ecommerce/airflow/admin-password -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 | base64 -w0
```

Copiar solo el criptograma resultante a un archivo local ui-password.b64, y descifrarlo localmente:

```bash
base64 -d ui-password.b64 | openssl pkeyutl -decrypt -inkey ui-private.pem -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256
```

Usar la salida local para iniciar sesión como admin; no grabar esa terminal ni capturar la contraseña. La contraseña no cruza los logs SSM en texto claro; proteger/eliminar la privada y los archivos locales al terminar. Reunir la UI real del DAG ecommerce_dw_pipeline con ejecución exitosa y el resumen terminal dbt en **una imagen 7.1**, según la [matriz de cinco imágenes](../evidencias/docEVIDENCIA/EVIDENCIAS.md); no pedir una captura del DAG vacío ni imágenes por ejecución/log. Nunca incluir credenciales. No abrir 8080 ni SSH en el SG.

## Operación remota

```bash
aws ssm start-session --target "$INSTANCE_ID" --region "$AWS_REGION"
# En la sesión de EC2, ejecutar como usuario sin privilegios:
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli --help
# Solo una vez sobre fuentes nuevas; seed no es un comando de recuperación:
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli seed --customer-count 50 --product-count 25 --order-count 100 --review-count 150 --event-count 500 --seed 42 --bad-records 2
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/airflow-venv/bin/airflow dags trigger ecommerce_dw_pipeline --conf '{"batch_id":0}'
sudo journalctl -u ecommerce-airflow.service --since today
```

La carga fuente inicial y append de lotes son comandos explícitos del CLI (ver --help y guía de operación); no los ejecuta Terraform. No disparar el DAG antes de poblar las fuentes. La ejecución inicial usa batch_id 0; para los siguientes lotes generar primero los datos correspondientes. El DAG llama al CLI real con DW_PYTHON, no un segundo pipeline paralelo.

Contrato runtime: MYSQL_HOST/PORT/USER/PASSWORD/DATABASE, MYSQL_SSL_CA; MONGO_URI/MONGO_DATABASE/MONGO_TLS_CA_FILE; AWS_REGION/S3_BUCKET; REDSHIFT_HOST/PORT/USER/PASSWORD/DATABASE/REDSHIFT_COPY_ROLE_ARN. DBT_BIN, DBT_PROJECT_DIR, DBT_PROFILES_DIR y DW_PYTHON apuntan a las rutas anteriores. MySQL/DocDB verifican CA global-bundle.pem; Redshift verifica hostname/CA con PGSSLROOTCERT y /opt/ecommerce/.postgresql/root.crt. Nunca deshabilitar verificación TLS para resolver conectividad.

## Costes persistentes y retención

No se publican precios estimados no verificados: dependen de región, consumo, fecha, créditos y elegibilidad de la cuenta. Revisar precios oficiales y presupuesto antes de activar cada fase:

- [S3](https://aws.amazon.com/s3/pricing/): almacenamiento actual **y versiones anteriores**, requests, transferencias. El lifecycle solo aborta multipart incompletos; no vence evidencia/datos.
- [EC2/EBS](https://aws.amazon.com/ec2/pricing/on-demand/): instancia mientras corre, disco mientras exista, [IPv4 pública](https://aws.amazon.com/vpc/pricing/). Parar EC2 no elimina EBS ni otros servicios.
- [RDS](https://aws.amazon.com/rds/mysql/pricing/) y [DocumentDB](https://aws.amazon.com/documentdb/pricing/): instancias, almacenamiento, I/O y backups; existen independientemente del DAG. Son fuentes con capacidad provisionada, no scale-to-zero.
- [Redshift Serverless](https://aws.amazon.com/redshift/pricing/): cómputo de consultas y almacenamiento persistente aun sin consultas; base_capacity=8 no es un límite de gasto ni un presupuesto.
- [Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/): secretos almacenados y llamadas. Logs, snapshots y transferencia también pueden persistir.

Deshabilitar flags es una **eliminación de recursos**, no un botón de pausa. RDS/DocDB tienen deletion_protection=true y snapshot final obligatorio, bucket force_destroy=false; un plan destructivo requiere decisión explícita de retención, copia y autorización. No se incluye auto-destroy ni comando de vaciado de cuenta. No borrar snapshots, versiones o secretos ajenos para solucionar conflictos de nombres.

### Retirar capacidad tras las capturas (solo este stack)

1. Confirmar evidencia completa, ausencia de cargas activas y política de retención. Respaldar Redshift si sus datos deben conservarse, antes de retirar el namespace; por ejemplo `aws redshift-serverless create-snapshot --namespace-name dw-namespace --snapshot-name dw-evidence-final-20261105 --region "$AWS_REGION"` usando un nombre nuevo y esperar su disponibilidad. Los snapshots retenidos siguen generando cargos.
2. Mantener enable_compute/enable_sources/enable_warehouse tal como están. En terraform.tfvars fijar **sources_deletion_protection=false** y nombres únicos deliberados en mysql_final_snapshot_identifier/docdb_final_snapshot_identifier (por ejemplo dw-mysql-final-20261105 y dw-docdb-final-20261105). No reutilizar nombres de snapshots existentes ni eliminarlos para resolver colisiones. skip_final_snapshot permanece false.
3. Crear un plan `terraform -chdir=datawarehouse/infra/terraform plan -out=unprotect.tfplan`, revisar que solo cambia protección/nombres de snapshots y aplicar ese plan con `terraform -chdir=datawarehouse/infra/terraform apply unprotect.tfplan`. Esta primera aplicación no elimina las BD; desactiva la protección antes del paso destructivo.
4. Solo con autorización, cambiar los tres flags enable_* a false. Crear un plan nuevo `terraform -chdir=datawarehouse/infra/terraform plan -out=retire-compute.tfplan`; comprobar explícitamente las eliminaciones de EC2, fuentes, warehouse, IAM y red. Aplicar únicamente ese plan revisado con `terraform -chdir=datawarehouse/infra/terraform apply retire-compute.tfplan`. RDS y DocDB crean los snapshots finales configurados. S3 y sus versiones permanecen; no confundir esto con coste cero.
5. Revisar inventario/costes del stack y registrar qué snapshots, secretos en recuperación, objetos/versiones S3 y otras evidencias se conservan. Su borrado requiere decisión separada de retención; no hay vaciado global de cuenta. Si se recrea el entorno, volver a sources_deletion_protection=true antes del siguiente despliegue y considerar la ventana de recuperación de los nombres de secretos.


## Fuentes de API

- [Workgroup AWS provider 5.100](https://github.com/hashicorp/terraform-provider-aws/blob/v5.100.0/website/docs/r/redshiftserverless_workgroup.html.markdown): namespace_name, tres subnets/AZ, endpoint y enhanced routing.
- [Namespace](https://github.com/hashicorp/terraform-provider-aws/blob/v5.100.0/website/docs/r/redshiftserverless_namespace.html.markdown): asociación de roles.
- [DocDB subnet group](https://github.com/hashicorp/terraform-provider-aws/blob/v5.100.0/website/docs/r/docdb_subnet_group.html.markdown) y [cluster parameter group](https://github.com/hashicorp/terraform-provider-aws/blob/v5.100.0/website/docs/r/docdb_cluster_parameter_group.html.markdown).
- [Truststore RDS/DocDB](https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem), [CA Redshift](https://s3.amazonaws.com/redshift-downloads/amazon-trust-ca-bundle.crt), [constraints Airflow](https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.11.txt).
- [Creación de usuarios FAB en Airflow 2.10.5](https://github.com/apache/airflow/blob/2.10.5/airflow/providers/fab/auth_manager/cli_commands/user_command.py): la misma API in-process usada por el bootstrap para no exponer password en argv.

No se ejecutaron init/validate/plan, checks, instalación o despliegue durante esta reparación. El responsable debe revisar y verificar antes de operar AWS.
