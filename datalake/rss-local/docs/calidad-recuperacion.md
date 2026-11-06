# Calidad, incrementalidad y recuperación

## Identidad y cambios

La clave canónica es `SHA-256(medio + NUL + enlace_canónico)`. El enlace acepta HTTP(S), normaliza esquema/host, elimina puerto estándar, fragmento y parámetros `utm_*`, `fbclid`, `gclid`, ordena los demás parámetros y quita barra final salvo raíz. GUID se conserva como campo, pero no se usa en la identidad; un enlace modificado genera una identidad nueva. La misma URL del mismo medio en feeds distintos comparte clave. Se elige sección/fuente lexicográficamente menor por `(section, source)` y, para repeticiones de esa fuente, fecha publicada más reciente y luego hash de contenido mayor. Esta regla es determinista, pero puede descartar la procedencia de otros feeds. No resuelve alias ni dos URL diferentes del mismo artículo.

El hash de contenido se calcula sobre título, descripción, enlace, fecha publicada y idioma; el hash de texto identifica título y descripción enviados a Comprehend. Un cambio en otro campo puede incrementar versión sin repetir enriquecimiento si el texto no cambió. Un lote exitoso repetido no debe incrementar el conjunto vigente ni el conteo Gold. La salida conserva un registro vigente por `news_id`; snapshots por ejecución no se suman entre sí.

## Reglas de calidad y trazabilidad

- Campos obligatorios y URL válida se comprueban antes de publicar; faltantes, enlace inválido o XML ilegible se aíslan en cuarentena con motivo y referencia al lote/objeto Bronze.
- Fechas interpretables se normalizan a UTC y se guarda su valor de origen. Fecha ausente/malformada se marca y se asigna partición `1970-01-01`, no una fecha inventada.
- Campos de RSS se limpian de HTML, manteniendo texto legible; el contenido bruto Bronze permanece intacto.
- News vigente debe ser único por `news_id`; relaciones de entidades/frases deben apuntar a noticia existente.
- Entidades/frases se deduplican por noticia y valor/type apropiados. Presencia en agregados cuenta `news_id` distintos.
- Se registran por lote `received`, `new`, `updated`, `repeated`, `duplicates_in_batch`, `rejected` y `unknown_date`. La validación concilia `received = new + updated + repeated + duplicates_in_batch + rejected`; no hay un conteo `valid` separado: los registros aceptados se expresan con las cuatro categorías previas a `rejected`. El resto de diferencias se explica por duplicados dentro/entre feeds, inválidos o versiones ya conocidas, no por pérdida silenciosa.

## Incrementalidad

La extracción crea una nueva corrida y conserva cada respuesta RSS válida en Bronze. Una repetición con el mismo `run_id`/`--replay` reutiliza manifiesto y checkpoints y no consulta la red; esto recupera etapas pendientes, pero no vuelve a calcular etapas ya checkpointed. Para reconstruir desde las respuestas Bronze con un ID nuevo, ejecute `rss-lake run --root ROOT --run-id DESTINO --from-bronze ORIGEN` (o use `--bucket BUCKET --region REGION` para el mismo lake S3). El comando referencia los objetos Bronze existentes sin copiarlos, fija el padre vigente y transforma de nuevo; exige mismo store y nuevo `run_id`. En un store vacío, restaure los objetos XML Bronze en sus claves originales y `_control/runs/ORIGEN/start.json` y `ingest.json` antes de invocarlo. No altere contenido existente: un XML controlado modificado requiere una nueva extracción fixture bajo `run_id` nuevo. Las noticias sin cambios reutilizan enriquecimiento mediante caché identificada por región/servicio, idioma y texto; Comprehend solo se llama con idioma soportado (`es`/`en`), texto no vacío y hasta 5000 bytes UTF-8. Otros casos quedan `skipped_disabled`, `skipped_empty`, `skipped_language` o `skipped_too_long`, según corresponda.

## Publicación y recuperación

Cada corrida construye Silver y Gold en `silver|gold/snapshots/<run_id>/<tabla>/publication_date=.../` con Parquet comprimido Snappy y checksums. `validate` comprueba checksums, conteos, unicidad, relaciones, fechas y conciliación; luego persiste el manifiesto y publica `_control/current.json` en una escritura atómica. Una falla antes de ese commit deja vigente el manifiesto anterior; una repetición del lote ya publicado no retrocede el puntero. Serialice corridas escritoras: si cambia el padre durante el procesamiento, la validación falla y no publica ese snapshot. Los objetos no publicados pueden ocupar almacenamiento y se deben revisar antes de eliminarlos.

Glue se actualiza por la etapa `catalog` después de publicar el manifiesto; registra ubicaciones y particiones de runtime en operaciones secuenciales, sin transacción de seis tablas. El módulo escribe `_control/catalog_status.json` como `updating` y solo tras completar la reconciliación como `ready`. No consulte Athena mientras esté `updating`; si falla, vuelva a ejecutar `rss-lake catalog` con el mismo lote: la operación idempotente converge. Después de `ready`, ejecute `rss-lake athena` y la conciliación. Una carpeta S3 por sí sola no es una partición Glue.

## Matriz de validación y evidencia

| Caso | Evidencia que debe capturarse | Resultado esperado |
|---|---|---|
| Carga inicial | run DAG/CLI, manifiesto Bronze, archivos por capa, catálogo y consulta | Filas navegables en cada etapa |
| Registro defectuoso | fila de cuarentena y referencia Bronze | Motivo explícito, sin fila válida publicada |
| Repetición de lote | comparación de claves y agregados antes/después | Sin duplicados ni incremento artificial |
| Lote incremental | conteos de lote y claves nuevas | Solo se agregan/cambian las noticias afectadas |
| Noticia modificada | hash previo/nuevo y estado Comprehend | Nueva versión vigente; llamada solo ante nuevo texto |
| Fallo y reejecución | estado parcial/fallido y referencia de snapshot | Recuperación sin perder publicación previa ni duplicar |
| Reproceso Bronze | parámetros de corrida y logs sin extracción RSS | Reproduce sin red al origen |
| Nueva partición | partición Glue y consulta Athena | Partición visible tras registrar metadatos |

Las cifras y capturas solo se completan tras ejecutar los casos; no presentar el resultado esperado como resultado observado.
