# Runtime — 2026-11-05

## Estado real y pausa

Cuenta **241732001318**, región **us-east-1**, operador `user_cli`. Plan revisado: **31 altas, 0 cambios y 0 eliminaciones**; aplicación completada con esos recuentos. Flags locales persistidos: compute=true, sources=false, warehouse=false. El inventario previo no encontró VPC, instancias ni buckets en la consulta realizada. No se importaron ni modificaron recursos preexistentes. No se crearon RDS, DocumentDB, Redshift ni secretos.

**Captura 2.1/3.1 pendiente; VPC, IAM/EC2 y EC2 pendientes de confirmación individual.** No existe todavía `03-runtime.png`. No hubo retiro, commit ni push. Esperar confirmación explícita de cada servicio antes de otra fase o eliminación. Después de la confirmación del usuario, delegar publicación a free-worker; si se solicita retiro, confirmar también su resultado antes de publicar.

## Recursos activos

- Bucket reconstruido: `dw-raw-55ce297c189637c0`, privado, AES256, versionado y política de denegación HTTP. No es el bucket retirado de 1.1.
- VPC: `vpc-0b26389992211d765`, CIDR `10.0.0.0/16`.
- Públicas: `subnet-0505e3af9cb6db4b0`, `subnet-0e085ab641a9bf8d5`, `subnet-0d890fda134eb492a`.
- Privadas: `subnet-08eb03bf0bd727607`, `subnet-03e34bdd6351f3cb6`, `subnet-079aad653c15f3796`; tres AZ, sin salida Internet por NAT.
- IGW `igw-0544d5f90f3101929`; rutas pública `rtb-03fb9041e248b7fb9` y privada `rtb-0aaddcc042e8870f9`; endpoint Gateway S3 `vpce-068864eb7465da3ff` asociado a ambas. Sin NAT ni endpoints Interface en esta VPC.
- EC2 `dw-airflow-dbt`: **`i-0b65cd081428de5fc`**, t3.medium, Amazon Linux 2023, us-east-1a, IPv4 pública `34.232.105.8`, privada `10.0.9.121`; running, comprobaciones sistema/instancia/EBS pasadas.
- SG `sg-072229ab7f21921c8`: sin reglas entrantes. IMDSv2 requerido, EBS gp3 cifrado de 30 GiB, créditos CPU standard.
- Rol `dw-ec2-20261105180243023500000001`; perfil `dw-ec2-20261105180243857800000002`. Confianza EC2, AmazonSSMManagedInstanceCore y política S3 limitada al bucket propio. Sin permisos de secretos en esta fase.

## Pruebas y limitación exacta

[inventario-runtime.json](inventario-runtime.json) conserva red, IAM, EC2, SSM y seguridad S3. [estado-ec2-final.json](estado-ec2-final.json) confirma checks `ok`. [verificacion-final.json](verificacion-final.json), comando SSM `2692d4e1-58e4-4f78-8233-dcecd4db5597`, terminó **Success/0**: Python 3.11.18, agente SSM activo, CA presentes, STS con el rol real de la instancia y ListObjectsV2 exitoso contra el bucket propio. SSM estaba Online. No se probó sesión interactiva ni escritura S3.

El bootstrap inicial falló: `dnf install curl` colisionó con `curl-minimal` preinstalado. Se conservan diagnóstico y fallo original; la plantilla se corrigió a `curl-minimal` y se ejecutó el bootstrap corregido sobre la misma instancia vía SSM, con éxito (comando `0ba49ad1-e320-4a31-8273-596f606f62be`). No se reemplazó EC2 ni se ocultó el error histórico de cloud-init.

**Limitación pendiente antes del despliegue de aplicaciones:** cloud-init conserva estado histórico `error`; `remote-deploy.sh` actualmente espera `cloud-init status --wait`, por lo que bloqueará el despliegue posterior. Además, la plantilla corregida difiere del user data original: `user_data_replace_on_change=true` implica que un futuro plan puede proponer reemplazo. No aplicar ese plan sin revisión y confirmación explícita; no retirar la instancia antes de confirmar evidencia. Airflow/dbt y el pipeline no se instalaron ni se ejecutaron en esta fase.

## Una sola captura mínima, real y legible

Guardar la imagen real como `datawarehouse/evidencias/02-runtime/03-runtime.png`. Usar tres terminales simultáneas; ejecutar consultas AWS reales, no dibujar paneles ni capturar únicamente este README. Ajustar fuente hasta poder leer IDs, cuenta/región y estados; no incluir state, planes binarios ni credenciales. La consola AWS también puede servir para EC2, pero no es necesario multiplicar imágenes.

Cabecera compartida:

```bash
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
aws sts get-caller-identity --query '{Account:Account,Arn:Arn}'
```

Panel red (2.1):

```bash
aws ec2 describe-subnets --filters Name=vpc-id,Values=vpc-0b26389992211d765 --query 'Subnets[].{VPC:VpcId,Subnet:SubnetId,AZ:AvailabilityZone,CIDR:CidrBlock}' --output table
aws ec2 describe-route-tables --filters Name=vpc-id,Values=vpc-0b26389992211d765 --query 'RouteTables[].{ID:RouteTableId,Routes:Routes}' --output json
aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=vpc-0b26389992211d765 --query 'VpcEndpoints[].{ID:VpcEndpointId,Type:VpcEndpointType,Service:ServiceName,State:State}' --output table
```

Panel IAM (2.1):

```bash
aws iam get-role --role-name dw-ec2-20261105180243023500000001 --query 'Role.{Name:RoleName,Trust:AssumeRolePolicyDocument}'
aws iam get-role-policy --role-name dw-ec2-20261105180243023500000001 --policy-name terraform-20261105180245599000000004 --query PolicyDocument
aws iam list-attached-role-policies --role-name dw-ec2-20261105180243023500000001 --output table
```

Panel EC2 (3.1):

```bash
aws ec2 describe-instances --instance-ids i-0b65cd081428de5fc --query 'Reservations[].Instances[].{ID:InstanceId,State:State.Name,Type:InstanceType,IMDS:MetadataOptions.HttpTokens,Profile:IamInstanceProfile.Arn,SG:SecurityGroups[].GroupId}'
aws ec2 describe-instance-status --instance-ids i-0b65cd081428de5fc --query 'InstanceStatuses[].{System:SystemStatus.Status,Instance:InstanceStatus.Status,EBS:AttachedEbsStatus.Status}' --output table
aws ec2 describe-volumes --filters Name=attachment.instance-id,Values=i-0b65cd081428de5fc --query 'Volumes[].{ID:VolumeId,GiB:Size,Type:VolumeType,Encrypted:Encrypted}' --output table
aws ec2 describe-security-groups --group-ids sg-072229ab7f21921c8 --query 'SecurityGroups[].{ID:GroupId,Ingress:IpPermissions}'
```

Las políticas/inventarios completos y SSM se conservan en texto, no necesitan imágenes adicionales. Si las rutas completas impiden legibilidad, mostrar en pantalla solo las rutas a IGW y S3; conservar JSON completo como soporte. Pedir: **«Confirma VPC, IAM/EC2 y EC2 de la captura 2.1/3.1»**, sin atribuir una confirmación no recibida.

## Costos activos, no factura

Tarifas públicas consultadas el 2026-11-05 para us-east-1, sin impuestos, descuentos ni créditos:

- t3.medium Linux On Demand: **USD 0.0416/h**, recuperado de AWS Pricing API; soporte [tarifa-ec2.json](tarifa-ec2.json), [fuente EC2](https://aws.amazon.com/ec2/pricing/on-demand/).
- EBS gp3: **USD 0.08/GB-mes**; 30 GiB = **USD 2.40/mes**, soporte [tarifa-ebs.json](tarifa-ebs.json), [fuente EBS](https://aws.amazon.com/ebs/pricing/).
- Una IPv4 pública: **USD 0.005/h**, [fuente VPC](https://aws.amazon.com/vpc/pricing/). Gateway S3 sin cargo por hora/procesamiento; no se provisionaron NAT/Interface.
- Proyección aritmética a 730 h: EC2 USD 30.368 + IPv4 USD 3.65 + disco USD 2.40 = **USD 36.418/mes**, aproximadamente **USD 0.04989/h** incluyendo prorrateo del disco. No es gasto observado ni techo presupuestario.
- S3 cobra requests, almacenamiento/versiones y transferencias aplicables según [tarifas S3](https://aws.amazon.com/s3/pricing/); no se asume gratuidad. IAM sin cargo directo. Detener EC2 conserva EBS; no detener, destruir ni vaciar recursos sin confirmación/autorización correspondiente.
