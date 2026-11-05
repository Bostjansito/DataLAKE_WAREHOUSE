# Arquitecturas de datos: Data Lake y Data Warehouse

> 📄 **Evidencias del Data Lake:** [`datalake/evidencias/docEVIDENCIA/EVIDENCIAS.md`](datalake/evidencias/docEVIDENCIA/EVIDENCIAS.md)
> ([ver en GitHub](https://github.com/Bostjansito/DataLAKE_WAREHOUSE/blob/main/datalake/evidencias/docEVIDENCIA/EVIDENCIAS.md))

| Parte | Carpeta | Contenido |
|---|---|---|
| Data Lake de noticias RSS | [`datalake/`](datalake/README.md) | Arquitectura, código, Terraform, DAG de Airflow, guías y evidencias |
| Data Warehouse | [`datawarehouse/`](datawarehouse/README.md) | Migración AWS; S3 y EC2/VPC demostrados y retirados, fuentes y pipeline pendientes. [Instrucciones](datawarehouse/docs/Instrucciones%20-%20Arquitecturas%20de%20datos%20-%20DataWarehouse.md) · [Evidencias](datawarehouse/evidencias/docEVIDENCIA/EVIDENCIAS.md) |

Dentro de `datalake/`:

- [`README.md`](datalake/README.md): arquitectura, diccionario de datos, despliegue y costos.
- [`docs/guias/`](datalake/docs/guias/): una guía por fase (00–10).
- [`evidencias/docEVIDENCIA/EVIDENCIAS.md`](datalake/evidencias/docEVIDENCIA/EVIDENCIAS.md): capturas y logs de cada requisito.
- Código: `src/`, `dags/`, `infra/terraform/`, `sql/`, `tests/`.
