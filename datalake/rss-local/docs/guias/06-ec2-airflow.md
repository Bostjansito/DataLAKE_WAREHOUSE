# 06 — EC2 y Airflow

## Objetivo

Habilitar opcionalmente un host de laboratorio, con acceso administrativo mediante Systems Manager y sin puertos entrantes. La instancia puede generar cargos mientras exista.

## Condiciones previas

- Terraform aplica solo tras aprobación; la instancia está deshabilitada por defecto.
- El artefacto reproducible de despliegue debe subirse manualmente al bucket único antes de activar EC2. No habilite la instancia sin verificar clave, hash y versión del artefacto.
- La instancia prevista usa VPC sin NAT, egreso público, SSM-only, cero reglas de entrada, IMDSv2, EBS cifrado y tipo de instancia validado por Terraform. Compruebe IAM y conectividad a SSM antes de `apply`.

## Despliegue y acceso

1. Siga el archivo determinista, cálculo SHA-256 y upload descritos en la sección [Terraform](07-terraform.md); excluya secretos y datos locales.
2. Active el parámetro de EC2 indicado por Terraform y revise `plan`: confirme número/tipo de instancia, volumen cifrado y grupos de seguridad sin ingreso. Aplique solo con autorización.
3. Espere que SSM muestre la instancia como administrada. El output `ssm_port_forward_command` contiene el comando completo con el ID y región del recurso. Tras comprobar ese valor, ejecútelo en terminal local con AWS Session Manager Plugin instalado y permiso `StartSession`. Mantenga el proceso activo durante la sesión; no se abre ingreso SSH ni puerto 8080 al público.

4. Con la sesión activa, visite `http://localhost:8080`; el túnel enlaza puerto local y remoto 8080. Bootstrap genera secretos aleatorios (usuario/contraseña admin, clave web, contraseña PostgreSQL y clave Fernet) en `/opt/lake/.env` con permisos `0600`. Consulte credenciales solo mediante sesión SSM autorizada; no las guarde en Terraform, logs o capturas. Nunca exponga la UI en internet.
5. Capture SSM, Airflow DAG/run y logs identificados por corrida/fuente/tarea, ocultando credenciales. Active el DAG según ventana de laboratorio y concurrencia limitada.
6. Para apagar cuando no se use, use el procedimiento Terraform de limpieza. Parar EC2 no elimina EBS, direcciones, snapshots, bucket ni otros recursos.

## DAG, programación y recuperación

Compose levanta PostgreSQL 16.6, Airflow 2.10.5 con `LocalExecutor`, webserver y scheduler. La UI se vincula a `127.0.0.1:8080` dentro del host y solo se alcanza por el túnel SSM. El DAG `rss_medallion_lake` ejecuta secuencialmente `check → ingest → transform → enrich → publish_silver → build_gold → validate → catalog → athena` y registra estado al final. Tiene `max_active_runs=1`, `max_active_tasks=1` y dos reintentos acotados con espera exponencial (máximo dos minutos).

Por defecto `LAKE_SCHEDULE` está vacío y el DAG nace pausado. Para programarlo solo durante el laboratorio, con sesión SSM autorizada, edite `/opt/lake/.env` como root con `sudoedit` y establezca `LAKE_SCHEDULE='0 */6 * * *'` (cada 6 horas UTC). Reinicie `sudo systemctl restart lake-compose.service` y luego habilite el DAG desde Airflow. Si no necesita programación, déjelo vacío y dispare manualmente desde la UI.

| Parámetro del DAG | Uso |
|---|---|
| `batch_id` | Lote existente para recuperación, o ID destino nuevo cuando se usa `from_bronze`; vacío genera uno desde el run de Airflow. |
| `replay` | Reutiliza manifiesto/checkpoints del mismo `batch_id` sin consultar RSS; recuperación idempotente, no reconstrucción. |
| `from_bronze` | Identificador de un lote Bronze existente; requiere `batch_id` destino nuevo y reconstruye sin copiar XML ni llamar la red. |
| `fail_after` | Falla intencionalmente tras `ingest`, `transform`, `enrich`, `publish_silver`, `build_gold` o `validate`. Para recuperar tras los reintentos controlados, dispara otra ejecución con el mismo `batch_id`, `replay=true` y `fail_after` vacío. |

Para reconstruir desde Bronze, proporciona `from_bronze=<lote original>` y un `batch_id` nuevo (destino). Al reejecutar explícitamente un lote histórico A después de que B sea vigente, no se rebobina la publicación: `catalog`/`athena` responden `skipped_historical_replay`. La herramienta reanuda catalogación del snapshot actual si se invoca con su ID vigente; tras interrupción, vuelve a ejecutar la etapa `catalog` y espera `_control/catalog_status.json` con `status=ready` antes de Athena.

En SSM, los binarios CLI existen dentro del contenedor `scheduler`, no en el host. Desde `/opt/lake`, use `sudo docker compose --env-file .env -f docker-compose.yml exec scheduler rss-lake <subcomando> ...`; `sudo` permite leer `.env` (modo `0600` y dueño root). Airflow ya usa el mismo CLI en sus tareas.

La validación local registrada en `evidence/deployment-validation.json` confirma Docker build/Compose `--wait`, PostgreSQL y scheduler sanos, e importación DagBag sin errores (10 tareas, un escritor, schedule `None`). No se ejecutó el DAG contra AWS; esa prueba y sus capturas siguen pendientes. El contenedor y volúmenes temporales de validación se retiraron; la imagen local cacheada permanece.
Los puertos y órdenes se deben cotejar contra Compose, bootstrap y outputs reales antes de ejecutar. No se desplegó EC2 en esta preparación; capturas y demo son pendientes.
