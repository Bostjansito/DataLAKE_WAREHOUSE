# Fase 9 – DAG de Airflow y escenarios de calidad, incrementalidad y recuperación

DAG: [`datalake/dags/noticias_datalake.py`](../../dags/noticias_datalake.py)

## Tareas y dependencias

```text
validar_configuracion ─► fuentes ─► extraer_fuente[x3] ─► resumen_extraccion ─► limpiar_validar_deduplicar
   ─► enriquecer_comprehend ─► publicar_silver ─► construir_gold ─► actualizar_glue ─► validar_athena
                                                                                          └─► registrar_estado (siempre)
```

| # | Requisito (4.6) | Tarea | Qué hace |
|---|---|---|---|
| 1 | Validación de configuración y acceso | `validar_configuracion` | Lee `sources.json`, verifica la identidad (STS), el bucket, la base y las tablas de Glue y el workgroup de Athena. Valida los parámetros |
| 2 | Extracción y Bronze | `extraer_fuente` (mapeada, una por fuente) + `resumen_extraccion` | Un fallo de red o HTTP se reintenta. Si se agotan los reintentos, la fuente queda *failed* y la ejecución pasa a **partial**. Si fallan todas, **failed** |
| 3 | Limpieza, validación y deduplicación | `limpiar_validar_deduplicar` | Rechazados a cuarentena. Dedup en el lote, entre feeds y entre lotes. Deja el estado en `tmp/jobs/<run>/prepared.json` |
| 4 | Enriquecimiento con Comprehend | `enriquecer_comprehend` | Solo noticias nuevas o con **texto analizado** distinto. Caché por hash |
| 5 | Publicación de Silver | `publicar_silver` | Parquet en `v=<write_id>` y cambio de partición en Glue. Registro de conteos por lote |
| 6 | Construcción de Gold | `construir_gold` | Agregados de las fechas afectadas, escritos sin publicar |
| 7 | Actualización de Glue | `actualizar_glue` | Publica las particiones de Gold y verifica que las fechas afectadas existan en las 6 tablas |
| 8 | Validaciones finales con Athena | `validar_athena` | Una consulta con las 8 reglas ([`validate.py`](../../src/noticias/validate.py)). Falla si alguna es distinta de 0 |
| 9 | Registro del estado | `registrar_estado` | `trigger_rule=all_done`: escribe `control/runs/run_id=<lote>/dag.json` con el estado de cada tarea y **complete / partial / failed** |

| Requisito del DAG | Implementación |
|---|---|
| Ejecución programada | `schedule="0 * * * *"` (cada hora), `catchup=False` |
| Dependencias explícitas | Flujo de datos TaskFlow, más `[cfg, resumen, validar_athena] >> registrar_estado` |
| Reintentos acotados | `retries=2`, espera de 30 s exponencial (máx. 5 min), `execution_timeout=20 min` |
| Logs con fuente, lote y tarea | Formato `source=… run_id=… task=…` en todos los módulos |
| Control de concurrencia | `max_active_runs=1` y `SequentialExecutor`: nunca dos escrituras simultáneas sobre Silver/Gold |
| Reprocesar un lote desde Bronze | Parámetros `bronze_run_id` (un lote) o `rebuild` (todo Bronze), sin consultar los RSS |

**Identificador del lote.** En las ejecuciones programadas es el fin del intervalo (`data_interval_end`); en las
manuales, el momento del disparo. Es estable entre reintentos (un reintento reutiliza el lote ya guardado
en Bronze) y sigue el orden real de las extracciones.

> **Error encontrado y corregido.** La primera versión usaba `logical_date`, que en las ejecuciones
> programadas es el *inicio* del intervalo (una hora antes). La segunda usaba `data_interval_end` también en
> las manuales, y dos disparos manuales de la misma hora compartieron `20261105T010000Z`. Los datos no se
> afectaron, porque las ejecuciones son secuenciales y el lote de Bronze era único, pero el resumen de
> `control/runs/` de la primera se sobrescribió.

## Cómo disparar el DAG

- **Desde la interfaz:** *Trigger DAG w/ config* con el JSON de parámetros.
- **Desde la terminal, por SSM:**
  ```bash
  datalake/infra/scripts/dag_trigger.sh '{"bronze_run_id": "20261105T020000Z"}'
  ```
- **Escenario completo con evidencia:**
  ```bash
  datalake/scripts/escenario.sh <nombre> '<json>'
  ```
  Guarda los estados de las tareas y los resúmenes de `control/runs/` en `datalake/evidencias/09-escenarios/`.

## Escenarios

Copias controladas de Bronze: `datalake/scripts/run_local.sh controlled-copy --from-run <lote> --source <fuente> --mode modificado|defectuosos`
([`scenarios.py`](../../src/noticias/scenarios.py)). Crean un lote **nuevo** en Bronze con
`batch_type=controlled_copy` y la ruta del original en `origin_bronze_key`. Bronze nunca se sobrescribe.

Los resultados de cada escenario están en [EVIDENCIAS.md – sección 11](../../evidencias/docEVIDENCIA/EVIDENCIAS.md#11-escenarios-de-calidad-incrementalidad-y-recuperación).

## Recibidos vs. noticias únicas

Un lote recibe 10 ítems por feed, pero el número de noticias únicas publicadas es menor por estas razones:

- **Rechazados:** ítems sin título o con un enlace inválido van a cuarentena.
- **Repetidos dentro del lote:** la misma noticia dos veces en un feed.
- **Repetidos entre feeds:** la misma noticia en dos secciones es una fila, con `sections` lista.
- **Repetidos entre lotes:** cada hora se repite la mayoría de los ítems. Si el contenido no cambió, se
  marcan como `unchanged` y no se reescriben ni se vuelven a enviar a Comprehend.
