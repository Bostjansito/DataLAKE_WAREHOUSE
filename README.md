# Data Lake de noticias RSS

Proyecto académico para aprender un flujo de datos de extremo a extremo con noticias RSS de El Tiempo: ingesta, lakehouse medallón, análisis de texto, catálogo, consultas y orquestación. La ruta local permite aprender y probar sin AWS; la ruta AWS es opcional y puede generar cargos.

| Parte | Carpeta | Contenido |
|---|---|---|
| Data Lake de noticias RSS | [`datalake/`](datalake/README.md) | Arquitectura, código, Terraform, DAG de Airflow, guías y evidencias |
| Data Warehouse | [`datawarehouse/`](datawarehouse/README.md) | Migración AWS; S3 y EC2/VPC demostrados y retirados, fuentes y pipeline pendientes. [Instrucciones](datawarehouse/docs/Instrucciones%20-%20Arquitecturas%20de%20datos%20-%20DataWarehouse.md) · [Evidencias](datawarehouse/evidencias/docEVIDENCIA/EVIDENCIAS.md) |

> **Estado de evidencia:** el orquestador registró 11 pruebas locales aprobadas y una ingesta RSS HTTPS real en `evidence/`; revise [evidencias](docs/guias/08-evidencias-demo-costos.md) para distinguir fixtures sintéticas, feeds reales y estado AWS. La identidad STS y el MCP están verificados en `evidence/access.json`. Las capturas de S3, Comprehend, Glue, Athena y Airflow siguen pendientes de una ejecución AWS autorizada: no se han creado recursos ni emitido llamadas AWS facturables.

## Recorrido recomendado

1. Lea [arquitectura y límites](docs/arquitectura.md), [fuentes RSS](docs/fuentes-rss.md) y el [diccionario](docs/diccionario-datos.md).
2. Siga [acceso y preparación](docs/guias/01-acceso.md) y [pipeline local](docs/guias/02-pipeline-local.md) antes de usar servicios facturables.
3. Para AWS, siga [despliegue Terraform](docs/guias/07-terraform.md) primero con EC2 desactivada; luego revise [S3](docs/guias/03-s3.md), [Comprehend](docs/guias/04-comprehend.md), [Glue y Athena](docs/guias/05-glue-athena.md) y [EC2 y Airflow](docs/guias/06-ec2-airflow.md), que requiere subir el artefacto y habilitar EC2 explícitamente.
4. Prepare capturas y demostración con [evidencias](docs/guias/08-evidencias-demo-costos.md); revise [calidad, incrementalidad y recuperación](docs/calidad-recuperacion.md) y [costos](docs/costos.md).

## Capas y flujo

- **Bronze:** respuestas RSS originales y manifiestos de ingesta, conservados para reprocesamiento.
- **Silver:** noticias vigentes limpias y validadas, entidades y frases clave; datos analíticos en Parquet. Los registros inválidos se aíslan con motivo.
- **Gold:** agregaciones por día, sección, medio, entidad y frase para consultas analíticas.
- **Airflow en EC2 (opcional):** coordina el pipeline en el despliegue AWS. El modo local no requiere instancia.
- **AWS Glue Data Catalog y Athena (opcional):** metadatos y consultas sobre Parquet en S3.

El diseño usa un solo bucket S3 para datos y artefactos del proyecto. La infraestructura EC2 queda desactivada por defecto. La instancia prevista no necesita puertos entrantes públicos: el acceso administrativo es mediante Systems Manager Session Manager y el túnel local a Airflow.

## Requisitos y ejecución

El proyecto requiere Python 3.11 o posterior. Los comandos completos de Terraform, perfil AWS y sesión SSM se encuentran en sus guías específicas. Nunca incluya credenciales en archivos versionados; use perfiles/roles AWS documentados en [acceso](docs/guias/01-acceso.md).

Para la ruta local, instale el paquete con `python -m pip install -e .` y siga los comandos del CLI `rss-lake` en [pipeline local](docs/guias/02-pipeline-local.md). La ruta AWS se separa con `--bucket`, región y enriquecimiento explícitos; requiere aprobación antes de crear recursos o realizar llamadas facturables.

## Calidad, reproducibilidad y límites

Las noticias se identifican con hash del medio y enlace canónico; la estrategia y límites están en [calidad y recuperación](docs/calidad-recuperacion.md). Reprocesar lee Bronze, no vuelve a consultar RSS. Cada corrida publica snapshots Silver/Gold completos tras validación; los archivos de snapshots anteriores no se agregan a las métricas vigentes. El registro de catálogo Glue actualiza las seis tablas por separado, por lo que puede haber una ventana transitoria de tablas en snapshots distintos: consulte después de finalizar la etapa y su conciliación. Comprehend analiza únicamente título y descripción RSS; no descarga el artículo completo, resuelve alias ni garantiza interpretación contextual perfecta.

## Documentación

- [Reporte de entrega, pruebas y contribuciones por agente](docs/reporte-entrega.md)
- [Arquitectura](docs/arquitectura.md)
- [Fuentes RSS](docs/fuentes-rss.md)
- [Diccionario de datos](docs/diccionario-datos.md)
- [Calidad, incrementalidad y recuperación](docs/calidad-recuperacion.md)
- [Costos y supuestos](docs/costos.md)
- Guías detalladas: [01 Acceso](docs/guias/01-acceso.md), [02 Pipeline local](docs/guias/02-pipeline-local.md), [03 S3](docs/guias/03-s3.md), [04 Comprehend](docs/guias/04-comprehend.md), [05 Glue y Athena](docs/guias/05-glue-athena.md), [06 EC2 y Airflow](docs/guias/06-ec2-airflow.md), [07 Terraform](docs/guias/07-terraform.md), [08 Evidencias, demo y costos](docs/guias/08-evidencias-demo-costos.md).

## Contribución

El proyecto sigue el enfoque funcional y documentado. Las pruebas están en `tests/` y se ejecutan con `python -m pytest`. La documentación evoluciona en `docs/`. Los archivos de evidencia en `evidence/` son resultados de ejecuciones pasadas, no deben modificarse manualmente.