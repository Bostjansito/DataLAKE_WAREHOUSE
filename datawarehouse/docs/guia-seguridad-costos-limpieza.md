# Seguridad y eliminación de recursos propios

## Identidad, secretos y red

Comprobar `aws sts get-caller-identity` antes de operar y comparar con la consola; no asumir que las evidencias históricas del Data Lake pertenecen a la cuenta actual. Terraform debe utilizar exclusivamente el estado de `datawarehouse/infra/terraform`, sin importar recursos preexistentes por nombre. Revisar el plan y los recursos a crear/modificar/eliminar.

Las bases RDS/DocumentDB y Redshift no son públicos. Solo reciben conexiones del grupo de seguridad EC2 a los puertos correspondientes. EC2 no abre SSH ni Airflow a Internet: usar SSM y túnel a la UI. La salida pública evita NAT Gateway en este laboratorio, pero la dirección IPv4 se factura. El endpoint S3 Gateway da ruta a COPY con enhanced VPC routing.

Verificar TLS y la CA AWS en MySQL, DocumentDB y Redshift; nunca habilitar certificados inválidos para resolver un error. DocumentDB usa `retryWrites=false`, colecciones sin validadores exclusivos de MongoDB y controles de calidad en dbt. El rol de instancia obtiene secretos específicos y acceso al bucket propio; el rol COPY autoriza lectura S3. No añadir claves AWS estáticas a `.env`, código, user-data ni capturas.

Las contraseñas generadas por Terraform pueden estar en el estado aunque la salida sea `sensitive`. Proteger el estado y `.env`, excluirlos de git y restringir sus permisos locales. No publicar planes binarios ni archivos de salida que contengan valores sensibles. La configuración declara cifrado S3/EBS/bases e IMDSv2; su existencia en código no reemplaza verificarla desplegada.

## Orden de retiro y pausa por capturas

La solicitud del usuario autoriza retirar **los recursos creados para la práctica después de confirmar su captura**. No interpretar una captura pendiente como confirmada ni ampliar el alcance a recursos ajenos. Antes de cada retiro, identificar cuenta, región, estado Terraform, inventario y dependencias. Si aparece un recurso desconocido o datos preexistentes, detener esa eliminación y pedir intervención específica.

1. Esperar confirmación explícita de la evidencia del servicio en el chat (una de las cinco imágenes de la matriz o soporte textual cuando corresponda). Conservar imagen, SQL, logs y datos necesarios para reproducir la fase fuera de los recursos a eliminar. Una imagen compartida no elimina la confirmación por servicio.
2. Identificar qué necesita la fase siguiente. El pipeline final requiere fuentes, S3, EC2 y Redshift simultáneamente: no fingir que puede completarse con una base ya eliminada. Para minimizar costo, retirar el servicio ya capturado y recrearlo/sembrarlo cuando corresponda, o informar claramente la retención temporal, dependencia y costo.
3. Desde `datawarehouse/infra/terraform`, inspeccionar `terraform state list` y generar `terraform plan -destroy` para el retiro total. Para una transición entre fases, modificar los flags del ejemplo, generar un plan normal y revisar el alcance; no usar `-target` como sustituto de un plan coherente.
4. Ejecutar únicamente el plan revisado correspondiente al estado propio, después de la confirmación. No ejecutar scripts de limpieza global por prefijo ni borrar todo el inventario de una cuenta.
5. Guardar salidas textuales saneadas del resultado e inventario posterior; no se exige otra imagen. Registrar un comando solicitado no significa que el recurso haya desaparecido. Si el plan falla parcialmente, conservar el estado y resolver dependencias; no repetir destrucciones a ciegas. Confirmar el resultado real antes de publicar la fase.

## Persistencia y pérdida de datos

- **S3 versionado:** `force_destroy=false` impide vaciado automático. Las versiones y delete markers bloquean el borrado y conservan almacenamiento. Identificar el bucket exacto, copiar evidencias/exportaciones y obtener aprobación específica para pérdida irreversible si el alcance no estaba claro; nunca vaciar un bucket ajeno.
- **EC2:** terminar una instancia con volumen raíz `delete_on_termination` elimina ese volumen, no otros volúmenes/snapshots. Detener conserva el costo de EBS. Revisar direcciones públicas y logs.
- **RDS/DocumentDB:** detener no elimina almacenamiento/backups. La configuración protege la eliminación y exige snapshot final: después de confirmar capturas, desactivar `sources_deletion_protection` manteniendo fuentes habilitadas, aplicar ese cambio revisado y solo después planificar su retirada. Configurar identificadores únicos de snapshots finales para no colisionar con una fase anterior. Estos snapshots conservan datos y costo: registrarlos y eliminarlos únicamente tras aclarar la retención autorizada. No trasladar decisiones de pérdida de datos de laboratorio a datos del usuario.
- **Redshift:** el almacenamiento y snapshots pueden sobrevivir al cómputo; revisar namespace, workgroup, snapshots y políticas de retención según el plan real.
- **Secrets Manager:** secretos con recuperación pendiente pueden persistir tras el retiro; no publicar sus valores. Registrar su ventana/estado y posible retención. No forzar borrado de secretos desconocidos.
- **Otros:** verificar EBS, backups, IP públicas, logs y recursos creados fuera del estado; este procedimiento no promete ausencia de cargos en otras regiones/servicios.

## Costos y publicación

Consultar [tarifas y escenarios calculados](costos.md). No se configuraron presupuestos en la cuenta durante la preparación; se recomienda un presupuesto/alerta revisado por el usuario antes de sesiones largas, recordando que alertar no apaga servicios.

Tras cada confirmación, registrar qué fue eliminado y qué queda activo. Solo entonces encargar a **free-worker** el commit/push de la fase sobre `feature/practica-merge`, limitando archivos y evitando cambios ajenos/secretos. La confirmación de una captura no autoriza atribuir éxito a otras pruebas todavía pendientes. Véase [documento de evidencias](../evidencias/docEVIDENCIA/EVIDENCIAS.md).
