# Fase 10 – Consultas entregables, comparación de escaneo, costos y eliminación

## Consultas

Archivo: [`datalake/sql/02_entregables.sql`](../../sql/02_entregables.sql). Se ejecutan en el
editor de Athena con el workgroup `datalake-noticias-lab-wg` y la base `datalake_noticias_lab`.

| # | Requisito (4.4) | Tabla | Idea clave |
|---|---|---|---|
| 10.1 | Noticias por fecha y sección | `silver_news` | Detalle de la versión vigente, filtrado por `published_date` |
| 10.2 | Top 10 organizaciones | `gold_entity_daily` | `sum(news_count)`: noticias **distintas**, no menciones |
| 10.3 | Presencia de una entidad entre días | `gold_entity_daily` + `gold_news_daily` | Porcentaje del día y variación con `lag()` |
| 10.4 | Frases clave por sección | `gold_key_phrases_daily` | `row_number()` por sección |
| 10.5 | Conciliación Gold vs Silver | ambas | `FULL OUTER JOIN`; la diferencia debe ser 0 |
| 10.6 / 10.7 | Bytes con y sin filtro de partición | `silver_news_key_phrases` + `silver_news` | La misma consulta con y sin `published_date = …` |

Para ver los bytes escaneados de cada consulta: panel de resultados → **Datos analizados**, o pestaña
*Estado de la consulta*. También en *Consultas recientes*.

Resultado: **0,54 KB con filtro y 1,51 KB sin filtro** (~2,8×). Con más días, la diferencia crece de forma
lineal. Athena cobra USD 5/TB con un mínimo de 10 MB por consulta, así que con este volumen cada consulta
cuesta ~USD 0,00005. Lo que importa es el patrón: sin filtro, el costo escala con todo el historial.

## Costos

Ver la estimación completa en [README – sección 7](../../README.md#7-estimación-de-costos-us-east-1). El costo
real se puede revisar en **Billing → Cost Explorer**, filtrando por la etiqueta `Project = datalake-noticias`.
Las etiquetas salen de `default_tags` de Terraform y deben activarse como *cost allocation tags* (tardan hasta
24 h en aparecer).

## Eliminación

| Opción | Comando | Qué queda |
|---|---|---|
| Solo el cómputo | `terraform destroy -target=aws_instance.airflow` | Bucket, Glue, Athena, IAM y el código en S3. Costo ~USD 0 en reposo |
| Todo | `terraform destroy` | Nada: `force_destroy=true` vacía y borra el bucket |

Después de `terraform destroy`, verificar:

1. **EC2:** la instancia queda *Terminada*.
2. **S3:** el bucket ya no aparece.
3. **Glue:** la base `datalake_noticias_lab` no existe.
4. **Athena:** el workgroup no existe.
5. **Terminal:** `terraform state list` queda vacío.

## Evidencias

Ver [EVIDENCIAS.md – secciones 10 y 12](../../evidencias/docEVIDENCIA/EVIDENCIAS.md#10-consultas-en-athena).
