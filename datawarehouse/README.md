# Data Warehouse: migración de DE-DW a AWS

Implementación de la migración del proyecto local **DE-DW**, localizado junto a este repositorio. Integra RDS MySQL y DocumentDB privados, exportaciones S3 por lote, COPY a Redshift Serverless y modelos dbt; Airflow y dbt se ejecutan en la misma EC2. Los tres hechos conservan ventas por línea, reseñas y navegación; clientes y productos conservan historia SCD2.

**Estado de AWS:** no se han desplegado recursos nuevos ni ejecutado el pipeline en AWS. La primera captura prevista es S3/Terraform (1.1); acceso e identidad son comprobaciones operacionales, sin captura ni confirmación exigida. Las validaciones locales se distinguen de evidencia AWS en [validación](evidencias/validacion.md). No hay capturas confirmadas ni commits/push de esta migración.

## Documentación

- [Instrucciones originales, movidas desde docs/ general](docs/Instrucciones%20-%20Arquitecturas%20de%20datos%20-%20DataWarehouse.md)
- [Arquitectura, reglas preservadas y diferencias](docs/arquitectura.md)
- [Operación y guías por sección](docs/guia-operacion.md)
- [Terraform, despliegue e instalación en EC2](infra/README.md)
- [Seguridad y eliminación por dependencias](docs/guia-seguridad-costos-limpieza.md)
- [Estimación verificable de costos](docs/costos.md)
- [Documento de evidencias por servicio](evidencias/docEVIDENCIA/EVIDENCIAS.md)

## Código

- `infra/terraform/`: recursos propios declarados con Terraform; flags por fase evitan desplegar todo al comenzar.
- `src/ecommerce_dw/sources/`: generadores y cambios reproducibles adaptados del origen.
- `src/aws_dw/`: CLI, conexiones TLS, extracción/manifiestos, carga/ledger y ejecución dbt.
- `dags/ecommerce_dw_pipeline.py`: DAG único para el lote completo, reintentos y recuperación.
- `dbt/`: capas intermediate/quarantine/marts, seeds, snapshots SCD2 y pruebas de negocio.
- `sql/`: conciliaciones consultables en Redshift.
- `tests/`: pruebas locales del contrato del pipeline; no sustituyen ejecutar sobre AWS.

## Pausas y publicación

Antes de desplegar, comprobar `aws sts get-caller-identity`, perfil y región; si se usa consola, contrastar su identidad. No se exige captura ni confirmación de acceso. La identidad observada es cuenta `241732001318`, `user/user_cli`, distinta a la cuenta histórica del Data Lake. No utilizar evidencia antigua ni asumir permisos de despliegue por el éxito de STS. Crear recursos requiere autorización explícita de ejecución y gasto; preguntar quién ejecuta no la sustituye.

Después de cada servicio o escenario, se detiene el avance para que el usuario tome y confirme su captura. Solo tras la confirmación se retiran recursos propios innecesarios, sin romper dependencias ni destruir datos ajenos, y se delega el commit/push de fase a **free-worker** sobre `feature/practica-merge`. Mientras no haya confirmación, no desmontar ni publicar la fase.
