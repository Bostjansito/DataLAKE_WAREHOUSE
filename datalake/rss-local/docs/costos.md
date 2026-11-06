# Costos y control del consumo

Estimación del escenario ilustrativo: **USD 0.241118576 (≈ USD 0.24112)**, precios consultados el 2026-10-22 para `us-east-1`. No es una factura, cotización, tarifa garantizada ni gasto real del proyecto. Las cantidades son editables; revise precios y supuestos antes de desplegar. El cálculo de referencia está registrado en [`evidence/pricing-assumptions.json`](../evidence/pricing-assumptions.json) y las fuentes oficiales se enlazan abajo.

## Variables a estimar

| Servicio | Supuesto/medida necesaria | Control práctico |
|---|---|---|
| S3 | GB-mes por capa, requests, recuperación y versiones retenidas | Un bucket, lifecycle revisado, borrar datos solo tras aprobación |
| EC2 | Tipo y horas en estado activo; región y sistema operativo | Instancia opcional desactivada por defecto; limitar horas de laboratorio |
| EBS | GB-mes y snapshots | Disco mínimo validado y eliminación revisada |
| Glue | almacenamiento de catálogo y operaciones de catálogo | Tablas explícitas; registrar solo particiones requeridas |
| Athena | bytes escaneados por consulta y ubicación S3 de resultados | Parquet, filtro por partición, workgroup con límite si está configurado |
| Comprehend | unidades de texto/caracteres analizados por operación y tipo de API | Cache por hash y evitar reenviar texto sin cambios |
| Transferencia | región, salida a internet y movimientos entre zonas/servicios | Mantener recursos en región consistente y no descargar datasets innecesarios |
| CloudWatch/SSM | retención de logs, sesiones y características según región | Retención limitada y seguimiento de cargos asociados |

## Estimación ilustrativa: una sesión de laboratorio

El modelo supone una EC2 `t3.medium` encendida 4 horas, una IPv4 pública asociada 4 horas, volumen raíz 30 GiB eliminado después de 4 horas, 0.1 GB S3 almacenado 7 días, 1,000 requests Tier 1 (PUT/LIST combinados), 10,000 GET, 20 consultas Athena de 10 MiB cada una y 30 textos de 500 caracteres cada uno enviados a las dos APIs síncronas de Comprehend.

| Servicio / unidad | Tarifa usada y supuesto | Cálculo | USD |
|---|---|---|---:|
| EC2 `t3.medium` | $0.0418/h (fuente oficial de tipo T3) | 4 h × 0.0418 | 0.167200000 |
| IPv4 pública | $0.005/h | 4 h × 0.005 | 0.020000000 |
| EBS gp3, 30 GiB | **Supuesto** $0.08/GB-mes del ejemplo oficial; no es precio regional verificado | aprox. 30 × 4 h/720 h de mes de 30 días × 0.08 | 0.013333333 |
| S3, almacenamiento | $0.023/GB-mes en primera banda consultada | 0.1 × 7/30 × 0.023 | 0.000536667 |
| S3, Tier 1 | $0.005 por 1,000 PUT/LIST; 1,000 requests combinados | 1,000/1,000 × 0.005 | 0.005000000 |
| S3, Tier 2 | $0.004 por 10,000 GET; 10,000 requests | 10,000/10,000 × 0.004 | 0.004000000 |
| Athena | $5/TB escaneado | 20 × 10 MiB × $5/10¹² bytes | 0.001048576 |
| Comprehend | $0.0001 por unidad de 100 caracteres | 30 × 500/100 × 2 APIs × 0.0001 | 0.030000000 |
| **Total estimado** | | | **0.241118576** |

Fuentes y supuestos detallados: [`evidence/pricing-assumptions.json`](../evidence/pricing-assumptions.json), [T3](https://aws.amazon.com/ec2/instance-types/t3/), [IPv4](https://aws.amazon.com/vpc/pricing/), [Comprehend](https://aws.amazon.com/comprehend/pricing/), [Athena](https://aws.amazon.com/athena/pricing/), [EBS](https://aws.amazon.com/ebs/pricing/) y [lista oficial de precios S3 `us-east-1`](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/us-east-1/index.json). Las tarifas públicas pueden cambiar; la fecha de consulta y el registro de cálculo prevalecen frente a este ejemplo para reproducir esa estimación.

## Qué incluye y qué excluye

Esta cifra **no es el costo real de ejecutar el proyecto**: `evidence/access.json` registra que no se crearon recursos AWS y que no se ejecutaron llamadas de Comprehend o Athena; `evidence/live-feeds.json` corresponde a RSS HTTPS con NLP deshabilitado. La estimación supone eliminación del volumen S3 tras 7 días, aunque el lifecycle Terraform **no expira los objetos actuales**: el dueño debe limpiar o recalcular si los retiene. No incluye impuestos, transferencia de datos, monitoreo pago, Glue sobre asignaciones gratuitas, solicitudes adicionales, volumen mayor, Comprehend fuera del supuesto, sesiones más largas ni costos residuales si EC2/EBS/IPv4 sobreviven a la limpieza.

La tarifa de EBS usada es explícitamente una **suposición** tomada del ejemplo público, no una cotización regional verificada. Sustituirla por el precio actual de `us-east-1` en [AWS Pricing Calculator](https://calculator.aws/) antes de presentar presupuesto. S3/EC2/Comprehend/Athena se basan en las fuentes oficiales indicadas; no extrapole el total a otra región.

## Procedimiento

1. Defina región, días/horas de EC2, cantidad de corridas, artículos por feed, longitud media de texto, proporción de cambios y retención de datos.
2. Mida volumen real de Parquet/JSON y bytes escaneados en una corrida controlada autorizada.
3. Ingrese cantidades y productos en AWS Pricing Calculator; guarde captura/fecha junto al reporte.
4. Compare escenario de una sesión mínima con varios días retenidos; explique qué supuestos dominan el total.
5. Revise AWS Billing/Cost Explorer tras la sesión. Presupuesto/alertas ayudan a monitorear pero no son límite de gasto garantizado.
6. Aplique limpieza Terraform y compruebe recursos que sobreviven: bucket/versiones, EBS/snapshots, logs y resultados Athena.

## Fuentes oficiales de precios

- [Amazon S3](https://aws.amazon.com/s3/pricing/)
- [Amazon EC2](https://aws.amazon.com/ec2/pricing/on-demand/)
- [Amazon EBS](https://aws.amazon.com/ebs/pricing/)
- [AWS Glue](https://aws.amazon.com/glue/pricing/)
- [Amazon Athena](https://aws.amazon.com/athena/pricing/)
- [Amazon Comprehend](https://aws.amazon.com/comprehend/pricing/)
- [AWS Systems Manager](https://aws.amazon.com/systems-manager/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

Los precios numéricos son una consulta fechada del 2026-10-22, no tarifas garantizadas a futuro. Consulte la región y precios vigentes antes de cotizar; no infiera cargos reales del escenario ilustrativo.
