"""Línea de comandos del pipeline (la usan las pruebas locales y las tareas de Airflow).

Ejemplos:
  python -m noticias.cli extract                      # nueva extracción (run_id automático)
  python -m noticias.cli silver --run-id 20261105T010000Z
  python -m noticias.cli gold --run-id 20261105T010000Z
  python -m noticias.cli run                          # extract + silver + gold
  python -m noticias.cli silver --rebuild             # reconstruye Silver desde Bronze sin consultar RSS
  python -m noticias.cli gold --all
  python -m noticias.cli validate                     # reglas de calidad con Athena
  python -m noticias.cli controlled-copy --from-run 20261105T003325Z --source eltiempo_politica --mode defectuosos
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from .gold import run_gold
from .ingest import run_extraction
from .settings import load_settings, new_run_id, setup_logging
from .scenarios import MODES, controlled_copy
from .silver import run_silver
from .validate import run_validations

log = logging.getLogger("noticias.cli")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="noticias")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", help="Consulta los RSS y escribe en Bronze")
    p.add_argument("--run-id")
    p.add_argument("--source", action="append", help="Limita a una fuente (repetible)")

    p = sub.add_parser("silver", help="Procesa lotes de Bronze hacia Silver")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--run-id", action="append", help="Lote(s) de Bronze a procesar")
    g.add_argument("--rebuild", action="store_true", help="Reconstruye Silver desde todo Bronze")

    p = sub.add_parser("gold", help="Construye Gold")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--run-id", help="Usa las fechas afectadas por esa ejecución de Silver")
    g.add_argument("--date", action="append", help="Fecha(s) AAAA-MM-DD o 'sin_fecha'")
    g.add_argument("--all", action="store_true", help="Todas las fechas")

    p = sub.add_parser("run", help="extract + silver + gold")
    p.add_argument("--run-id")

    p = sub.add_parser("validate", help="Validaciones de calidad con Athena")
    p.add_argument("--run-id", default="manual")

    p = sub.add_parser("controlled-copy", help="Nuevo lote de Bronze a partir de una copia controlada")
    p.add_argument("--from-run", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--mode", choices=MODES, required=True)
    p.add_argument("--run-id")

    args = parser.parse_args(argv)
    setup_logging()
    settings = load_settings()

    if args.cmd == "extract":
        result = run_extraction(args.run_id or new_run_id(), settings, args.source)
    elif args.cmd == "silver":
        result = run_silver(settings, run_ids=args.run_id, rebuild=args.rebuild)
    elif args.cmd == "gold":
        if args.all:
            result = run_gold(settings, all_dates=True)
        elif args.date:
            result = run_gold(settings, dates=args.date)
        else:
            result = run_gold(settings, run_id=args.run_id)
    elif args.cmd == "validate":
        result = run_validations(settings, args.run_id)
    elif args.cmd == "controlled-copy":
        result = controlled_copy(settings, args.from_run, args.source, args.mode, args.run_id)
    else:
        run_id = args.run_id or new_run_id()
        extract = run_extraction(run_id, settings)
        if extract["status"] == "failed":
            print(json.dumps(extract, indent=2, ensure_ascii=False))
            return 2
        silver = run_silver(settings, run_ids=[run_id])
        gold = run_gold(settings, run_id=run_id)
        result = {"extract": extract, "silver": silver, "gold": gold}

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
