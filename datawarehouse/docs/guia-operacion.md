# Operación: guías por sección

**Estado:** las capturas registran S3, EC2/VPC, fuentes, Redshift y una ejecución exitosa del lote inicial. Los escenarios incrementales, SCD2 y recuperación no se completaron antes del cierre solicitado; consultar [evidencias](../evidencias/docEVIDENCIA/EVIDENCIAS.md) y [limpieza](guia-seguridad-costos-limpieza.md). Los comandos son instrucciones, no resultados verificados en nuevas ejecuciones.

1. [Preparación operacional de acceso (sin evidencia)](guias/00-acceso-captura.md)
2. [01 · Terraform, S3, red y roles](guias/01-terraform-s3-red-roles.md)
3. [02 · Fuentes RDS, DocumentDB y generadores](guias/02-fuentes-generadores.md)
4. [03 · Extracción S3 y replay](guias/03-extraccion-replay.md)
5. [04 · Redshift y dbt](guias/04-redshift-dbt.md)
6. [05 · EC2, Airflow y acceso SSM](guias/05-ec2-airflow.md)
7. [06 · Escenarios y recuperación](guias/06-escenarios-recuperacion.md)
8. [07 · Retiro y dependencias](guias/07-retiro-dependencias.md)

La [matriz de evidencias](../evidencias/docEVIDENCIA/EVIDENCIAS.md) fija **5 imágenes mínimas**: S3/Terraform; runtime (VPC/IAM EC2/EC2); fuentes (RDS/DocumentDB); Redshift/IAM COPY; Airflow/dbt. La primera es S3/Terraform (1.1), no identidad. Manifiestos, escenarios, costos y retiro se acreditan con salidas textuales reproducibles, sin imágenes adicionales obligatorias. Tras cada servicio o escenario detenerse y confirmar su evidencia; los servicios provisionados juntos comparten imagen, pero se confirma cada uno antes de la siguiente fase o del retiro. Solo después delegar publicación de fase a free-worker. No registrar secretos. Mantener dependencias; consultar [seguridad y limpieza](guia-seguridad-costos-limpieza.md), [costos](costos.md) e [infraestructura](../infra/README.md).
