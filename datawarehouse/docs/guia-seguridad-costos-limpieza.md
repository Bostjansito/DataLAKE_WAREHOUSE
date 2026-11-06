# Seguridad y eliminación de recursos propios

## Identidad, secretos y red

Comprobar `aws sts get-caller-identity` antes de operar y comparar con la consola; no asumir que las evidencias históricas del Data Lake pertenecen a la cuenta actual. Terraform debe utilizar exclusivamente el estado de `datawarehouse/infra/terraform`, sin importar recursos preexistentes por nombre. Revisar el plan y los recursos a crear/modificar/eliminar.

Las bases RDS/DocumentDB y Redshift no son públicos. Solo reciben conexiones del grupo de seguridad EC2 a los puertos correspondientes. EC2 no abre SSH ni Airflow a Internet: usar SSM y túnel a la UI. La salida pública evita NAT Gateway en este laboratorio, pero la dirección IPv4 se factura. El endpoint S3 Gateway da ruta a COPY con enhanced VPC routing.

Verificar TLS y la CA AWS en MySQL, DocumentDB y Redshift; nunca habilitar certificados inválidos para resolver un error. DocumentDB usa `retryWrites=false`, colecciones sin validadores exclusivos de MongoDB y controles de calidad en dbt. El rol de instancia obtiene secretos específicos y acceso al bucket propio; el rol COPY autoriza lectura S3. No añadir claves AWS estáticas a `.env`, código, user-data ni capturas.

Las contraseñas generadas por Terraform pueden estar en el estado aunque la salida sea `sensitive`. Proteger el estado y `.env`, excluirlos de git y restringir sus permisos locales. No publicar planes binarios ni archivos de salida que contengan valores sensibles. La configuración declara cifrado S3/EBS/bases e IMDSv2; su existencia en código no reemplaza verificarla desplegada.

Los secretos maestros nativos gestionados por RDS, DocumentDB y Redshift se eliminan con su recurso administrador según el ciclo de vida del servicio. Un snapshot no conserva la credencial runtime: planificar recuperación o creación de credenciales nuevas al restaurar y actualizar los ARN y endpoints correspondientes. No respaldar valores secretos en evidencias.

## Cierre definitivo autorizado

El usuario autorizó eliminar definitivamente todos los recursos propios de la práctica y sus datos de prueba, sin esperar capturas, carga ni incrementales. **La eliminación sin snapshot final y de backups implica pérdida irreversible**; no extender esta autorización a recursos ajenos o datos preexistentes. Conservar código, estado Terraform y evidencias locales. No publicar `datawarehouse/evidencias/06-redshift/06_dw_queryredshift.png`: contiene nombres, correos y teléfonos generados.

Antes de operar, comprobar `aws sts get-caller-identity`: la cuenta debe ser `241732001318`, región `us-east-1`, y el estado propio está en `datawarehouse/infra/terraform`. Ante recursos desconocidos o dependencias inesperadas, detenerse; no ejecutar limpieza global por prefijo.

### Estado observado y pendiente

- Confirmado: EC2 `i-08a26829d2db22844` terminada y su EBS inexistente; bucket `dw-raw-3fdd5d35fec3c75d` eliminado tras borrar 20 versiones, sin delete markers ni cargas multipart pendientes; workgroup Redshift `dw-workgroup` eliminado.
- Confirmado después del retiro: `dw-namespace` y `dw-workgroup` responden `ResourceNotFoundException`; los snapshots y recovery points Redshift son `[]`, y el secreto administrado Redshift ya no aparece, incluyendo secretos programados para eliminación. Ambos roles propios EC2/Redshift, el perfil EC2 y la política `dw-redshift-s3-read` responden `NoSuchEntity`. Se retiraron los grupos de seguridad EC2/Redshift y sus reglas. Terraform completó un plan con **0 creados, 0 modificados y 15 destruidos**; EC2, workgroup y bucket se habían retirado previamente mediante CLI.
- Las bases siguen pendientes de intervención manual: RDS `dw-mysql` y DocumentDB `dw-docdb`/`dw-docdb-instance` estaban `available`, con protección contra eliminación y retención de backup de un día. MySQL es `db.t3.micro` con 20 GiB; DocumentDB es `db.t3.medium`. Se observó un snapshot automático de MySQL y recuperación a un punto en el tiempo de DocumentDB, sin snapshots manuales de ambas bases. El inventario final de secretos contiene únicamente los dos secretos administrados de estas bases, ambos activos y sin fecha de eliminación programada; no se consultaron sus valores.
- La auditoría en `us-east-1` no encontró NAT Gateway, EIP, log groups, snapshots EBS ni volúmenes; no extrapolar ese resultado a otras regiones o servicios. Las ENI y el endpoint Interface administrados por Redshift desaparecieron. El túnel local `dw-airflow-tunnel` ya estaba terminado.
- Un segundo plan selectivo completó **0 creados, 0 modificados y 13 destruidos**: tres subredes públicas, las dos tablas de rutas personalizadas y sus seis asociaciones, el gateway de Internet y el endpoint S3. La consulta posterior devuelve cero endpoints, únicamente la tabla principal `rtb-0244d0504ab559a98` y tres subredes privadas: `subnet-07c49499f98259c31`, `subnet-0d5afd36fd80d97e2`, `subnet-0bc1d085bf557e5ca`. Se conservan VPC `vpc-0f1f8aa80c3b8ddf3`, grupos de seguridad RDS/DocumentDB y sus ENI administradas porque las bases los necesitan. No manipular esas ENI directamente.

### Bases: ejecución manual por el usuario

Las herramientas de asistencia no pueden modificar el RDS existente ni eliminar la instancia o el clúster DocumentDB. Los comandos siguientes son **para ejecución manual por el usuario**, no fueron ejecutados por esta guía. Confirmar identidad y región, revisar que los identificadores sigan siendo los propios y detenerse si una operación falla. Las eliminaciones son asíncronas: comprobar que terminan antes del paso siguiente.

Para RDS, desactivar la protección, verificar en la respuesta o mediante `describe` que `DeletionProtection` sea `false`, y después eliminar sin snapshot final y con eliminación de backups automáticos:

```bash
aws sts get-caller-identity
aws rds modify-db-instance --region us-east-1 --db-instance-identifier dw-mysql --no-deletion-protection --apply-immediately
aws rds describe-db-instances --region us-east-1 --db-instance-identifier dw-mysql --query 'DBInstances[0].[DBInstanceStatus,DeletionProtection]'
aws rds delete-db-instance --region us-east-1 --db-instance-identifier dw-mysql --skip-final-snapshot --delete-automated-backups
aws rds wait db-instance-deleted --region us-east-1 --db-instance-identifier dw-mysql
```

Para DocumentDB, desactivar la protección y comprobar `DeletionProtection=false`; eliminar primero la instancia, esperar su desaparición y luego eliminar el clúster sin snapshot final:

```bash
aws docdb modify-db-cluster --region us-east-1 --db-cluster-identifier dw-docdb --no-deletion-protection --apply-immediately
aws docdb describe-db-clusters --region us-east-1 --db-cluster-identifier dw-docdb --query 'DBClusters[0].[Status,DeletionProtection]'
aws docdb delete-db-instance --region us-east-1 --db-instance-identifier dw-docdb-instance
aws docdb wait db-instance-deleted --region us-east-1 --db-instance-identifier dw-docdb-instance
aws docdb delete-db-cluster --region us-east-1 --db-cluster-identifier dw-docdb --skip-final-snapshot
aws docdb describe-db-clusters --region us-east-1 --db-cluster-identifier dw-docdb
```

Repetir el último `describe` hasta que informe `DBClusterNotFoundFault`; un estado `deleting` aún no confirma la desaparición. Otros errores requieren revisión y no equivalen a una eliminación confirmada.

Al borrar el clúster se eliminan sus backups automáticos; los snapshots manuales, si aparecieran, no se eliminan automáticamente. Los snapshots manuales de RDS tampoco se eliminan con la instancia. Comprobar el inventario real de backups, snapshots y secretos administrados tras la eliminación; no borrar secretos desconocidos.

### Terraform, red y costos residuales

No ejecutar `terraform apply` normal ni reutilizar planes históricos: la configuración puede recrear recursos ya retirados. No modificar por ahora tfvars ni HCL. Mientras RDS y DocumentDB existan, **no ejecutar un destroy total**. Para cualquier mutación permitida restante, generar desde el estado propio únicamente un `terraform plan -destroy` selectivo, inspeccionar cada acción y dependencia y aplicar solo el plan revisado; no incluir modificaciones o eliminaciones de las bases ni de la red que todavía necesitan. Si el plan falla parcialmente, conservar el estado y revisar el resultado real antes de continuar.

Una vez que el usuario haya eliminado ambas bases y se confirme su desaparición, debe retirar también los grupos de parámetros/subred RDS existentes, que la asistencia no modifica. Los siguientes comandos son manuales, se ejecutan solo cuando no quedan bases consumidoras y no fueron ejecutados por el asistente:

```bash
aws rds delete-db-parameter-group --region us-east-1 --db-parameter-group-name dw-mysql-params
aws rds delete-db-subnet-group --region us-east-1 --db-subnet-group-name dw-db-subnet-group
aws docdb delete-db-cluster-parameter-group --region us-east-1 --db-cluster-parameter-group-name dw-docdb-params
aws docdb delete-db-subnet-group --region us-east-1 --db-subnet-group-name dw-docdb-subnet-group
```

Después, generar desde el estado conservado un nuevo plan de destrucción, inspeccionarlo y retirar solo los grupos de seguridad y la red propios liberados. El refresco debe constatar la ausencia de bases y grupos eliminados manualmente; si el plan aún propone modificar o destruir un recurso RDS, o un clúster/instancia DocumentDB, no aplicarlo mediante asistencia. No retirar la VPC ni subredes privadas mientras existan dependencias; no importar ni eliminar recursos ajenos. Los outputs Terraform pueden estar desactualizados después de un retiro con `-target`: no son evidencia de existencia ni autorización para recrear servicios.

Hasta entonces RDS y DocumentDB pueden seguir generando cargos por instancia, almacenamiento y backups; snapshots, recovery points, secretos, direcciones públicas u otros recursos retenidos también pueden generar cargos según servicio y retención. Detener una base no equivale a eliminar su almacenamiento o backups. Revisar facturación e inventario final; la auditoría indicada no garantiza ausencia de cargos en toda la cuenta.

## Costos y publicación

Consultar [tarifas y escenarios calculados](costos.md). No se configuraron presupuestos en la cuenta durante la preparación; se recomienda un presupuesto/alerta revisado por el usuario antes de sesiones largas, recordando que alertar no apaga servicios.

Registrar resultados reales y pendientes con salidas saneadas; no atribuir éxito a capturas o pruebas no realizadas. Preservar las evidencias locales y evitar publicar datos sensibles o secretos. Véase [documento de evidencias](../evidencias/docEVIDENCIA/EVIDENCIAS.md).
