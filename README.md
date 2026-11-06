# Arquitecturas de datos: Data Lake y Data Warehouse

> 📄 **Evidencias del Data Lake:** [`datalake/evidencias/docEVIDENCIA/EVIDENCIAS.md`](datalake/evidencias/docEVIDENCIA/EVIDENCIAS.md) ([ver en GitHub](https://github.com/Bostjansito/DataLAKE_WAREHOUSE/blob/main/datalake/evidencias/docEVIDENCIA/EVIDENCIAS.md))
>
> 📄 **Evidencias del Data Warehouse:** [`datawarehouse/evidencias/docEVIDENCIA/EVIDENCIAS.md`](datawarehouse/evidencias/docEVIDENCIA/EVIDENCIAS.md) ([ver en GitHub](https://github.com/Bostjansito/DataLAKE_WAREHOUSE/blob/main/datawarehouse/evidencias/docEVIDENCIA/EVIDENCIAS.md))

| Parte | Carpeta | Contenido |
|---|---|---|
| Data Lake de noticias RSS | [`datalake/`](datalake/) | Arquitectura, código, Terraform, DAG de Airflow, guías y evidencias |
| Data Warehouse | [`datawarehouse/`](datawarehouse/) | Migración de DE-DW a AWS: código, Terraform, modelos dbt, DAG de Airflow, guías y evidencias |

Dentro de `datalake/`:

- [`README.md`](datalake/README.md): arquitectura, diccionario de datos, despliegue y costos.
- [`docs/guias/`](datalake/docs/guias/): una guía por fase (00–10).
- [`evidencias/docEVIDENCIA/EVIDENCIAS.md`](datalake/evidencias/docEVIDENCIA/EVIDENCIAS.md): capturas y logs de cada requisito.
- Código: `src/`, `dags/`, `infra/terraform/`, `sql/`, `tests/`.
- [`rss-local/`](datalake/rss-local/): implementación alternativa del Data Lake RSS.

Dentro de `datawarehouse/`:

- [`README.md`](datawarehouse/README.md): arquitectura, operación y documentación de la migración.
- [`docs/guias/`](datawarehouse/docs/guias/): guías de despliegue y ejecución por fase.
- [`evidencias/docEVIDENCIA/EVIDENCIAS.md`](datawarehouse/evidencias/docEVIDENCIA/EVIDENCIAS.md): capturas y resultados de la práctica.
- Código: `src/`, `dags/`, `dbt/`, `infra/terraform/`, `sql/`, `tests/`.
