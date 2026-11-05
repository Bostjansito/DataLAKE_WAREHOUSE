# Validación de la preparación local

Fecha de sesión: 2026-11-05. **Esto no es una demostración desplegada en AWS ni una captura confirmada.** No se ejecutó `terraform apply`, no se crearon recursos AWS, no se sembraron bases remotas y no hubo commit/push. La primera captura prevista es S3/Terraform (1.1); no se exige captura de identidad.

## Comprobaciones ejecutadas

| Comprobación | Resultado observado |
|---|---|
| Estado inicial repositorio destino | `feature/practica-merge`, sin cambios al iniciar. El directorio inicial DATA_LAKE-Perez_Quintero no es un repositorio git; el proyecto solicitado con docs/datalake se localizó en DataLAKE_WAREHOUSE. |
| Proyecto previo | Encontrado DE-DW; se inspeccionaron fuentes, modelos y reglas. No se alteró ese repositorio. |
| `aws sts get-caller-identity` | Cuenta `241732001318`, ARN `arn:aws:iam::241732001318:user/user_cli`. [Salida](00-acceso/sts-get-caller-identity.json). |
| Inventario de solo lectura | EC2, RDS, clusters DocumentDB y workgroups Redshift vacíos en us-east-1; buckets cuenta vacíos. Alcance y límites en [inventario](00-acceso/inventario-previo.json). No acredita ausencia de otros servicios/regiones/cargos. |
| Terraform `init -backend=false` | Correcto, Terraform 1.9.8, AWS provider 5.100.0 y random 3.9.1; lockfile generado. Binario disponible en `../TallerAWS/.tools/terraform`, no en PATH inicial. |
| Terraform `validate` | `Success! The configuration is valid.` |
| Terraform `plan -refresh=false -input=false -no-color`, flags por defecto | **8 to add, 0 to change, 0 to destroy**: únicamente bucket/configuración S3 y random ID; no EC2 ni bases ni VPC. No aplicado. |
| Plan con `-var=enable_compute=true -var=enable_sources=true -var=enable_warehouse=true` | **59 to add, 0 to change, 0 to destroy**. Consultó AMI y AZ; no creó recursos. El primer intento detectó output sensible, se corrigió `redshift_username` y el segundo plan terminó correctamente. |
| `.venv-dw/bin/python -m pytest datawarehouse/tests -q` | **23 passed**, Python 3.11.17. Son pruebas offline, no conexiones a AWS/Redshift. |
| `dbt deps --profiles-dir .` | Resuelto `dbt_utils` 1.3.0. |
| `dbt parse --profiles-dir . --no-partial-parse` con host `example.invalid` y credenciales ficticias | Correcto con **dbt-core 1.9.4 / dbt-redshift 1.9.4**, versiones previstas para EC2. Un parse inicial con 1.12.6 también terminó, con avisos de deprecación propios de esa versión; luego se alineó la herramienta a la versión de despliegue. Parse no ejecuta SQL sobre Redshift. |
| `python -m compileall -q datawarehouse/src datawarehouse/dags datawarehouse/infra/scripts` | Sin errores de sintaxis. No acredita importación/ejecución real de Airflow. |
| `bash -n` upload-bundle, remote-deploy, deploy-instance | Correcto. |
| Empaquetado `tar` con lista exacta del bundle hacia `/dev/null` | Correcto tras retirar referencia a setup.py inexistente; no se subió nada a S3. |
| `uv pip install -e datawarehouse`; `aws-dw --help`; `aws-dw seed --help` | Paquete instalable y CLI/argumentos fuente reconocidos; incluye dependencias declaradas, sin contactar fuentes. |
| `git diff --check` y revisión diff de archivos existentes | Sin errores de espacios; cambios raíz limitados a índice/ignorados y traslado de instrucciones. Archivos nuevos revisados por especialistas. |

## Revisión independiente y correcciones

La revisión inicial detectó fallos reales de infraestructura, carga y compatibilidad de modelos; se repararon antes de estas comprobaciones. La revisión funcional final detectó el identificador reservado Redshift `raw`: se citaron esquema/ledger en SQL runtime, consultas auxiliares y fuentes dbt, con regresiones offline. La revisión funcional de infraestructura y la de seguridad detectaron el empaquetado de setup.py inexistente; corregido y cierre confirmado por revisión estática. El plan completo detectó una salida sensible no marcada; corregida y replan exitoso. No se reportaron otros bloqueos de alta certeza en el alcance final revisado. Esto no sustituye comprobaciones desplegadas.

## Lo que falta verificar después de cada captura confirmada

- Permisos de creación/IAM/SSM y cuotas reales de la cuenta; STS no prueba permisos de despliegue.
- Disponibilidad real de las clases RDS/DocumentDB y capacidad Redshift en la región/cuenta.
- Arranque EC2 y servicios systemd, instalación de venvs, UI Airflow mediante SSM y recuperación segura de credenciales.
- Conexiones TLS, siembra RDS/DocumentDB, COPY transaccional y SQL de dbt ejecutado en Redshift.
- Escenarios reales: inicial, defectuosos, repetición, nuevo lote, SCD2, fallo/replay y conciliación agregada.
- Capturas del usuario, retiro efectivo de recursos propios tras confirmar cada una, inventario de residuos y pushes por fase mediante free-worker.

El siguiente paso no es desplegar todo: es revisar identidad, perfil, región y permisos como seguridad operacional, obtener autorización explícita de despliegue/gasto y ejecutar únicamente S3 según la [guía](../docs/guias/01-terraform-s3-red-roles.md). Después solicitar y esperar confirmación de la captura 1.1 antes de continuar o retirar el recurso. No hay captura ni confirmación de acceso.
