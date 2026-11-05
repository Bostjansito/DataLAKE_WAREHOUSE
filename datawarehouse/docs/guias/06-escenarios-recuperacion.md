# 06 · Escenarios, calidad y recuperación

[Índice](../guia-operacion.md) · [Matriz de capturas](../../evidencias/docEVIDENCIA/EVIDENCIAS.md)

Las siguientes instrucciones son una secuencia propuesta, no resultados observados. Usar la sesión EC2 y wrapper de [fuentes](02-fuentes-generadores.md); ejecutar una sola carga a la vez. Registrar lote, fecha, SQL/comandos y salidas completas antes/después en archivos textuales reproducibles. **Los escenarios E1–E9 no exigen imágenes adicionales** a las cinco de la matriz. Tras **cada escenario**, detenerse y esperar confirmación de su evidencia antes de continuar; posteriormente retirar solo recursos propios innecesarios sin romper dependencias. Los agentes no publican.

1. **Inicial y calidad:** ejecutar seed una sola vez y `pipeline --batch-id 0` según [03](03-extraccion-replay.md). Consultar ledger y conteos de dimensiones y tres hechos; ejecutar los SQL de [04](04-redshift-dbt.md) para rechazos con motivo y lote, conciliación y SCD2. Guardar salida de dbt test. Sembrar defectuosos no demuestra por sí solo los rechazos.
2. **Repetición exitosa (E3):** guardar conteos, sumas de ventas y versiones; repetir `pipeline --batch-id 0 --replay` y comparar. El código retorna al encontrar `succeeded`: no consulta fuentes ni modifica warehouse. Guardar también logs y ledger como texto y confirmar el resultado.
3. **Incremental y SCD2:** consultar valores actuales y versiones de cliente 1 y producto 1; ejecutar `append --batch-id 1` y `simulate-changes` con valores diferentes y fecha posterior al valor previo como en [02](02-fuentes-generadores.md), ambos antes de `pipeline --batch-id 1`. Comparar hechos, medidas e historia. Por ejemplo en Redshift:

```sql
select customer_id, city, department, valid_from, valid_to, is_current
from marts.dim_customer where customer_id = 1 order by valid_from;
select product_id, category, valid_from, valid_to, is_current
from marts.dim_product where product_id = 1 order by valid_from;
```

Confirmar una versión previa cerrada y otra vigente para los atributos efectivamente cambiados, y los tres hechos incrementados; no inferir éxito si la consulta no lo muestra.
4. **Fallo y recuperación:** preparar otro lote nuevo con append y ejecutar desde EC2:

```bash
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli append --batch-id 2
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli pipeline --batch-id 2 --fail-after-load
```

El fallo deliberado ocurre después de COPY atómico y deja `pending`, antes de dbt. Guardar fallo y ledger en texto y **parar para confirmar E6 antes de recuperar**, sin exigir imagen nueva. Después ejecutar:

```bash
sudo -u ecommerce /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/runtime/bin/python -m aws_dw.cli pipeline --batch-id 2 --replay
```

Replay lee manifiestos y payloads S3 sin acceso a fuentes, termina dbt y pruebas y marca `succeeded` solo si todo pasa. Comparar conteos, sumas e historia antes/después y guardar resultados textuales; pausar para confirmar E7. Un `pending` bloquea cargar otro lote; resolverlo primero. Si falta un manifiesto o falla una prueba, conservar los logs, corregir la causa y no marcar el escenario exitoso.

5. **Conciliación y demostración (E8/E9):** ejecutar la primera consulta completa de [02_business_reconciliation.sql](../../sql/02_business_reconciliation.sql): unidades e importe válidos por fecha contra `fct_sales`, sin diferencias esperadas. Guardar y confirmar E8. La demostración debe procesar un lote nuevo desde fuentes hasta marts; puede ser el mismo de incremental/SCD2 (E4/E5) si se conservan sus resultados completos y se confirma cada requisito, sin ejecutar otro lote solo para obtener otra imagen. Conservar explicación del ledger y confirmar E9. La [matriz](../../evidencias/docEVIDENCIA/EVIDENCIAS.md) especifica las cinco imágenes y los soportes textuales.

El ledger es la marca de avance: `pending` se registra con COPY; `succeeded` solo después de snapshots, modelos y tests. No hay que borrar manualmente esa fila para reintentar ni volver a consultar fuentes para recuperar un lote capturado.
