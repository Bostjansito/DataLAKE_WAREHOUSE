# Fase 8 – Capa Gold

Objetivo: tablas agregadas, listas para responder las preguntas del taller con consultas baratas en Athena.

Código: [`datalake/src/noticias/gold.py`](../../src/noticias/gold.py)

## Tablas y métricas

| Tabla | Grano (una fila por…) | Métrica | Pregunta |
|---|---|---|---|
| `gold_news_daily` | fecha + medio + sección | `news_count` = noticias **distintas** | 1. Noticias por día, medio y sección |
| `gold_entity_daily` | fecha + tipo + entidad normalizada | `news_count` = noticias distintas que la mencionan | 2. Entidades más presentes · 4. Cambio entre fechas |
| `gold_key_phrases_daily` | fecha + sección + frase normalizada | `news_count` = noticias distintas | 3. Frases clave por sección |

Todas se particionan por `published_date` y llevan `gold_run_id` y `built_at` para trazabilidad.

**Decisiones:**

- Se cuentan **noticias distintas** (`news_id`), no filas. Una noticia que aparece en dos feeds o menciona una
  entidad tres veces cuenta una vez.
- La sección de una noticia es la del primer feed donde apareció (`section`). Así la suma por sección es igual
  al total de noticias.
- La entidad se agrupa por su forma normalizada. Se muestra el texto original más frecuente.
- Gold se recalcula solo para las fechas afectadas por la ejecución de Silver. Usa la misma publicación atómica
  (`v=<write_id>` + cambio de partición en Glue), así que recalcular una fecha reemplaza sus filas y no las
  duplica.

## Cómo ejecutar

```bash
datalake/scripts/run_local.sh gold --run-id <run_id de Silver>   # fechas afectadas por esa ejecución
datalake/scripts/run_local.sh gold --date 2026-11-04             # una fecha
datalake/scripts/run_local.sh gold --all                         # todo
datalake/scripts/run_local.sh run                                # extract + silver + gold
```

## Qué revisar en la consola de AWS

1. **S3 → `gold/`:** carpetas `news_daily/`, `entity_daily/`, `key_phrases_daily/`.
2. **Athena:** las consultas de las preguntas 1–3 están en
   [`datalake/sql/01_exploracion.sql`](../../sql/01_exploracion.sql). Las consultas finales, con la
   comparación de bytes escaneados, van en la Fase 10.

## Resultado de la carga

| Tabla | Filas | Fechas |
|---|---|---|
| `gold_news_daily` | 5 (suma = 30 noticias) | 2026-11-04, 2026-11-05 |
| `gold_entity_daily` | 91 | 〃 |
| `gold_key_phrases_daily` | 344 | 〃 |

## Costo

Solo S3 y Glue (las llamadas al catálogo están dentro de la capa gratuita): prácticamente USD 0.

## Evidencias

Ver [EVIDENCIAS.md – sección 8](../../evidencias/docEVIDENCIA/EVIDENCIAS.md#8-capa-gold).
