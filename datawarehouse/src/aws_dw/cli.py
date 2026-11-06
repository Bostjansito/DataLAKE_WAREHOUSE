"""CLI for immutable DE-DW batches and ordered Redshift/dbt processing."""
import argparse
import fcntl
import json
import logging
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

LOGGER = logging.getLogger(__name__)
PROJECT = Path(__file__).resolve().parents[2] / "dbt"


@contextmanager
def pipeline_lock():
    # Airflow and CLI share the EC2 host. Hold across dbt, not just COPY.
    path = Path(os.getenv("DW_LOCK_PATH", "/tmp/ecommerce_dw_pipeline.lock"))
    with path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def setup(replay=False):
    from aws_dw.extraction.extractor import get_mysql_connection, get_mongo_client, s3_client
    from aws_dw.load.loader import _connect_redshift
    required = ["AWS_REGION", "S3_BUCKET", "REDSHIFT_HOST", "REDSHIFT_DATABASE",
                "REDSHIFT_USER", "REDSHIFT_PASSWORD", "REDSHIFT_COPY_ROLE_ARN"]
    if not replay:
        required += ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE", "MONGO_URI", "MONGO_DATABASE"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ValueError(f"Missing environment variables: {', '.join(missing)}")
    s3_client().head_bucket(Bucket=os.environ["S3_BUCKET"])
    conn = _connect_redshift()
    conn.close()
    if not replay:
        conn = get_mysql_connection()
        conn.close()
        client = get_mongo_client()
        try:
            client.admin.command("ping")
        finally:
            client.close()


def extract(batch_id):
    from aws_dw.extraction.extractor import extract_mysql_to_s3, extract_mongo_to_s3
    return {"batch_id": batch_id, "mysql": extract_mysql_to_s3(batch_id),
            "mongodb": extract_mongo_to_s3(batch_id)}


def run_dbt(batch_id, project_dir):
    from aws_dw.load.loader import batch_status, mark_batch_succeeded
    state = batch_status(batch_id)
    if state == "succeeded":
        LOGGER.info("Batch %s already succeeded; skipping dbt and SCD2 snapshots", batch_id)
        return
    if state != "pending":
        raise RuntimeError("Load the batch from S3 before running dbt")
    project = str(Path(project_dir).resolve())
    common = ["--project-dir", project, "--profiles-dir", project,
              "--vars", json.dumps({"batch_id": batch_id})]
    commands = [["deps"], ["seed"], ["run", "--select", "intermediate", "quarantine"],
                ["snapshot"], ["run", "--select", "marts"], ["test"]]
    for command in commands:
        LOGGER.info("Batch %s dbt stage %s", batch_id, " ".join(command))
        subprocess.run([os.getenv("DBT_BIN", "dbt"), *command, *common], check=True)
    mark_batch_succeeded(batch_id)


def pipeline(batch_id, project_dir, replay=False, fail_after_load=False):
    from aws_dw.extraction.extractor import validate_batch_id
    from aws_dw.load.loader import batch_status, load_batch
    batch_id = validate_batch_id(batch_id)
    with pipeline_lock():
        state = batch_status(batch_id)
        if state == "succeeded":
            LOGGER.info("Batch %s already succeeded; no source access or warehouse mutations", batch_id)
            return
        # Pending recovery never recontacts sources, even without --replay.
        setup(replay=replay or state == "pending")
        if not replay and state is None:
            extract(batch_id)
        load_batch(batch_id)
        if fail_after_load:
            raise RuntimeError(f"Controlled failure after atomic COPY for batch {batch_id}; rerun with --replay without --fail-after-load")
        run_dbt(batch_id, project_dir)


def _source(args):
    if args.command == "seed":
        from ecommerce_dw.sources.generate_data import main
    elif args.command == "append":
        from ecommerce_dw.sources.append_batch import main
    else:
        from ecommerce_dw.sources.simulate_changes import main
    main(args.source_args)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup_parser = commands.add_parser("setup", help="Validate TLS connections")
    setup_parser.add_argument("--replay", action="store_true", help="Do not validate source connections")
    for name in ("seed", "append", "simulate-changes"):
        source = commands.add_parser(name, help="Forward DE-DW generator options unchanged", add_help=False)
        source.add_argument("source_args", nargs=argparse.REMAINDER)
    for name in ("extract", "load", "run", "pipeline", "scenario"):
        command = commands.add_parser(name)
        command.add_argument("--batch-id", required=True)
        if name in ("run", "pipeline", "scenario"):
            command.add_argument("--dbt-project-dir", default=os.getenv("DBT_PROJECT_DIR", str(PROJECT)))
        if name in ("pipeline", "scenario"):
            command.add_argument("--replay", action="store_true")
            command.add_argument("--fail-after-load", action="store_true")
        if name == "scenario":
            command.add_argument("--scenario", required=True, choices=["initial", "incremental", "replay", "recovery"])
    return parser


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = build_parser()
    # Source parsers own their exact options, including --help and validation.
    import sys
    tokens = list(sys.argv[1:] if argv is None else argv)
    if tokens and tokens[0] in ("seed", "append", "simulate-changes"):
        _source(argparse.Namespace(command=tokens[0], source_args=tokens[1:]))
        return 0
    args = parser.parse_args(tokens)
    from aws_dw.extraction.extractor import validate_batch_id
    if hasattr(args, "batch_id"):
        args.batch_id = validate_batch_id(args.batch_id)
    if args.command == "setup":
        setup(args.replay)
    elif args.command == "extract":
        print(json.dumps(extract(args.batch_id), indent=2))
    elif args.command == "load":
        from aws_dw.load.loader import load_batch
        with pipeline_lock():
            load_batch(args.batch_id)
    elif args.command == "run":
        with pipeline_lock():
            run_dbt(args.batch_id, args.dbt_project_dir)
    elif args.command in ("pipeline", "scenario"):
        replay = args.replay
        if args.command == "scenario":
            if args.scenario == "initial" and args.batch_id != "0":
                parser.error("initial scenario requires --batch-id 0")
            if args.scenario == "incremental" and args.batch_id == "0":
                parser.error("incremental scenario requires --batch-id 1..365")
            replay = replay or args.scenario in ("replay", "recovery")
        pipeline(args.batch_id, args.dbt_project_dir, replay, args.fail_after_load)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
