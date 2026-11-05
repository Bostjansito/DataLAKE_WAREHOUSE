#!/usr/bin/env bash
# Escenarios 11.3 a 11.7 en secuencia (cada uno es una ejecución del DAG en Airflow).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
S=datalake/scripts/escenario.sh
BUCKET=datalake-noticias-387512138242-us-east-1

# Último lote extraído de Política (el más reciente evita revertir ediciones reales del medio).
LAST=$(aws s3 ls "s3://$BUCKET/bronze/source=eltiempo_politica/" --recursive | grep _manifest.json \
  | grep -o 'run_id=[0-9TZ]*' | sed 's/run_id=//' | sort | tail -1)
echo "Último lote de Política: $LAST"

# 11.3 Repetición de un lote exitoso: mismo lote de Bronze otra vez.
$S 03-repeticion-lote "{\"bronze_run_id\": \"$LAST\"}"

# 11.5 Noticia con contenido modificado (copia controlada del último lote).
datalake/scripts/run_local.sh controlled-copy --from-run "$LAST" --source eltiempo_politica --mode modificado \
  2>&1 | tee datalake/evidencias/09-escenarios/05-copia-controlada-modificado.log
MOD=$(grep -o '"run_id": "[0-9TZ]*"' datalake/evidencias/09-escenarios/05-copia-controlada-modificado.log | head -1 | grep -o '[0-9]\{8\}T[0-9]\{6\}Z')
$S 05-contenido-modificado "{\"bronze_run_id\": \"$MOD\"}"

# 11.6 Fallo controlado y reejecución: publicar_silver falla en el 1er intento, el reintento recupera.
$S 06a-fallo-controlado-reintento '{"simular_fallo": true}'
# 11.6 Fuente no disponible: ejecución parcial, no "sin noticias".
$S 06b-fuente-no-disponible '{"fuente_caida": "eltiempo_deportes"}'

# 11.7 Reprocesamiento completo desde Bronze sin consultar RSS.
$S 07-reprocesamiento-bronze '{"rebuild": true}'
echo "== escenarios terminados"
