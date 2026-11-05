# 02 · Fuentes y generadores

[Índice](../guia-operacion.md) · [Evidencias](../../evidencias/docEVIDENCIA/EVIDENCIAS.md)

Con compute activo, habilitar `enable_sources` según [Terraform](01-terraform-s3-red-roles.md), revisar y aplicar el plan. Comprobar RDS MySQL y DocumentDB privados, cifrados y disponibles. Reunir **RDS (4.1) y DocumentDB (5.1) en una sola imagen `04-fuentes/04-fuentes.png`**, con configuración/disponibilidad y conexiones TLS desde EC2 de ambos. Pausar y confirmar cada servicio con ese archivo antes de la fase siguiente o del retiro. Instalar primero el runtime descrito abajo para comprobar conexiones; no exigir datos sembrados todavía. Después de seed guardar tablas/colecciones y conteos como texto, sin imágenes adicionales. El proyecto usa TLS con CA verificada; DocumentDB usa `replicaSet=rs0` y `retryWrites=false`. No asumir compatibilidad total con MongoDB ni desactivar TLS para superar fallos. Las fuentes provisionadas generan costo aunque el DAG no corra.

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
