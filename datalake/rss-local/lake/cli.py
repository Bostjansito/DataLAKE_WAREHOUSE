"""CLI shared by local users and Airflow tasks; never provisions infrastructure."""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from .core import Pipeline, DisabledEnricher, ComprehendEnricher
from .storage import LocalStore, S3Store, read_json, write_json

STAGES = ("ingest", "transform", "enrich", "publish_silver", "build_gold", "validate")


def runtime(args):
    feeds = json.loads(Path(args.feeds).read_text(encoding="utf-8"))
    store = S3Store(args.bucket, args.region) if args.bucket else LocalStore(args.root)
    enricher = ComprehendEnricher(args.region) if args.enrichment == "comprehend" else DisabledEnricher()
    return Pipeline(store, feeds, enricher)


def run_stage(pipeline, stage, run_id, *, fixture_dir=None, replay=False):
    logging.info("run_id=%s task=%s", run_id, stage)
    if stage == "ingest":
        if replay:
            result = read_json(pipeline.store, f"_control/runs/{run_id}/ingest.json")
        else:
            fetcher = None
            if fixture_dir:
                def fetcher(feed):
                    return 200, (Path(fixture_dir) / f"{feed['source']}.xml").read_bytes()
            result = pipeline.ingest(run_id, fetcher)
        for source in result["sources"]:
            logging.info("run_id=%s source=%s status=%s", run_id, source["source"], source["status"])
        if result["status"] == "failed":
            raise ValueError("Todas las fuentes fallaron; consulte el manifiesto de ingesta")
        return result
    return getattr(pipeline, stage)(run_id)


def parser():
    p = argparse.ArgumentParser(description="Lake RSS: local sin costos o AWS explícito")
    p.add_argument("command", choices=["run", *STAGES, "check", "catalog", "athena", "status"])
    p.add_argument("--run-id", default="local-demo")
    p.add_argument("--feeds", default=os.getenv("LAKE_FEEDS", "config/feeds.json"))
    p.add_argument("--root", default=os.getenv("LAKE_ROOT", ".local-lake"))
    p.add_argument("--bucket", default=os.getenv("LAKE_BUCKET"))
    p.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    p.add_argument("--enrichment", choices=["disabled", "comprehend"], default=os.getenv("LAKE_ENRICHMENT", "disabled"))
    p.add_argument("--database", default=os.getenv("GLUE_DATABASE", "rss_lake"))
    p.add_argument("--workgroup", default=os.getenv("ATHENA_WORKGROUP", "rss-lake"))
    p.add_argument("--fixture-dir", help="XML controlado <source>.xml; no consulta red")
    p.add_argument("--replay", action="store_true", help="Exige lote Bronze existente; nunca vuelve a consultar RSS")
    p.add_argument("--fail-after", choices=STAGES, help="Fallo de demostración después del checkpoint indicado")
    p.add_argument("--from-bronze", help="Reconstruye en run-id nuevo usando Bronze del lote indicado, sin copiar XML ni HTTP")
    return p


def execute(args):
    pipeline = runtime(args)
    if args.from_bronze:
        if args.command not in {"run", "ingest"} or args.from_bronze == args.run_id:
            raise ValueError("--from-bronze requiere run o ingest y un run-id nuevo distinto")
        target = pipeline._key(args.run_id, "ingest")
        if not pipeline.store.exists(target):
            original = read_json(pipeline.store, pipeline._key(args.from_bronze, "ingest"))
            source_start = read_json(pipeline.store, pipeline._key(args.from_bronze, "start"))
            parent = read_json(pipeline.store, "_control/current.json") if pipeline.store.exists("_control/current.json") else None
            start = dict(source_start, parent=parent, replay_of=args.from_bronze)
            ingestion = dict(original, run_id=args.run_id, replay_of=args.from_bronze,
                             parent_run_id=parent["run_id"] if parent else None)
            write_json(pipeline.store, pipeline._key(args.run_id, "start"), start)
            write_json(pipeline.store, target, ingestion)
        elif read_json(pipeline.store, target).get("replay_of") != args.from_bronze:
            raise ValueError("run-id ocupado por otra ingesta; use un identificador nuevo")
        args.replay = True
    if args.command == "check":
        if args.bucket:
            from .catalog import clients
            glue, athena = clients(args.region)
            pipeline.store.client.get_bucket_location(Bucket=args.bucket)
            glue.get_database(Name=args.database)
            athena.get_work_group(WorkGroup=args.workgroup)
            if args.enrichment == "comprehend":
                # Authorization is ultimately checked by detect_* at execution; no paid probe.
                logging.info("Comprehend configurado; no se realiza análisis facturable de prueba")
        return {"configuration": "valid", "storage": pipeline.store.uri("_control/"), "sources": len(pipeline.feeds)}
    if args.command == "status":
        return read_json(pipeline.store, "_control/current.json")
    if args.command in {"catalog", "athena"}:
        if not args.bucket:
            raise ValueError("Glue/Athena requieren --bucket; no existen resultados AWS locales")
        from .catalog import clients, register_snapshot, validate_athena
        from .core import committed_manifest
        manifest = read_json(pipeline.store, "_control/current.json")
        if manifest["run_id"] != args.run_id:
            if committed_manifest(pipeline.store, args.run_id) is not None:
                return {"status": "skipped_historical_replay", "requested_run_id": args.run_id,
                        "current_run_id": manifest["run_id"], "stage": args.command}
            raise ValueError("run-id no corresponde a un snapshot publicado")
        glue, athena = clients(args.region)
        return (register_snapshot(pipeline.store, manifest, args.database, glue) if args.command == "catalog"
                else validate_athena(pipeline.store, manifest, args.database, args.workgroup, athena))
    stages = STAGES if args.command == "run" else (args.command,)
    result = None
    for stage in stages:
        result = run_stage(pipeline, stage, args.run_id, fixture_dir=args.fixture_dir, replay=args.replay)
        if stage == args.fail_after:
            raise RuntimeError(f"Fallo controlado después de {stage}; reejecute el mismo run-id sin --fail-after")
    return result


def main():
    args = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = execute(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
