# 02 · Fuentes y generadores

[Índice](../guia-operacion.md) · [Evidencias](../../evidencias/docEVIDENCIA/EVIDENCIAS.md)

La fase requiere reconstruir compute si ya fue retirado. El operador debe comprobar identidad cuenta `241732001318`, región `us-east-1`, y generar un plan nuevo desde el directorio Terraform con flags explícitos:

```bash
cd datawarehouse/infra/terraform
umask 077
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
aws sts get-caller-identity
TF="/home/emanuel/Universidad/Sexto/Ingenieria de Datos/TallerAWS/.tools/terraform"
"$TF" plan -var='aws_region=us-east-1' -var='aws_account_id=241732001318' -var='enable_compute=true' -var='enable_sources=true' -var='enable_docdb=true' -var='enable_warehouse=false' -out=fuentes-nuevo.tfplan
chmod 600 fuentes-nuevo.tfplan
"$TF" show -no-color fuentes-nuevo.tfplan
```

El `fuentes.tfplan` anterior se generó con `sources=false`: **no aplicarlo**. Revisar altas, cambios, eliminaciones y reemplazos, en particular EC2, antes de que el operador decida aplicar únicamente el nuevo plan revisado y autorizado. Los agentes no ejecutan apply ni push. Estos comandos son instrucciones, no evidencia de ejecución.

Solo el operador autorizado, después de revisar el plan vigente y confirmar cuenta, región y gasto, puede aplicarlo desde ese mismo directorio:

```bash
"/home/emanuel/Universidad/Sexto/Ingenieria de Datos/TallerAWS/.tools/terraform" apply fuentes-nuevo.tfplan
```

El plan es sensible y puede quedar obsoleto si cambia el estado o la configuración: en ese caso generar y revisar otro, sin reutilizarlo.

Reunir **RDS (4.1) y DocumentDB (5.1) en una sola imagen `04-fuentes/04-fuentes.png`**: estado, configuración privada/cifrada y conexiones TLS desde EC2 para ambos motores. Mostrar solo campos necesarios y resultados reales, sin credenciales; si no caben legibles, dividir y documentar el motivo. Confirmar cada servicio antes del retiro. Instalar primero el runtime de [EC2](05-ec2-airflow.md); no exigir seed para la captura. DocumentDB utiliza CA verificada, `replicaSet=rs0` y `retryWrites=false`; no asumir compatibilidad completa con MongoDB. Las fuentes provisionadas generan costo aunque el DAG no corra.

Las credenciales maestras de RDS y DocumentDB son gestionadas por AWS (`manage_master_user_password=true`); los outputs proporcionan sus ARN, no el contenido. Cada secreto nativo contiene `username` y `password`, no host, puerto, base ni URI. `runtime.json` proporciona por separado `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MONGO_HOST`, `MONGO_PORT`, `MONGO_DATABASE` y los correspondientes `MYSQL_SECRET_ARN` y `MONGO_SECRET_ARN`; el runtime recupera credenciales y construye las URI con escape seguro. No imprimir secretos, URI con credenciales, estado ni planes.

Para comprobar las dos fuentes sin seed ni Redshift, ejecutar **en EC2, después del despliegue del runtime**, y capturar únicamente el resultado sin credenciales. Este comando no se ha ejecutado durante la validación local:

```bash
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python - <<'PY'
from aws_dw.extraction.extractor import get_mysql_connection, get_mongo_client
mysql = get_mysql_connection(streaming=False)
with mysql.cursor() as cursor:
    cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
    cipher = cursor.fetchone()[1]
    assert cipher, "MySQL session must use TLS"
mongo = get_mongo_client()
assert mongo.admin.command("ping")["ok"] == 1
print("MySQL TLS:", cipher, "| DocumentDB verified TLS: ping OK")
mysql.close()
mongo.close()
PY
```

Tras instalar el runtime de [EC2](05-ec2-airflow.md), abrir una sesión SSM. Los siguientes comandos se ejecutan **en EC2**, con el wrapper que obtiene las credenciales de los secretos sin imprimirlas. `seed` es para fuentes nuevas, no para recuperación; crea el esquema y los datos iniciales, incluidos defectuosos de prueba:

```bash
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli setup
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli seed --customer-count 50 --product-count 25 --order-count 100 --review-count 150 --event-count 500 --seed 42 --bad-records 2
```

`setup` requiere también S3 y Redshift disponibles; si aún no se habilitó warehouse, ejecutar la comprobación después de activarlo. Capturar el lote inicial como `0` solo después de seed. Para cada lote nuevo N entre 1 y 365, después del éxito del lote 0 y antes de capturar N:

```bash
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli append --batch-id 1
```

El generador usa IDs estables y produce tres pedidos/líneas, reseñas y eventos por lote. Para demostrar SCD2, inspeccionar primero los valores actuales de cliente y producto y escoger valores realmente distintos; aplicar el cambio **antes de la captura del siguiente lote**, por ejemplo:

```bash
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli simulate-changes --customer-id 1 --product-id 1 --city Medellín --department Antioquia --category Hogar --changed-at 2025-07-01T00:00:00
```

Escoger una fecha posterior al `updated_at` previo; no repetir el mismo lote ya capturado esperando nuevos valores. Después de append y cambios ejecutar `pipeline --batch-id 1` o el DAG con ese lote. Consultar [escenarios](06-escenarios-recuperacion.md). Ver conteos por fuente en [SQL](../../sql/01_source_counts.sql); no exponer credenciales ni datos personales en capturas. Retirar solo recursos propios ya innecesarios tras confirmación, conservando dependencias y registrando costo; delegar publicación de fase a free-worker.
