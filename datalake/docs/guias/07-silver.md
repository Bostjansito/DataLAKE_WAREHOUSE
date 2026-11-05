# Fase 7 – Capa Silver y Amazon Comprehend

Objetivo: convertir el XML de Bronze en datos limpios, validados, sin duplicados y enriquecidos con
entidades y frases clave, en Parquet y particionados por fecha de publicación.

## Qué se construye

| Archivo | Para qué |
|---|---|
| [`parse.py`](../../src/noticias/parse.py) | Interpreta el XML, limpia HTML, valida, normaliza fechas y enlaces, y asigna el identificador |
| [`enrich.py`](../../src/noticias/enrich.py) | Llama a Comprehend en lotes, con caché por hash de texto |
| [`silver.py`](../../src/noticias/silver.py) | Deduplicación, versionado, escritura Parquet, cuarentena y publicación en Glue |
| [`schemas.py`](../../src/noticias/schemas.py) | Esquemas Parquet, iguales a las tablas de Glue |
| [`tests/test_parse.py`](../../tests/test_parse.py) | 8 pruebas sin AWS |

## Tablas

| Tabla | Grano | Ruta |
|---|---|---|
| `silver_news` | 1 fila por noticia (versión vigente) | `silver/news/published_date=…/v=…/` |
| `silver_news_entities` | 1 fila por noticia + entidad + tipo | `silver/news_entities/…` |
| `silver_news_key_phrases` | 1 fila por noticia + frase | `silver/news_key_phrases/…` |
| `quarantine_news` | 1 fila por ítem rechazado, con motivos | `quarantine/news/ingestion_date=…/` (JSON) |

## Decisiones

**Identificador estable.** Se usa la primera estrategia que funcione:

1. `article_id`: el número al final del enlace de El Tiempo (`…-3598523` → `eltiempo-3598523`). No cambia
   aunque editen el título.
2. `guid`: hash del GUID.
3. `link`: hash del enlace normalizado (sin `utm_*`/`fbclid`, sin fragmento ni barra final).
4. `title_date`: hash de título + fecha (último recurso).

**Validación.** Sin título, sin enlace o con enlace no http(s), el ítem va a cuarentena con su motivo y el
lote continúa.

**Fechas.** Se acepta ISO 8601 (formato de los ítems) y RFC 822, y todo se convierte a UTC. Si la fecha falta,
no se puede interpretar o está en el futuro, la noticia se conserva en la partición `published_date=sin_fecha`
y el motivo queda en `date_status`.

**Duplicados.**

- *En el mismo lote:* se queda la primera aparición.
- *Entre feeds:* si la misma noticia sale en dos secciones, es una sola fila y la columna `sections` lista
  todas.
- *Entre lotes:*
  - Mismo `content_hash` → `unchanged`.
  - Contenido distinto y lote más reciente → `version + 1`.
  - Lote más antiguo → se ignora, para no volver a una versión anterior.

**Publicación atómica.**

1. Cada escritura va a una carpeta nueva `v=<write_id>`.
2. Al terminar, la ubicación de la partición se cambia en Glue con `BatchUpdatePartition`.
3. Athena solo ve particiones completas, y un reintento no duplica filas.
4. Se publica primero entidades y frases, y al final noticias.

**Comprehend.**

- Se usan `BatchDetectEntities` y `BatchDetectKeyPhrases`, con 25 documentos por llamada, idioma `es` y
  texto `título. descripción`, recortado a 4.500 bytes.
- Solo se analizan noticias nuevas o modificadas.
- Los resultados se guardan en `control/comprehend_cache/` por SHA-256 del texto.
- Se guardan entidades PERSON, ORGANIZATION y LOCATION.
- Estados posibles: `ok`, `reused`, `empty_text`, `unsupported_language`, `text_too_long`, `error`. Un error de
  Comprehend no borra la noticia.

**Normalización para agrupar.**

- Pasa a minúsculas, quita tildes y quita la puntuación de los bordes.
- La **ñ se conserva**, porque "años" no es "anos". Este error se corrigió y Silver se reconstruyó.

## Cómo ejecutar

```bash
datalake/scripts/run_local.sh silver --run-id 20261105T003325Z   # procesa un lote de Bronze
datalake/scripts/run_local.sh silver --rebuild                   # reconstruye todo desde Bronze, sin RSS
```

Si un lote ya fue procesado, se puede reprocesar. El nuevo registro de control se guarda aparte
(`batch_type=reprocess`) y el original no se modifica.

## Qué revisar en la consola de AWS

1. **S3 → `silver/`:** carpetas `news/`, `news_entities/`, `news_key_phrases/`, y dentro
   `published_date=…/v=…/part-*.parquet`.
2. **Glue → Tablas → `silver_news` → Particiones:** cada fecha apunta a su `v=` vigente.
3. **S3 → `control/comprehend_cache/`:** un JSON por texto analizado.
4. **Athena:** consultas en [`datalake/sql/01_exploracion.sql`](../../sql/01_exploracion.sql).

## Limitaciones de Comprehend observadas

- "Petro" se detectó como `ORGANIZATION`.
- Cargos como "presidente" o "ministro del Interior" se detectaron como `PERSON`.
- Las entidades son inferencias automáticas con una puntuación de confianza, no hechos verificados.
- Además, el análisis usa solo título y resumen del RSS, no el artículo completo.

## Costo

Comprehend cobra USD 0,0001 por unidad de 100 caracteres, con un mínimo de 3 unidades por documento y por API.
Carga inicial: 30 documentos de unos 490 caracteres = 5 unidades × 30 × 2 API (entidades y frases) = 300 unidades,
unos **USD 0,03**. La reconstrucción desde Bronze costó USD 0, porque todo salió de la caché.

## Evidencias

Ver [EVIDENCIAS.md – sección 7](../../evidencias/docEVIDENCIA/EVIDENCIAS.md#7-capa-silver-y-amazon-comprehend).
