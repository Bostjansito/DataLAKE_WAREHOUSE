# Preparación operacional de acceso (sin evidencia)

[Índice](../guia-operacion.md) · [Matriz de evidencias](../../evidencias/docEVIDENCIA/EVIDENCIAS.md)

Antes de crear recursos, desde la estación local ejecutar:

```bash
aws sts get-caller-identity
```

Comprobar perfil y región antes de cada operación. Si se utiliza la consola AWS, comparar la cuenta y usuario/rol activo con la identidad CLI; la sesión CLI no abre la consola. Se observó cuenta `241732001318`, `user/user_cli`; la cuenta histórica del Data Lake es distinta. Si no coinciden, detenerse y aclarar la identidad antes de operar. STS no demuestra permisos para desplegar. Preferir credenciales temporales y permisos de mínimo privilegio; no publicar tokens ni contraseñas.

Esta preparación **no es una fase de evidencia**: no requiere imagen ni confirmación del usuario. La primera captura prevista corresponde a **S3/Terraform (1.1)**. No confundir eliminar la captura de acceso con autorizar creación de recursos o gasto: el despliegue requiere autorización explícita.

En las fases de servicios siguientes detenerse tras cada servicio o escenario y esperar confirmación de su evidencia, usando las **5 imágenes mínimas** y los soportes textuales de la matriz. Los servicios creados juntos en runtime o fuentes comparten imagen, pero conservan confirmaciones por servicio antes de avanzar o retirar recursos. Solo después retirar recursos propios innecesarios respetando dependencias y publicar la fase conforme a las instrucciones del usuario. No eliminar recursos ajenos ni publicar evidencia sin confirmar.
