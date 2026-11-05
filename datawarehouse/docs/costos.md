# Estimación de costos y límites de la práctica

Consulta histórica: **2026-11-05, us-east-1, USD**, API pública AWS Price List `GetProducts`. Tarifas y filtros en [precios-consultados.json](../evidencias/00-acceso/precios-consultados.json). Son precios On-Demand sin impuestos ni descuentos; no equivalen al consumo de la cuenta ni garantizan Free Tier. S3 y runtime se desplegaron y retiraron posteriormente; ver [evidencias](../evidencias/docEVIDENCIA/EVIDENCIAS.md).

| Componente de referencia | Tarifa consultada | Unidad |
|---|---:|---|
| EC2 Linux t3.medium | 0.0416 | instancia/hora |
| RDS MySQL db.t3.micro Single-AZ | 0.017 | instancia/hora |
| DocumentDB db.t3.medium Standard, no I/O-Optimized | 0.078 | instancia/hora |
| Redshift Serverless On-Demand | 0.375 | RPU/hora |
| IPv4 pública | 0.005 | dirección/hora |
| EBS gp3 | 0.08 | GB/mes provisionado |
| RDS MySQL gp3 | 0.115 | GB/mes provisionado |
| DocumentDB Standard almacenamiento | 0.10 | GB/mes consumido |
| S3 Standard, primer tramo | 0.023 | GB/mes almacenado |

## Dos escenarios, no una factura prometida

**Práctica breve:** una instancia de cada servicio de la tabla, EC2/RDS/DocumentDB/una IPv4 durante dos horas y Redshift consumiendo exactamente 8 RPU durante 15 minutos: subtotal de cómputo e IPv4 **USD 1.03320**. Fórmula: `2*(0.0416+0.017+0.078+0.005) + 8*0.375*0.25`. La espera por capturas puede aumentar este costo; no se presume consumo nulo mientras el usuario decide.

**Advertencia de abandono:** mismos recursos durante 730 horas y consumo Redshift continuo de 8 RPU: subtotal **USD 2293.3680**. Redshift no necesariamente consume todo el mes: este escenario ilustra el riesgo de actividad continua, no el costo fijo de un workgroup inactivo. El cálculo se realizó con aritmética decimal, no mediante estimación mental.

Ambos subtotales **excluyen** EBS, almacenamiento RDS/DocumentDB/Redshift/S3, I/O y backups DocumentDB, snapshots, solicitudes y versiones S3, transferencia entre AZ/egreso, Secrets Manager y posibles créditos CPU de las bases burstable. Las cantidades almacenadas, número de solicitudes y tiempo real de trabajo deben añadirse mediante [AWS Pricing Calculator](https://calculator.aws/). La consulta de almacenamiento Redshift no devolvió productos con el filtro utilizado: no se inventa esa tarifa. El tamaño y clase realmente configurados por Terraform prevalecen sobre este ejemplo.

## Selección para el laboratorio

La configuración prevista usa RDS MySQL 8.4 `db.t3.micro` Single-AZ con gp3 y DocumentDB 5.0 `db.t3.medium` provisionado, ambos privados. Son opciones pequeñas para una práctica, no una recomendación de alta disponibilidad: Single-AZ y clases burstable intercambian resiliencia y rendimiento sostenido por menor capacidad. DocumentDB Standard cobra instancia, almacenamiento e I/O; comparar con I/O-Optimized según el patrón real, no asumir que es más barato. Consultar disponibilidad de clase, versión y tarifas actuales en la región.

Se eligió MySQL 8.4 en lugar de 8.0 porque el soporte estándar de RDS MySQL 8.0 terminó el **31 de julio de 2026**; el soporte extendido puede generar cargos adicionales. Terraform deshabilita la inscripción en Extended Support (`open-source-rds-extended-support-disabled`), por lo que corresponde mantener una versión elegible y revisar su ciclo de vida antes de desplegar. Véase [ciclo de versiones RDS MySQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/MySQL.Concepts.VersionMgmt.html).

La consulta posterior de precios para us-east-1 informó DocumentDB `db.t3.medium` Standard **USD 0.078/h** frente a I/O-Optimized **USD 0.0858/h**; los créditos CPU adicionales consultados cuestan **USD 0.09/vCPU-h**. Son tarifas unitarias, no un total: I/O, almacenamiento y carga efectiva determinan la comparación. RDS `db.t3.micro` consultado: **USD 0.017/h**. Consultar nuevamente los precios oficiales antes de desplegar.

**DocumentDB provisionado frente a Serverless:** se selecciona DocumentDB 5.0 provisionado con una instancia `db.t3.medium`, opción pequeña consultada como disponible en us-east-1; una sola instancia no ofrece alta disponibilidad. [DocumentDB Serverless](https://docs.aws.amazon.com/documentdb/latest/developerguide/docdb-serverless.html) ajusta capacidad automáticamente para cargas variables, pero no es requisito académico ni sinónimo de DocumentDB Elastic. Su costo no se ha consultado para esta comparación; no asumir que resulte menor ni que no facture en reposo. La alternativa Serverless 8 requiere evaluar disponibilidad, compatibilidad de aplicación y provider: el esquema AWS provider 5.100 utilizado no contiene campos o bloques Serverless en `aws_docdb_cluster`, por lo que implicaría actualizar el provider y verificar compatibilidad antes de adoptarla. Esta práctica mantiene la opción provisionada.

Las instrucciones académicas permiten **Redshift Serverless o provisionado**. Este proyecto configura Serverless para la demostración; un clúster provisionado es una alternativa permitida que requiere evaluar nodos, duración y almacenamiento, no un cambio ya desplegado. Serverless no implica costo cero ni escala a cero para los demás servicios. Comparar con [precios Redshift](https://aws.amazon.com/redshift/pricing/) y la calculadora antes de elegir.

## Controles y costos persistentes

- Desplegar por fases y solo el servicio que vaya a capturarse. La primera captura es S3/Terraform (1.1); identidad se comprueba sin imagen ni confirmación. Con los tres flags de despliegue en `false` solo se crea almacenamiento S3, no cómputo, bases ni red.
- Sin NAT Gateway ni endpoints Interface en esta arquitectura de laboratorio; EC2 emplea salida pública y acceso SSM, sin puertos de entrada. La IPv4 pública sí se factura. El endpoint S3 Gateway permite acceso de COPY privado.
- Los límites de capacidad/uso de Redshift ayudan a acotar consumo; un presupuesto AWS **alerta**, no es un apagado inmediato ni sustituye la eliminación.
- Tras confirmación explícita de captura, retirar los recursos propios que no sean dependencia de la siguiente fase. Fuentes y EC2 deben coexistir para el pipeline final: retirar una base sin exportar sus datos rompe la demostración; documentar retención y reconstrucción, nunca destruir por adelantado.
- Detener EC2 no elimina EBS; detener RDS/DocumentDB no elimina almacenamiento/backups y las bases pueden reiniciarse automáticamente según su servicio. La eliminación de cómputo no elimina versiones S3, snapshots ni secretos pendientes de borrado. Evitar mantener recursos innecesarios mientras se esperan nuevas fases.
- Eliminar un bucket versionado requiere tratar versiones y delete markers; no hacer vaciado masivo automático. Conservar evidencias y exportaciones fuera del recurso antes de su eliminación autorizada. Revisar plan Terraform y limitarse al estado de este proyecto; nunca borrar recursos de la cuenta por coincidencia de nombre.

Fuentes oficiales: [EC2](https://aws.amazon.com/ec2/pricing/on-demand/), [IPv4/VPC](https://aws.amazon.com/vpc/pricing/), [EBS](https://aws.amazon.com/ebs/pricing/), [RDS MySQL](https://aws.amazon.com/rds/mysql/pricing/), [DocumentDB](https://aws.amazon.com/documentdb/pricing/), [Redshift](https://aws.amazon.com/redshift/pricing/), [S3](https://aws.amazon.com/s3/pricing/), [Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/).
