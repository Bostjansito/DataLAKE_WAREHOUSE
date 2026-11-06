# Diccionario de datos

Las tablas Silver y Gold usan Parquet y `publication_date` como partición de fecha. Los tipos concretos son los definidos por `lake/schemas.py` y por las definiciones Glue: esa fuente de esquema gobierna frente a esta descripción semántica. No se deben inferir columnas adicionales de esta guía. `publication_date=1970-01-01` indica fecha de publicación inválida/ausente; se conserva el texto original de la fecha para distinguirlo de una fecha real.

## Silver

| Tabla | Granularidad | Columnas |
|---|---|---|
| `news` | Una fila por `news_id` vigente | `news_id` string: identidad; `title` string: título limpio; `description` string: descripción limpia RSS; `link` string: enlace canónico; `medium` string: medio; `section` string: sección principal; `source` string: fuente RSS elegida; `published_at` timestamp UTC nullable: fecha válida; `publication_date` string: partición `YYYY-MM-DD`, excluida del archivo Parquet; `original_date` string: texto de fecha RSS; `date_status` string: `valid`, `missing`, `missing_timezone` o `invalid`; `guid` string: identificador original, no clave; `first_seen_at` timestamp UTC; `last_seen_at` timestamp UTC; `version` int64; `content_hash` string: SHA-256 de título, descripción, enlace, fecha UTC y original, e idioma; `text_hash` string: SHA-256 de título + salto de línea + descripción; `bronze_key` string; `run_id` string; `enrichment_status` string; `analyzed_text` string; `language` string; `analyzed_at` timestamp UTC nullable. |
| `news_entities` | Una fila por noticia y mención distinta (texto y tipo) | `news_id` string, `entity` string, `entity_type` string (`PERSON`, `ORGANIZATION`, `LOCATION`), `score` double, `section` string, `medium` string, `publication_date` string de partición, excluida de Parquet. |
| `news_key_phrases` | Una fila por noticia y frase distinta | `news_id` string, `phrase` string, `score` double, `section` string, `medium` string, `publication_date` string de partición, excluida de Parquet. |

El esquema Arrow tipado autoritativo está en `lake/schemas.py`; Glue declara columnas de archivo y agrega `publication_date` como partition key, por lo que la fecha no forma parte del Parquet físico.

## Gold

| Tabla | Granularidad | Columnas |
|---|---|---|
| `daily_news` | Día `publication_date`, medio y sección | `medium` string, `section` string, `news_count` int64, `publication_date` string de partición (no se almacena en Parquet). |
| `entity_daily` | Día, entidad y tipo | `entity` string, `entity_type` string, `news_count` int64, `publication_date` string de partición (no se almacena en Parquet). |
| `section_phrases` | Día, sección y frase | `section` string, `phrase` string, `news_count` int64, `publication_date` string de partición (no se almacena en Parquet). |

`news_count` cuenta noticias distintas. En `entity_daily`, la presencia no cuenta menciones repetidas dentro de una noticia; las tablas tampoco consolidan alias como «IBM» y «International Business Machines».

## Campos transversales

- **`news_id`:** SHA-256 del medio y enlace canónico. GUID RSS se conserva pero no forma parte de la clave; ver [calidad y recuperación](calidad-recuperacion.md).
- **Fecha de publicación:** fecha normalizada a UTC si tiene zona válida; se conserva el valor original. Ausente, sin zona o inválida usa `published_at = null`, estado explícito y partición centinela `1970-01-01`.
- **Confianza:** puntuación devuelta por Comprehend para la mención, entre 0 y 1 según validación; no equivale a certeza.
- **Primera/última observación y versión:** `first_seen_at` conserva la primera ingesta de la identidad; `last_seen_at` corresponde a la corrida más reciente que la observó. `version` comienza en 1 y aumenta cuando cambia `content_hash`.
- **Enriquecimiento:** `analyzed_text` es título, salto de línea y descripción RSS; `language` proviene del feed; `enrichment_status` es `completed` o un estado de omisión explícito. `analyzed_at` es la hora del análisis y puede ser nula cuando no se analiza.
- **Partición:** valor de cadena `YYYY-MM-DD`, presente en ubicación S3/Glue como partición y ausente del archivo Parquet físico.

## Conteos

`news_count` siempre pretende contar `news_id` distintos. Una conciliación de Gold con Silver debe aplicar el mismo filtro de snapshot vigente, fecha (incluyendo la partición centinela) y dimensiones; no comparar el total bruto de archivos de snapshots históricos.
