"""Sequential single-writer lab DAG. Enable schedule explicitly with LAKE_SCHEDULE."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.python import PythonOperator

from lake.cli import execute, parser
from lake.storage import write_json


def task_run(stage, **context):
    params = context["params"]
    # Airflow generated IDs contain '+', not accepted as object checkpoint IDs.
    import hashlib
    batch = params["batch_id"] or hashlib.sha256(context["run_id"].encode()).hexdigest()[:24]
    argv = [stage, "--run-id", batch]
    if params["replay"]:
        if not params["batch_id"]:
            raise ValueError("Reproceso requiere batch_id explícito existente")
        argv += ["--replay"]
    if stage == "ingest" and params["from_bronze"]:
        if not params["batch_id"]:
            raise ValueError("Reconstrucción requiere batch_id nuevo explícito")
        argv += ["--from-bronze", params["from_bronze"]]
    if params["fail_after"] and stage == params["fail_after"]:
        argv += ["--fail-after", stage]
    return execute(parser().parse_args(argv))


def record_state(**context):
    from lake.cli import runtime
    import hashlib
    from airflow.exceptions import AirflowException
    batch = context["params"]["batch_id"] or hashlib.sha256(context["run_id"].encode()).hexdigest()[:24]
    pipeline = runtime(parser().parse_args(["status", "--run-id", batch]))
    failures = {ti.task_id: str(ti.state) for ti in context["dag_run"].get_task_instances()
                if ti.task_id != "record_state" and str(ti.state) != "success"}
    from lake.storage import read_json
    key = f"_control/runs/{batch}/ingest.json"
    ingestion = read_json(pipeline.store, key) if pipeline.store.exists(key) else {}
    result = {"run_id": batch, "airflow_run_id": context["run_id"],
              "status": "failed" if failures else ingestion.get("status", "failed"),
              "failures": failures, "recorded_at": datetime.now(timezone.utc).isoformat()}
    write_json(pipeline.store, f"_control/runs/{batch}/airflow.json", result)
    if failures:
        raise AirflowException(f"Pipeline fallido: {failures}")
    return result


with DAG(
    "rss_medallion_lake",
    description="El Tiempo: Bronze → Silver → Gold → Glue → Athena",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=os.getenv("LAKE_SCHEDULE") or None,
    catchup=False, max_active_runs=1, max_active_tasks=1,
    default_args={"owner": "data-lake", "retries": 2,
                  "retry_delay": timedelta(seconds=30), "retry_exponential_backoff": True,
                  "max_retry_delay": timedelta(minutes=2), "execution_timeout": timedelta(minutes=15)},
    params={"batch_id": Param("", type="string", pattern=r"^[A-Za-z0-9_.:-]*$"),
            "replay": Param(False, type="boolean"),
            "from_bronze": Param("", type="string", pattern=r"^[A-Za-z0-9_.:-]*$"),
            "fail_after": Param("", enum=["", "ingest", "transform", "enrich", "publish_silver", "build_gold", "validate"])},
    tags=["rss", "laboratorio", "medallion"],
) as dag:
    previous = None
    for stage in ("check", "ingest", "transform", "enrich", "publish_silver", "build_gold", "validate", "catalog", "athena"):
        task = PythonOperator(task_id=stage, python_callable=task_run,
                              op_kwargs={"stage": stage}, do_xcom_push=False)
        if previous:
            previous >> task
        previous = task
    final = PythonOperator(task_id="record_state", python_callable=record_state,
                           trigger_rule="all_done", retries=0, do_xcom_push=False)
    # All tasks are direct upstreams, so the ledger sees the whole settled run.
    for task in list(dag.tasks):
        if task.task_id != "record_state":
            task >> final
