# 04 · Redshift, COPY y dbt

[Índice](../guia-operacion.md) · [Evidencias](../../evidencias/docEVIDENCIA/EVIDENCIAS.md)

Habilitar `enable_warehouse` con compute y fuentes activos; revisar el plan y aplicar como en [01](01-terraform-s3-red-roles.md). En consola identificar namespace, workgroup privado y rol COPY asociado, autorizado al bucket. El cargador verifica manifiestos, columnas y payloads, hace COPY CSV a tablas temporales y reemplaza por clave en seis tablas raw; carga y registro `pending` se confirman juntos. No asumir que Redshift está operativo antes de comprobarlo.

El runtime obtiene `username` y `password` del secreto nativo gestionado por AWS, identificado por `REDSHIFT_SECRET_ARN`; `REDSHIFT_HOST`, `REDSHIFT_PORT` y `REDSHIFT_DATABASE` se configuran por separado en `runtime.json`. No esperar host, puerto ni base dentro del secreto, ni imprimir sus valores o credenciales.

El pipeline ejecuta `dbt deps`, `seed`, `run --select intermediate quarantine`, `snapshot`, `run --select marts` y `test`; solo después marca `succeeded`. `intermediate` valida, `quarantine` conserva rechazos y motivo, `marts` construye dimensiones y hechos; snapshots conservan historia SCD2. dbt corre en EC2 y envía SQL a Redshift. Los tests cubren unicidad, obligatoriedad, relaciones y reglas de negocio; capturar sus resultados efectivos, no solo el código.

En un cliente SQL conectado a Redshift ejecutar las consultas completas de [conciliación](../../sql/02_business_reconciliation.sql). La primera compara por fecha unidades e importe de `intermediate.int_mysql__order_items__valid` unido a pedidos válidos contra `marts.fct_sales` unido a `marts.dim_date`; debe devolver cero diferencias. La segunda identifica claves con distinto de una versión SCD2 vigente y también debe devolver cero filas. La tercera muestra registros rechazados con motivo y lote. Guardar SQL y resultados reales. [Conteos](../../sql/01_source_counts.sql) distingue consultas MySQL, DocumentDB y Redshift; no interpretar los conteos raw como historial acumulativo de dimensiones, ya que se reemplazan por clave.

```sql
select batch_id, status, rows_loaded, loaded_at, completed_at
from raw.batch_ledger order by loaded_at;
```

Usar **una imagen 6.1** para configuración/disponibilidad Redshift y confirmar el servicio antes de continuar. Guardar COPY/ledger, capas y resultados completos de dbt como texto; reunir el resumen real dbt con la UI exitosa de Airflow en **una imagen 7.1**, sin imágenes separadas por capa o herramienta. Pausar y confirmar cada evidencia, aunque compartan archivo. Tras ella retirar solo recursos propios innecesarios sin romper dependencias y delegar publicación de fase a free-worker. Almacenamiento y snapshots pueden seguir facturándose; ver [retiro](07-retiro-dependencias.md).
