# 05 · EC2, Airflow, SSM y DAG

[Índice](../guia-operacion.md) · [Evidencias](../../evidencias/docEVIDENCIA/EVIDENCIAS.md) · [Procedimiento completo de infraestructura](../../infra/README.md)

Habilitar compute y, para el pipeline completo, fuentes y warehouse. Revisar el plan de cada fase. Reunir EC2, perfil, IMDSv2, disco cifrado y grupo sin entrada (comprobación 3.1) **en la misma imagen `02-runtime/03-runtime.png` de VPC/IAM (2.1)**, sin otra imagen EC2; pausar y confirmar cada servicio con ese archivo antes de la siguiente fase o del retiro. Tras disponibilidad de SSM, desde la raíz del repositorio:

```bash
bash datawarehouse/infra/scripts/upload-bundle.sh
terraform -chdir=datawarehouse/infra/terraform output -raw ec2_instance_id
# Asignar INSTANCE_ID al output y BUNDLE_URI a la URI exacta impresa por upload.
bash datawarehouse/infra/scripts/remote-deploy.sh "$INSTANCE_ID" "$BUNDLE_URI"
# Asignar COMMAND_ID a la salida anterior.
aws ssm get-command-invocation --instance-id "$INSTANCE_ID" --command-id "$COMMAND_ID" --region "$AWS_REGION"
```

El despliegue instala aplicación, Airflow y dbt en EC2; detener una actualización durante una carga activa no es seguro. El webserver escucha solo en `127.0.0.1:8080`. Abrir desde la estación local con Session Manager plugin:

```bash
aws ssm start-session --target "$INSTANCE_ID" --region "$AWS_REGION" --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["8080"],"localPortNumber":["8080"]}'
```

Mantener el túnel y abrir http://127.0.0.1:8080. Seguir el procedimiento de clave pública efímera de [infra/README](../../infra/README.md#airflow-ui-y-captura-del-dag) para obtener localmente la contraseña del administrador sin texto claro en logs SSM. No mostrarla, grabarla ni abrir el puerto en el security group. No pedir una imagen del DAG vacío: la UI del DAG y su ejecución exitosa se reúnen con el resumen real dbt en **una imagen 7.1**, al completar el lote inicial; entonces confirmar Airflow y dbt sin duplicar imagen.

Para ejecutar desde la UI: seleccionar `ecommerce_dw_pipeline`, Trigger DAG, introducir JSON y confirmar. Primero poblar fuentes con seed; para cada N ejecutar append y, si aplica, cambios antes de capturar. Configuraciones válidas:

```json
{"batch_id": 0}
```

```json
{"batch_id": 1}
```

```json
{"batch_id": 1, "replay": true}
```

Para fallo controlado en un lote nuevo ya preparado: `{"batch_id": 2, "fail_after_load": true}`; recuperar con `{"batch_id": 2, "replay": true}` sin el flag de fallo. Los flags son booleanos JSON, no cadenas. El DAG valida lote 0..365 y ejecuta el CLI en `capture_copy_dbt_quality_ledger`; hay dos reintentos automáticos acotados, por lo que debe esperarse el fallo final antes de lanzar recuperación. Guardar logs por lote/tarea y ledger como texto y **confirmar el fallo antes de recuperar**; después confirmar los resultados de recuperación. No exigir imágenes nuevas de Grid/logs para cada escenario.

Alternativamente, desde sesión SSM interactiva:

```bash
aws ssm start-session --target "$INSTANCE_ID" --region "$AWS_REGION"
# En EC2:
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/airflow-venv/bin/airflow dags trigger ecommerce_dw_pipeline --conf '{"batch_id":0}'
sudo journalctl -u ecommerce-airflow.service --since today
```

El primer comando se ejecuta localmente y los siguientes en EC2. No repetir seed como recuperación. Después de cada captura confirmada retirar solo recursos propios innecesarios, mantener dependencias para fases siguientes y delegar publicación a free-worker.
