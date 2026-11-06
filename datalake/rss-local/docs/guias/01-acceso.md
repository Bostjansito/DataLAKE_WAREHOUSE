# 01 — Acceso y preparación

## Objetivo

Separar el aprendizaje local de la identidad AWS. Ningún paso de esta guía crea recursos. No comparta secretos ni los escriba en `.env` versionado.

## Ruta local

1. Instale Python y herramientas indicadas por `pyproject.toml`; si la ruta de orquestación local requiere Docker, use la configuración Compose del repositorio.
2. Revise archivos de configuración y ejemplos para conocer nombres de variables. Use valores locales no sensibles y almacene el lake debajo de un directorio de trabajo ignorado por Git.
3. Siga `docs/guias/02-pipeline-local.md` para ejecución reproducible.

## Ruta AWS: solo comprobar identidad

1. Configure AWS CLI con un perfil autenticado siguiendo la documentación oficial de [AWS CLI, configuración de perfiles](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html). Use SSO o mecanismo institucional seguro cuando corresponda; no pegue claves en comandos o capturas.
2. Compruebe perfil y región activos con `aws configure list --profile NOMBRE` y `aws sts get-caller-identity --profile NOMBRE`. El resultado confirma identidad/cuenta, no permisos suficientes para desplegar ni ausencia de costo.
3. Seleccione explícitamente región coherente para todos los recursos; Comprehend y límites de servicio varían por región.

4. Para el MCP, valide que el cliente configurado pueda inicializar y enumerar herramientas. La verificación indicada para esta actividad ya tuvo éxito; no se debe reportar MCP ausente. Esto tampoco implica autorización para escribir en AWS.
5. No ejecute `terraform apply`, consultas Athena facturables ni llamadas Comprehend hasta revisar la guía correspondiente y contar con autorización explícita.
Para ejecutar el pipeline local contra AWS, la identidad AWS efectiva necesita permisos del lake. Después del primer despliegue Terraform, revise el output `pipeline_policy_arn` y coordine con el administrador para conceder esa política a un rol de ejecución existente autorizado; no use la cuenta root ni adjunte permisos amplios de forma manual. EC2 recibe la política del pipeline y el permiso de Systems Manager mediante el instance profile cuando se habilita. Una identidad que solo pasa `sts get-caller-identity` puede no tener permisos de S3, Glue, Athena o Comprehend.

## Captura de identidad

Con la autorización del docente, capture solo la pantalla de identidad con cuenta/ARN parcialmente ocultos y región. No incluya credenciales, tokens, valores de entorno o salida de configuración sensible. La comprobación inicial de identidad ya se realizó, pero esta captura de consola queda pendiente de la ejecución guiada.

## Referencias

- [AWS CLI: configuración](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html)
- [STS GetCallerIdentity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html)
