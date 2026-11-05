# Reporte de entrega por secciones

## 1. Acceso y autorización

Se verificaron identidad AWS mediante `aws sts get-caller-identity`, negociación MCP `initialize` y `tools/list` contra el proxy AWS configurado. Evidencia: [`access.json`](../evidence/access.json). No se dedujo autorización para crear recursos ni consumir servicios facturables. No se ejecutaron `terraform apply`, Comprehend ni Athena; tampoco se subieron objetos a S3.

**Responsable:** orquestador `Actividad Data Lake completa`, comprobación inicial y límite de autorización. No hubo un subagente de acceso.

## 2. RSS y arquitectura medallón

Tres feeds oficiales configurados en `config/feeds.json`: política, economía y deportes de El Tiempo. Implementación completa en `lake/core.py`, `lake/storage.py` y `lake/schemas.py`: Bronze original, metadatos UTC/hash/HTTP, parsing seguro RSS/Atom, limpieza HTML, enlaces canónicos, identidad por medio/enlace, deduplicación, versiones vigentes, cuarentena trazable y métricas conciliables. Silver y Gold están en Parquet con partición `publication_date` y archivos tipados incluso sin filas.

Se ejecutó una extracción HTTPS **real**: tres fuentes exitosas, 30 registros recibidos/nuevos/vigentes, cero rechazados/duplicados/fechas desconocidas y estado `complete`. NLP explícitamente deshabilitado: no se atribuyen entidades ficticias a estas noticias. Evidencia: [`live-feeds.json`](../evidence/live-feeds.json); objetos originales y snapshots están disponibles localmente bajo `.local-lake/live/`.

**Subagente:** `PipelineMedallon`, implementación del core, almacenamiento, esquemas, feeds y dependencias. **Orquestador:** CLI, ejecución real y consolidación de evidencia.

## 3. Enriquecimiento y recuperación

Comprehend está implementado con `DetectEntities` y `DetectKeyPhrases`, idioma, texto/hash, fecha y confidencias; caché durable por texto/idioma/versión del analizador y por operación. Estados explícitos: completado, deshabilitado, vacío, idioma no admitido y texto demasiado extenso. No se truncó texto silenciosamente. Pruebas con dobles controlados demuestran recuperación si falla la segunda operación; no son evidencia AWS.

`--replay` recupera checkpoints sin nueva extracción. `--from-bronze LOTE` con un ID destino nuevo reconstruye usando las claves originales, sin copiar Bronze. Repetir un lote histórico no rebobina la versión vigente ni república catálogo. Snapshots completos se validan antes del cambio atómico de `_control/current.json`. Se requiere un escritor; el DAG limita concurrencia y no deben ejecutarse CLI escritores externos simultáneos.

**Subagente:** `PipelineMedallon`. **Revisor:** `RevisionFuncional`, detectó y permitió corregir reintentos HTTP transitorios, replay histórico y colisión de destino de reconstrucción. La revisión posterior no reportó bloqueadores de código.

## 4. Glue, Athena e infraestructura

Terraform incluye exactamente un bucket privado/cifrado/versionado con lifecycle, base y seis tablas Glue, particiones por fecha, workgroup Athena con límite por consulta, IAM acotado y EC2 opcional apagada por defecto. EC2 usa VPC sin NAT, cero ingreso, SSM, IMDSv2 hop limit 2, volumen cifrado y créditos CPU Standard. Bootstrap verifica SHA-256 y seguridad del archivo antes de construir Compose; usa paquetes AL2023 `awscli-2` y `curl-minimal`, y genera secretos exclusivamente en el host.

`lake/catalog.py` reconcilia ubicaciones y particiones; `sql/` contiene consultas analíticas, conciliaciones, integridad y comparación con/sin filtro. Glue no ofrece transacción de seis tablas: no consultar mientras `_control/catalog_status.json` sea `updating`; reejecutar catalogación tras un fallo hasta `ready`. La etapa Athena verifica conteos, huérfanos, agregados y conserva IDs/bytes reales cuando se ejecute en AWS.

**Subagente:** `InfraestructuraTerraform`, IaC, IAM, bootstrap y ocho archivos SQL. **Orquestador:** publicación Glue y validaciones Athena. **Revisor:** `RevisionSeguridad`, detectó y permitió corregir autorización de existencia S3 y conflicto de paquete curl; revisión final sin bloqueadores. Se redujeron permisos S3 y se validó el nombre de base.

Validaciones reales: Terraform **1.10.5**, provider AWS **5.100.0**, `init -backend=false`, `fmt -check`, `validate` y `bash -n` del bootstrap. No se ejecutaron `plan` ni `apply`. Estos checks no prueban permisos o disponibilidad de recursos de la cuenta.

## 5. Airflow y Compose

`dags/rss_lake.py` coordina diez tareas: acceso/configuración, ingesta, transformación, NLP, Silver, Gold, validación/publicación, Glue, Athena y registro final. Incluye reintentos acotados, logs de lote/tarea/fuente, control de concurrencia y parámetros de replay, reconstrucción y fallo controlado. Por seguridad el DAG nace pausado y sin horario; la guía explica habilitar `LAKE_SCHEDULE` únicamente durante el laboratorio.

Se construyó la imagen Docker y se levantó **Compose real local** con PostgreSQL, inicialización, webserver y scheduler. Se observó salud de metadatabase/scheduler y se importó el DAG: diez tareas, `max_active_runs=1`, `max_active_tasks=1`, sin errores. El smoke no ejecutó el DAG AWS ni pasó credenciales a los contenedores. Los contenedores, volúmenes, red y archivo temporal de secretos se eliminaron; las imágenes locales quedaron en caché. Evidencia: [`deployment-validation.json`](../evidence/deployment-validation.json).

**Responsable:** orquestador, integración de CLI, catálogo, DAG, Dockerfile y Compose. `RevisionSeguridad` revisó también los healthchecks, secretos y aislamiento.

## 6. Pruebas y evidencias

**11 pruebas aprobadas.** Smoke específico final ejecutado también con variables heredadas hostiles (`LAKE_BUCKET`, NLP Comprehend y ruta de feeds inexistente): permaneció local y no llamó AWS. Ejercita carga inicial, rechazo, repetición actual/histórica, incrementalidad, cambios de texto/fecha, recuperación, restauración limpia desde Bronze y nueva partición/catalogación con doble Glue validado contra formas del SDK. Controles adicionales: XML externo, traversal, checksums, conflicto de padre, caché por operación y cancelación Athena.

- [`local-smoke.json`](../evidence/local-smoke.json): comandos, resultados, métricas, hashes, rutas y snapshot.
- [`test-results.xml`](../evidence/test-results.xml): once casos realmente ejecutados.
- [`live-feeds.json`](../evidence/live-feeds.json): lectura de noticias reales sin NLP AWS.
- [Matriz de los ocho escenarios y capturas requeridas](guias/08-evidencias-demo-costos.md).

Para reproducir: siga [pipeline local](guias/02-pipeline-local.md) y ejecute `python scripts/smoke.py` tras instalar `.[test]` en el entorno virtual.

## 7. Aprendizaje, costos y documentación

Se entregan diagrama Mermaid, fuentes, diccionario, reglas/calidad/recuperación y ocho guías independientes con procedimientos AWS/Terraform y capturas. El escenario de costos documentado estima **USD 0.24112** para una sesión ilustrativa de cuatro horas; no es factura ni límite garantizado. Tarifas, cantidades, cálculo determinista, exclusiones y supuesto EBS explícito están en [costos](costos.md) y [`pricing-assumptions.json`](../evidence/pricing-assumptions.json).

**Subagente:** `GuiasAprendizaje`, documentación técnica y guías; el orquestador integró al cierre la matriz y este reporte tras la interrupción de la última reactivación documental. Su trabajo anterior sí permanece entregado.

## 8. Límite pendiente de autorización, no evidencia fabricada

No se crearon recursos AWS. Por tanto, siguen sin ejercitarse: bootstrap en EC2 real, IAM efectivo en la cuenta, DAG end-to-end en EC2, S3 remoto, análisis real Comprehend, tablas/particiones Glue, SQL/bytes Athena y capturas de consola de esos servicios. Código y procedimientos completos están entregados; realizar esa demostración requiere autorización explícita de despliegue/consumo y seguir las guías, incluido respaldo y borrado de versiones del bucket.

## Subagentes creados

| Agente | Contribución concreta |
|---|---|
| `PipelineMedallon` | Core RSS/Bronze/Silver/Gold, almacenamiento local/S3, caché/estados NLP, esquemas, feeds y dependencias |
| `InfraestructuraTerraform` | Terraform, IAM, seguridad/costo, bootstrap y consultas SQL |
| `GuiasAprendizaje` | README, arquitectura, diccionario, fuentes, calidad, costo y ocho guías |
| `RevisionFuncional` | Revisión funcional, tres hallazgos de recuperación corregidos y revisión de cierre |
| `RevisionSeguridad` | Revisión de seguridad, dos P1 corregidos y cierre de cambios finales |

El orquestador retuvo la integración y ejecución de pruebas; no se delegó ni fabricó la evidencia AWS.
