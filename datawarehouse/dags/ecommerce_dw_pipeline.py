"""One serialized DAG; the shared CLI owns capture/COPY/dbt/ledger ordering."""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator


def validate_parameters(**context):
    config = context["dag_run"].conf or {}
    batch = str(config.get("batch_id", ""))
    if not batch.isascii() or not batch.isdecimal() or str(int(batch)) != batch or not 0 <= int(batch) <= 365:
        raise ValueError("dag_run.conf.batch_id must be 0 (initial) or 1..365 (source daily batch)")
    for flag in ("replay", "fail_after_load"):
        if flag in config and not isinstance(config[flag], bool):
            raise ValueError(f"{flag} must be a JSON boolean")
    return batch


def process_batch(**context):
    config = context["dag_run"].conf or {}
    batch = context["ti"].xcom_pull(task_ids="validate_parameters")
    command = [os.getenv("DW_PYTHON", sys.executable), "-m", "aws_dw.cli", "pipeline", "--batch-id", batch]
    if config.get("replay", False):
        command.append("--replay")
    if config.get("fail_after_load", False):
        command.append("--fail-after-load")
    # Streams all stage output, including dbt quality failures, into this batch's task log.
    subprocess.run(command, check=True)


with DAG(
    dag_id="ecommerce_dw_pipeline",
    description="DE-DW: immutable S3 batches, atomic COPY, dbt SCD2 and quality gate",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "data-platform", "retries": 2,
                  "retry_delay": timedelta(minutes=2),
                  "retry_exponential_backoff": True,
                  "max_retry_delay": timedelta(minutes=10),
                  "execution_timeout": timedelta(hours=2)},
    tags=["data-warehouse", "redshift", "dbt"],
) as dag:
    parameters = PythonOperator(task_id="validate_parameters", python_callable=validate_parameters)
    pipeline = PythonOperator(task_id="capture_copy_dbt_quality_ledger", python_callable=process_batch)
    parameters >> pipeline
