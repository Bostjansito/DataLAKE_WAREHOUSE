# Fase 5 – Airflow en EC2

Objetivo: una instancia EC2 con Apache Airflow que ejecute el pipeline sin intervención manual. Debe ser
reproducible con Terraform, no exponer puertos y costar lo mínimo.

## Qué se crea

Archivos: [`ec2_airflow.tf`](../../infra/terraform/ec2_airflow.tf) y
[`templates/airflow_user_data.sh.tftpl`](../../infra/terraform/templates/airflow_user_data.sh.tftpl)

| Recurso | Configuración | Por qué |
|---|---|---|
| `aws_instance.airflow` | Amazon Linux 2023, `t3.medium`, gp3 20 GB cifrado, IMDSv2 obligatorio | 4 GB alcanzan para el webserver, el scheduler y las tareas, con 2 GB de swap de respaldo |
| `aws_security_group.airflow` | **Sin reglas de entrada**. Salida solo 443/80 | No se abre el 22 ni el 8080. Se administra con Session Manager |
| IP pública | Sí, en la subred por defecto | Salida a Internet sin NAT Gateway, que costaría USD 0,045/h |
| Rol | `datalake-noticias-lab-airflow-ec2` (Fase 2) | Las credenciales salen del perfil de la instancia; no hay llaves en archivos |
| `aws_s3_object.datalake_code` | `s3://…/deploy/datalake.zip` (src, dags, config, requirements) | Terraform empaqueta el código; la instancia solo lo puede **leer** |
| `random_password` + `aws_ssm_parameter` | SecureString `/datalake-noticias/lab/airflow/admin-password` | La contraseña del admin no está en el repositorio ni en user_data |

La política IAM del pipeline suma dos permisos: `s3:GetObject` sobre `deploy/*` y `ssm:GetParameter` sobre
`/datalake-noticias/lab/airflow/*`.

## Qué instala el arranque (user_data)

1. Python 3.11 y Airflow **2.10.5** en `/opt/airflow/venv`, con el archivo de *constraints* oficial.
2. `/opt/datalake/deploy.sh`: descarga el zip de S3, instala `requirements.txt` y reemplaza `/opt/datalake/app`.
3. Configuración en `/etc/sysconfig/airflow`:
   - `SequentialExecutor` con SQLite. Es suficiente para el laboratorio, porque el DAG ya usa `max_active_runs=1`.
   - Webserver solo en `127.0.0.1:8080`.
   - Variables `DATALAKE_BUCKET`, `GLUE_DATABASE` y `ATHENA_WORKGROUP`.
4. `airflow db migrate` y el usuario `admin`, con la contraseña leída de SSM.
5. Servicios systemd `airflow-webserver` y `airflow-scheduler`, que se reinician solos.

El registro del arranque queda en `/var/log/airflow-bootstrap.log` (unos 2 minutos).

## Qué hacer con Terraform

```bash
cd datalake/infra
./scripts/tf_apply_evidencia.sh 05-ec2-airflow     # Plan: 5 to add, 1 to change
./scripts/wait_bootstrap.sh                         # espera "bootstrap terminado"
```

Para publicar una versión nueva del código, sin recrear la instancia:

```bash
./scripts/tf_apply_evidencia.sh 05-despliegue-codigo aws_s3_object.datalake_code
./scripts/ssm_run.sh /opt/datalake/deploy.sh
```

## Acceso a la interfaz de Airflow (sin abrir puertos)

1. Instalar el [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html).
   En WSL se puede extraer el `.deb` en `~/.local` sin sudo.
2. Abrir el túnel: `./scripts/airflow_tunnel.sh` (puerto local 8081; el 8080 suele estar ocupado por otro
   Airflow local).
3. Leer la contraseña, en tu propia terminal:
   ```bash
   aws ssm get-parameter --name /datalake-noticias/lab/airflow/admin-password --with-decryption \
     --query Parameter.Value --output text
   ```
4. Entrar a <http://localhost:8081> con el usuario `admin`.

Comandos en la instancia sin SSH: `./scripts/ssm_run.sh "<comando>"` (SSM Run Command).

## Qué revisar en la consola de AWS

- **EC2 → Instancias → `datalake-noticias-lab-airflow`:** estado *En ejecución*, `t3.medium`, rol IAM e IMDSv2 *Required*.
- **EC2 → Grupos de seguridad → `datalake-noticias-lab-airflow`:** reglas de entrada vacías.
- **Systems Manager → Fleet Manager:** la instancia aparece *Online*.

## Problemas encontrados

| Problema | Causa | Solución |
|---|---|---|
| El scheduler se reiniciaba con `FileNotFoundError: 'airflow'` | `SequentialExecutor` lanza `airflow tasks run` y systemd no tenía el venv en el `PATH` | `PATH=/opt/airflow/venv/bin:…` en `/etc/sysconfig/airflow`. Se volvió a aplicar con Terraform y la instancia se reemplazó ([evidencia](../../evidencias/05-ec2-airflow-v2/)) |
| `localhost:8080` mostraba otro Airflow | Un Airflow local de otro proyecto (Docker) ya usaba ese puerto | El túnel usa el puerto local 8081 |

## Costo

| Recurso | Precio | Laboratorio de ~10 h |
|---|---|---|
| EC2 `t3.medium` | USD 0,0416/h | ~USD 0,42 |
| EBS gp3 20 GB | USD 0,08/GB-mes | ~USD 0,02 |
| IP pública IPv4 | USD 0,005/h | ~USD 0,05 |
| Parámetro SSM estándar y Session Manager | Gratis | 0 |

**Al terminar:** `terraform destroy -target=aws_instance.airflow` (o apagar la instancia) para no seguir pagando.

## Evidencias

Ver [EVIDENCIAS.md – sección 5](../../evidencias/docEVIDENCIA/EVIDENCIAS.md#5-airflow-en-ec2).
