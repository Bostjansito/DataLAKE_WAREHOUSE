# 08 — Evidencias, demostración y costos

## Evidencia real

Organice evidencia con fecha, región, corrida, comando/SQL y resultado, sin secretos. Incluya:

| Evidencia | Qué demuestra |
|---|---|
| `evidence/local-smoke.json` | Evidencia del orquestador: 11 pruebas locales aprobadas; no hubo llamadas AWS en el smoke |
| `evidence/test-results.xml` | Reporte JUnit de las 11 pruebas |
| `evidence/live-feeds.json` | Corrida HTTPS real, sin AWS ni Comprehend: tres fuentes exitosas, 30 recibidas/nuevas, 0 rechazadas/duplicadas/fechas inválidas; estado `complete` |
| `evidence/access.json` | MCP configurado e initialize/tools-list exitosos; `aws sts get-caller-identity` exitoso y cuenta redactada; cero recursos AWS creados |
| `evidence/deployment-validation.json` | Imagen Docker construida; Compose real con PostgreSQL y Airflow saludables; DAG importado con 10 tareas y escritor único. Servicios temporales eliminados; no equivale a un DAG completo en EC2 |
| Airflow DAG y logs | Pendiente de despliegue AWS autorizado; demostrará dependencias y estado |
| S3 Bronze/Silver/Gold | Los objetos locales están bajo `.local-lake/`; manifiestos y rutas constan en `evidence/local-smoke.json` / `evidence/live-feeds.json`. Capturas S3 reales pendientes |
| Cuarentena | Smoke local incluye un rechazo sintético trazable; no equivale a una respuesta RSS real defectuosa |
| Comprehend | Pendiente: el live RSS reportó `skipped_disabled`; no hay resultados reales de servicio |
| Glue | Pendiente: no hay tablas ni particiones AWS evidenciadas |
| Athena | Pendiente: no hay consultas ni bytes escaneados AWS evidenciados |
| Recuperación | Smoke local valida replay desde Bronze; recuperación/catalogación AWS pendiente |

Las capturas AWS se obtendrán durante ejecución guiada autorizada; actualmente están pendientes. La comprobación de identidad AWS y disponibilidad MCP sí fue realizada en el entorno indicado, pero no es prueba de despliegue ni de ejecución del pipeline.

## Matriz de los ocho escenarios

Los nombres siguientes corresponden a pruebas realmente aprobadas en `evidence/test-results.xml`. Las respuestas NLP de prueba son dobles controlados, nunca resultados de Comprehend.

| Escenario solicitado | Evidencia local ejercitada | Captura AWS después de autorización |
|---|---|---|
| Carga inicial | `test_end_to_end_scenarios`: seis entradas sintéticas, cuatro noticias vigentes, Parquet en seis tablas; ingesta HTTPS adicional de 30 noticias reales | DAG exitoso, Bronze/Silver/Gold y consulta Athena |
| Registros defectuosos | Rechazo `missing_title` trazable y fecha inválida explícita; `test_partial_failed_http_xml_empty_and_network` diferencia 503, XML roto, vacío y red | JSON de cuarentena con motivo y referencia Bronze; manifiesto de fuentes |
| Repetición exitosa | Igualdad del manifiesto, ninguna copia Bronze ni llamada NLP adicional; repetición histórica no rebobina `current` | Dos runs y conciliación Gold sin duplicados |
| Incremental | Una noticia nueva conserva las anteriores y reutiliza cache para las existentes | Conteos nuevos/repetidos y nueva partición visible |
| Contenido modificado | Cambio de título aumenta versión y una llamada NLP; cambiar solo fecha no vuelve a analizar texto | Hash anterior/nuevo y cache de operaciones Comprehend |
| Fallo y reejecución | Fallo tras Silver mantiene el puntero anterior; recuperación completa el mismo lote | Run fallido y recuperado; snapshot vigente y conciliación Athena |
| Reconstrucción Bronze | `test_cli_rebuild_references_bronze_without_new_logical_copy`, más restauración limpia desde Bronze/manifiestos con red prohibida | Parámetro `from_bronze`, mismas claves originales y nueva publicación |
| Nueva partición | Parquet en fechas nuevas; `test_glue_interrupted_switch_converges_and_removes_old_partitions` valida formas SDK y convergencia con doble Glue, no AWS real | Glue partitions actualizadas, consulta Athena por fecha y bytes escaneados |

Las pruebas adicionales verifican caché durable entre operaciones Comprehend, XML con entidades externas, traversal de rutas, manipulación de Bronze, conflicto de escritor, timeout/cancelación Athena y aislamiento de configuración AWS heredada. El smoke fuerza bucket vacío y NLP deshabilitado.


## Guion de demostración

1. Mostrar los tres feeds configurados y aclarar que los XML de `tests/fixtures/initial` son sintéticos, no respuestas de El Tiempo.
2. Ejecutar una carga AWS completa; mostrar el DAG `rss_medallion_lake`, su manifiesto y objetos Bronze/Silver/Gold.
3. Esperar `_control/catalog_status.json` con `status=ready`; consultar indicadores y revisar bytes escaneados en el reporte Athena.
4. Reconstruir en una nueva corrida desde Bronze y comparar claves/conteos:

   ```bash
   rss-lake run --bucket BUCKET --region REGION --enrichment comprehend \
     --run-id rebuild-01 --from-bronze RUN_ORIGINAL
   rss-lake catalog --bucket BUCKET --region REGION \
     --database rss_lake --run-id rebuild-01
   rss-lake athena --bucket BUCKET --region REGION \
     --database rss_lake --workgroup rss-lake --run-id rebuild-01
   ```

   Sustituya valores reales y ejecute en el entorno con la identidad autorizada. `--from-bronze` usa la respuesta almacenada, no vuelve a consultar RSS. Para recuperación de checkpoints del mismo lote, use `--replay`; no confunda recuperación idempotente con reconstrucción.
5. Inyectar un fallo tras `publish_silver` y recuperar el mismo `run_id` sin la bandera de fallo. Vuelva a actualizar catálogo y consultar Athena cuando el estado esté `ready`. Puede usar el parámetro `fail_after`/`batch_id` de Airflow o los comandos CLI de la guía local.
6. Modificar controladamente una copia fixture bajo un ID nuevo: comparar hashes y explicar que Comprehend solo vuelve a analizar texto que cambia.
7. Mostrar una limitación: análisis solo del RSS, sin artículo completo ni resolución de alias.

No afirme éxito hasta que la salida correspondiente esté registrada. La evidencia debe dejar claro qué fue ejecución local, qué fue AWS y qué resultado está pendiente.

## Costos

Antes de desplegar, complete el ejercicio de `../costos.md` con región, duración, almacenamiento, llamadas y bytes consultados. Revise precios y estimador oficial en la fecha de la sesión; no copie tarifas desactualizadas. Detenga/elimine recursos conforme a Terraform al cerrar el laboratorio.
