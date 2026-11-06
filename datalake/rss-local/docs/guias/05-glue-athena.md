# 05 — AWS Glue Data Catalog y Athena

## Objetivo

Registrar las seis tablas Silver/Gold y consultar Parquet en S3, con comparación de costo de escaneo particionado.

## Registro y consulta

1. Revise en Terraform las definiciones iniciales de base Glue y tablas; columnas/tipos deben corresponder a `lake/schemas.py` y `sql/`.

Los ejemplos de `rss-lake` sirven desde una instalación local autenticada con perfil AWS. En EC2, el CLI vive dentro de `scheduler`; desde `/opt/lake` prefije cada comando con `docker compose --env-file .env -f docker-compose.yml exec scheduler`. El comando `aws s3 cp` de lectura de estado puede ejecutarse en el host EC2.

2. Después de `rss-lake run`, registre las ubicaciones y particiones del manifiesto vigente:

   ```bash
   rss-lake catalog --bucket BUCKET --region REGION \
     --database rss_lake --run-id RUN_ID
   aws s3 cp "s3://BUCKET/_control/catalog_status.json" - \
     --region REGION
   ```

   Cambie los valores de ejemplo. El estado debe mostrar `ready` para ese `run_id`. Glue no tiene transacción multitabla: mientras está `updating`, no consulte Athena. Si la actualización se interrumpe, vuelva a ejecutar `rss-lake catalog` con el mismo lote; la reconciliación es idempotente y converge.
3. En Glue verifique las seis tablas: ubicación del snapshot vigente, formato Parquet, esquema y partition key `publication_date`. El runtime registra particiones explícitamente; escribir un prefijo no basta.
4. Capture base, tabla, ubicación, columnas y al menos una partición. Compare la ubicación de catálogo con `_control/current.json`, no con una ruta de snapshot antigua.
5. Una vez `ready`, ejecute los controles integrales Athena:

   ```bash
   rss-lake athena --bucket BUCKET --region REGION \
     --database rss_lake --workgroup rss-lake --run-id RUN_ID
   ```

   Este comando consulta conteos, claves/huérfanos, conciliación y bytes escaneados; puede generar cargos. El manifiesto de resultados se guarda en `_control/runs/<run_id>/athena.json`. Después, abra Athena con el workgroup del proyecto y ejecute las consultas SQL versionadas en `sql/`: `01` por fecha/sección, `02` top diez organizaciones, `03` evolución diaria, `04` frases por sección, `05` conciliación Silver/Gold y `08` integridad/huérfanos. Reemplace fechas de ejemplo por días poblados en el snapshot vigente.

6. Para comparar escaneo use `sql/06_bytes_sin_filtro.sql` y `sql/07_bytes_con_filtro.sql` en el mismo snapshot, workgroup y motor. Sustituya la fecha fija por una partición poblada; deben existir al menos dos fechas para que el filtro pueda podar datos. Desactive reutilización de resultados en ambas consultas, anote los `QueryExecutionId` y obtenga `QueryExecution.Statistics.DataScannedInBytes` para cada una (consola o `aws athena get-query-execution`). Los resultados cubren rangos distintos: compare bytes, no conteos. No se garantiza ahorro si el dataset es pequeño o una sola partición está poblada; cada consulta puede facturar.

## Seguridad y costo

El workgroup aplica un corte de bytes por consulta cuyo valor predeterminado es 10 MiB (`athena_scan_limit_bytes=10485760`); confirme la configuración real antes de usarlo. No es un tope mensual ni impide cargos de otros servicios. Resultados Athena también ocupan S3. Evite `SELECT *` sin filtros y limpie resultados según política autorizada.

## Evidencia

Capturas requeridas: tablas/particiones Glue, SQL ejecutado y resultados Athena, bytes escaneados con filtro frente a sin filtro. No hay ejecución ni capturas AWS generadas por esta guía; complete evidencia en una sesión autorizada.
