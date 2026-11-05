# Evidencias – Data Warehouse en AWS

**Estado: capturas de fuentes y Redshift confirmadas por el usuario.** En la cuenta `241732001318`, región `us-east-1`, RDS, DocumentDB y Redshift fueron observados disponibles. Las fuentes, Redshift y sus dependencias permanecen activas para la demostración; retirarlas al final según el procedimiento acordado.

Identidad CLI observada: cuenta **241732001318**, `arn:aws:iam::241732001318:user/user_cli`. La cuenta histórica del Data Lake **387512138242** es distinta; no reutilizar sus imágenes para este almacén. [Salida STS real](../00-acceso/sts-get-caller-identity.json) · [Inventario previo limitado](../00-acceso/inventario-previo.json). Son soportes de seguridad operacional, no una fase de evidencia: acceso no requiere captura ni confirmación.

## Plan mínimo: 5 imágenes, sin capturas redundantes

Las [instrucciones originales](../../docs/Instrucciones%20-%20Arquitecturas%20de%20datos%20-%20DataWarehouse.md), secciones 3.5 y 4, exigen evidencias de funcionamiento y escenarios, pero no una imagen por comprobación: las capturas complementan el código y las instrucciones reproducibles. Se conservan las imágenes de servicios AWS y ejecución de Airflow; el resto se acredita con resultados textuales reales. Se elimina la evidencia de acceso por indicación del usuario, sin eliminar comprobaciones de cuenta, perfil y región.

| ID / archivo previsto | Momento y contenido de la única imagen | Soporte textual de la fase | Estado |
|---|---|---|---|
| 1.1 · ubicación del archivo no indicada | Bucket `dw-raw-c89245ce4ec26c4e`; bloqueo público, cifrado AES256, versionado y política TLS verificados mediante AWS CLI | Terraform: 8 recursos creados y 8 retirados; bucket sin versiones ni cargas multipart antes del retiro | Confirmada por el usuario |
| 2.1 / 3.1 · [EC2 y VPC](../03-ec2vpc/03_d2_ec2vpc.png) | VPC `vpc-0b26389992211d765` disponible e instancia `i-0b65cd081428de5fc` running | [Inventario y pruebas SSM](../02-runtime/README.md); 31 recursos retirados tras la captura | Confirmada |
| 4.1 / 5.1 · [RDS y DocumentDB](../04-rdsdocdb/04_dw_rdsdocdb.png) | RDS `dw-mysql` y clúster/instancia DocumentDB `dw-docdb` disponibles | Disponibilidad confirmada por AWS CLI; conexión TLS y datos pendientes de verificación | Captura confirmada por el usuario |
| 6.1 · [Redshift](../06-redshift/06_dw_redshift.png) | Namespace `dw-namespace` y workgroup `dw-workgroup` disponibles | Disponibilidad confirmada por AWS CLI; conexión, COPY y capas pendientes | Captura confirmada por el usuario |
| 7.1 · [Airflow](../07-airflow/07_dw_airflowDAG.png) | DAG `ecommerce_dw_pipeline`, lote 0 reprocesado desde S3 | Ejecución `manual__2026-11-05T21:45:21+00:00`: success; dbt PASS=151 WARN=0 ERROR=0 | Captura confirmada por el usuario |

**Restricciones:** cinco es el mínimo previsto, no una autorización para comprimir contenido ilegible. Mostrar solo campos pertinentes mediante consultas de lectura o SQL reproducible; conservar las salidas completas saneadas como soporte. Usar ventanas simultáneas/multipanel y fuente legible, sin inventar paneles, alterar valores, recomponer éxitos ni atribuir a un mismo instante estados distintos. Si no cabe una evidencia obligatoria legible, dividir únicamente esa imagen y registrar el motivo y el total real; no exigir imágenes extra por pestaña, consulta o escenario. Una terminal con respuestas reales de AWS es válida salvo la UI de Airflow (7.1), que debe verse.

**Una pausa no equivale a una imagen nueva.** Confirmar cada servicio y escenario cuya evidencia se solicita antes de avanzar o retirar recursos. Por decisión del usuario, IAM no requiere captura ni confirmación independiente. Los flags actuales crean juntos RDS y DocumentDB: comparten una imagen, pero requieren confirmación de cada servicio. Mantener dependencias según las guías y registrar retención y costo.

Los escenarios se conservan por separado con identificadores **E1 inicial, E2 calidad, E3 repetición, E4 incremental, E5 SCD2, E6 fallo, E7 recuperación, E8 conciliación y E9 demostración**. E1/E2 pueden referenciar 7.1, sin otra imagen. E4/E5/E9 pueden corresponder a la misma ejecución de un lote nuevo si demuestra las tres condiciones, pero cada resultado y confirmación se registra por separado. E6 se confirma antes de ejecutar E7. Las comparaciones antes/después son archivos de salida, no capturas adicionales.

## Seguridad operacional previa (sin captura)

Antes de desplegar o borrar, comprobar identidad CLI con `aws sts get-caller-identity`, perfil y región; si se usa consola, contrastar su cuenta. Registrar cambios de identidad y no mezclar cuentas. STS identifica al ejecutor pero no demuestra permisos para crear recursos.

Esta comprobación no requiere imagen ni confirmación del usuario. La primera evidencia es **1.1 S3/Terraform**. Obtener autorización explícita antes de ejecutar operaciones que creen recursos o gasto; la pregunta sobre quién ejecutará no la sustituye.

## 1. S3 y Terraform

Terraform convierte la configuración de infraestructura en un plan revisable y un estado identificable. S3 conserva exportaciones y manifiestos por lote, separando almacenamiento de las fuentes y permitiendo reprocesar sin volver a consultarlas. Privacidad, cifrado y versionado mejoran el control frente a archivos locales, pero las versiones también pueden generar costo.

Usar únicamente la imagen 1.1 para Terraform y configuración S3; no pedir imágenes separadas de Permisos/Propiedades. Las consultas AWS de lectura pueden mostrar bloqueo público, cifrado, versionado y política TLS. Después guardar en texto el listado real `raw/<fuente>/<entidad>/batch_id=<id>/` y manifiestos con fecha, lote, conteo y checksum: no requieren otra imagen. Pausar y confirmar S3 antes de seguir o retirar el bucket; si lo requiere la siguiente fase, exportar datos y reconstruirlo o registrar retención y costo.

## 2. Red e IAM

La VPC aísla las bases y Redshift en subredes privadas; los grupos de seguridad permiten solo las conexiones necesarias desde EC2. IAM autoriza a EC2 y COPY sin claves estáticas de aplicación. Esto reduce exposición y privilegios frente a puertos locales publicados.

La captura histórica 2.1/3.1 está enlazada arriba. Por decisión del usuario IAM no requiere captura ni confirmación independiente. El rol COPY se crea con warehouse; conservar sus políticas y las ampliaciones de permisos de secretos como soporte textual, sin mostrar valores.

La comprobación EC2 3.1 comparte la captura histórica 2.1 enlazada en la matriz.

## 3. EC2 y Airflow

EC2 ejecuta Airflow y dbt juntos; Airflow ordena validación, extracción, carga, snapshots, modelos, pruebas y resultado. La mejora es poder identificar lote/tarea fallidos y reintentar de forma acotada sin intervención entre etapas. Las transformaciones SQL se ejecutan en Redshift, no en DuckDB ni en EC2.

Usar 3.1 para EC2 y su seguridad. Acceder mediante Systems Manager y túnel al puerto local de Airflow según [guía operativa](../../docs/guia-operacion.md). La UI del DAG y su ejecución exitosa se reúnen con dbt en 7.1: no pedir una imagen previa del DAG vacío ni otra de sus logs. Confirmar EC2 antes de continuar; confirmar Airflow cuando exista evidencia real de su funcionamiento. Terminar EC2 cuando deje de ser necesaria; detenerla no elimina el costo EBS.

## 4. RDS MySQL

RDS administra la fuente relacional y su almacenamiento cifrado. Mantiene las tablas clientes, productos, pedidos y líneas, conservando las reglas de negocio del origen y eliminando la dependencia de un contenedor MySQL local.

Reunir en 4.1 estado **Available**, motor MySQL, endpoint privado, cifrado y conexión TLS desde EC2. Guardar tablas/conteos en texto después de seed, sin imagen por tabla ni contraseñas de Secrets Manager; no exigir datos sembrados antes de confirmar disponibilidad. Esperar confirmación de RDS antes de continuar o eliminar recursos propios; el pipeline completo necesita esta fuente o una reconstrucción reproducible.

Las comprobaciones 4.1 y 5.1 comparten `04-fuentes/04-fuentes.png`: no se solicita una segunda imagen para DocumentDB.

## 5. DocumentDB

DocumentDB administra reseñas y eventos documentales. Conserva documentos anidados pero no equivale a MongoDB: se utiliza CA verificada, TLS y `retryWrites=false`, y las reglas de calidad se comprueban en dbt. La mejora es una fuente administrada privada, sin asumir compatibilidad total de validadores u operadores MongoDB.

Reunir en 5.1 cluster/instancia disponibles, cifrado, endpoint privado y conexión TLS válida desde EC2. Guardar colecciones/conteos después de seed y ajustes de compatibilidad observados en texto, sin información sensible ni imagen adicional. Confirmar DocumentDB antes de continuar; los volúmenes/backups pueden seguir facturándose incluso sin una instancia activa.

## 6. Redshift y dbt

Redshift sustituye DuckDB como almacén analítico; COPY ingiere exportaciones S3 mediante rol IAM. dbt adapta SQL al motor y separa raw, registros evaluados, cuarentena y marts. Snapshots conservan versiones SCD2 de clientes/productos y las pruebas verifican llaves y reglas.

Usar 6.1 para disponibilidad/configuración de Redshift y confirmar el servicio antes de continuar. Tras ejecutar el pipeline, guardar COPY/ledger, tablas por capa, SQL y resultados completos como texto; el resumen real de dbt comparte 7.1 con Airflow. No exigir una imagen para COPY, otra para capas y otra para dbt. Confirmar dbt con esa evidencia y Airflow con la misma imagen, sin duplicarla. Almacenamiento, snapshots y secretos pueden persistir al eliminar cómputo.

## 7. Escenarios de calidad y demostración

Guardar SQL/comandos y salida completa antes/después, lote técnico, fecha, estado de ledger y resultado para E1–E9. **No se exigen imágenes adicionales**: resultados reproducibles en `.sql`, `.json`, `.txt` o `.log` bastan para estos escenarios. Cada escenario tiene su propia pausa y confirmación de evidencia:

- Inicial: conteos de dimensiones y tres hechos.
- Calidad: registros concretos de cuarentena con motivo/lote y comparación válidos+rechazos.
- Repetición: mismos hechos, medidas e historial, sin duplicados.
- Incremental: nuevo lote fuente incorporado a ventas, reseñas y navegación.
- SCD2: cliente/producto antes y después, una versión previa cerrada y una vigente.
- Recuperación (E6/E7): fallo deliberado después de COPY y ledger no exitoso; guardar salida y **parar para confirmar E6 antes del replay**. Después guardar replay solo desde S3, resultado exitoso y comparación sin pérdida/duplicación; confirmar E7.
- Conciliación: indicador agregado de líneas válidas y `fct_sales` iguales, con SQL reproducible.
- Demostración (E9): nuevo lote completo desde fuentes hasta marts, identificando ejecución Airflow/CLI y explicación del ledger. Puede compartir resultados con E4/E5 si cumplen todos sus requisitos; no repetir un lote solo para producir otra captura.

La mejora es demostrar recuperación e integridad, no inferirlas por tener un DAG verde. No marcar capturada una fila cuyo comportamiento aún no haya sido ejecutado.

## 8. Costos, eliminación y publicación por fase

Consultar [costos](../../docs/costos.md) y [seguridad y limpieza](../../docs/guia-seguridad-costos-limpieza.md). Tras confirmar cada captura, retirar los recursos propios innecesarios según las dependencias del plan y conservar evidencia fuera de ellos. No desmontar antes de la confirmación; no borrar recursos ajenos. Registrar también estado vacío o residuos: versiones/delete markers S3, EBS, snapshots, backups, secretos y direcciones públicas.

Costos y eliminación se documentan con tarifas/supuestos, inventario y salidas saneadas del plan/aplicación e inventario posterior, **sin una sexta imagen obligatoria**. No capturar ni publicar planes binarios o estado con secretos. Confirmar la evidencia del servicio antes de autorizar su retiro y confirmar después el resultado real de eliminación/residuos antes de publicar esa fase; la segunda confirmación no sustituye la primera.

El usuario ya solicitó la publicación **después** de confirmar cada fase. En ese momento delegar el commit/push a **free-worker** sobre `feature/practica-merge`, con mensaje que destaque la fase, cambios específicos y evidencia confirmada; nunca incluir secretos ni cambios ajenos. Si la confirmación no existe, no publicar ni fingir que se obtuvo. No se ha realizado ningún push de esta migración.

Para cada evidencia confirmada registrar: ID, archivo real enlazado, cuenta/región, fecha, lote si aplica, qué demuestra, confirmación del usuario, recursos retirados/retenidos y commit de fase cuando exista. La ubicación de la captura 1.1 no fue indicada; la captura 2.1/3.1 está enlazada arriba y las fases posteriores están pendientes.
