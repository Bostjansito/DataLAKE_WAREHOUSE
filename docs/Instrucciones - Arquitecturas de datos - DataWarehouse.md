
Todo lo presente en este taller que se pueda realizar con terraform se debe hacer con esta herramienta. Además, se debe indicar al usuario qué debe hacer con AWS y con terraform en un md guia por cada sección específica.

Durante el curso construimos el flujo de un data warehouse ejecutado localmente a partir del
repositorio DE-DW (Dirigirse al repositorio local por este mismo nombre, reportar si lo encuentras o no)

El siguiente reto consiste en migrar esta solución a AWS, conservando sus reglas de negocio
y garantizando que el procesamiento sea reproducible, verificable y seguro.

La solución debe integrar fuentes relacionales y documentales, construir un data warehouse
en Amazon Redshift.

# 1. Objetivo
- Implementar y demostrar un pipeline de datos de extremo a extremo en AWS que permita:
	- Extraer información desde Amazon RDS y Amazon DocumentDB.
	- Conservar los datos extraídos en Amazon S3.
	- Cargar y transformar los datos en Amazon Redshift.
	- Ejecutar Apache Airflow y dbt en una instancia Amazon EC2.
	- Verificar calidad, cargas incrementales, idempotencia e historia de cambios.
# 2. Arquitectura
![[Pasted image 20261020070217.png]]
# 3. Requisitos funcionales
## 3.1. Fuentes de datos
1. Migrar la fuente MySQL local a Amazon RDS for MySQL.
2. Migrar MongoDB local a Amazon DocumentDB.
3. Adaptar los scripts de generación y conexión.
4. Se pueden seguir usando los mis datos que se emplearon en local
5. Documentar los ajustes necesarios por diferencias entre MongoDB y DocumentDB.
## 3.2. Extracción y almacenamiento en S3
Implementar una extracción inicial y una extracción incremental por lote.
Cada extracción debe:

- Escribir los datos en un bucket S3 privado.
- Identificar la fuente, entidad y lote en la ruta de los objetos.
- Registrar fecha de extracción, identificador del lote y cantidad de registros.
- Conservar los archivos necesarios para reprocesar un lote sin consultar nuevamente las fuentes.
- Evitar sobrescribir silenciosamente los datos de otros lotes.
Ejemplo de organización:
`s3://<bucket>/raw/<fuente>/<entidad>/batch_id=<id>/`

Se permite utilizar CSV, JSON o Parquet, justificando la elección y su compatibilidad con la carga a Redshift.
## 3.3. Data warehouse en Redshift
Sustituir DuckDB por Amazon Redshift.

Se permite utilizar Redshift Serverless o un clúster aprovisionado, según los recursos disponibles en la cuenta del curso.

La implementación debe:
1. Cargar los archivos desde S3 mediante COPY.
2. Utilizar un rol IAM para autorizar el acceso de Redshift a S3.
3. Mantener las responsabilidades de las capas raw, intermediate, quarantine y marts.
4. Conservar el modelo dimensional y los procesos de negocio del proyecto.
5. Implementar historia de cambios SCD tipo 2.
6. Adaptar tipos de datos, funciones SQL y configuraciones de dbt a Redshift.
7. Registrar los rechazos junto con su motivo y lote de origen.

## 3.4. Orquestación con Airflow
Construir o adaptar un DAG que coordine:
1. Validación de conexiones y parámetros.
2. Extracción de las fuentes.
3. Escritura de archivos en S3.
4. Carga a Redshift.
5. Transformaciones y snapshots de dbt.
6. Pruebas de calidad.
7. Registro del resultado del procesamiento.

Airflow y dbt deben ejecutarse en la misma instancia EC2. Las transformaciones SQL enviadas por dbt deben ejecutarse en Redshift.
El flujo debe incluir dependencias explícitas, reintentos acotados y logs que permitan identificar el lote y la tarea que fallaron.
El pipeline debe poder ejecutarse desde Airflow sin intervención manual entre etapas.

## 3.5. Calidad, incrementalidad y recuperación
Presentar evidencia de los siguientes escenarios:

| Escenario                         | Resultado esperado                                |
| --------------------------------- | ------------------------------------------------- |
| Carga inicial                     | Datos disponibles en los modelos analíticos       |
| Registros defectuosos             | Rechazos identificados y trazables                |
| Repetición de un lote exitoso     | Sin duplicación de hechos ni versiones históricas |
| Nuevo lote incremental            | Incorporación correcta de nuevos registros        |
| Cambio en un atributo historizado | Nueva versión SCD tipo 2 y cierre de la anterior  |
| Fallo controlado y reejecución    | Recuperación sin pérdida ni duplicación           |
Incluir pruebas de unicidad, campos obligatorios, relaciones y reglas de negocio. Conciliar al menos un indicador agregado entre los datos válidos de origen y el modelo analítico.

Documentar cómo se identifica un lote procesado y en qué momento se actualiza su estado o marca de avance.
# 4. Entregables
1. Repositorio de código
	- DAGs de Airflow y scripts de extracción y carga.
	-  Proyecto dbt adaptado a Redshift.
	-  Configuración de despliegue sin secretos.
	-  Archivo de ejemplo con las variables requeridas.
2. Documentación
	-  Diagrama de arquitectura.
	-  Instrucciones reproducibles de despliegue, ejecución y eliminación de recursos
	- Decisiones técnicas y diferencias frente a la versión local.
	-  Estimación de costos y controles de seguridad implementados.
3. Evidencias de funcionamiento
	-  Ejecución exitosa del pipeline en Airflow.
	-  Resultados de las pruebas de dbt.
	-  Validación de carga inicial, calidad, incrementalidad, idempotencia, SCD tipo 2 y recuperación ante fallos.
4. Demostración
	-  Procesar un nuevo lote desde las fuentes hasta los marts en Redshift.
	-  Explicar cómo se identifica y recupera una ejecución fallida.

Las capturas complementan la entrega, pero no sustituyen el código ni las instrucciones reproducibles.