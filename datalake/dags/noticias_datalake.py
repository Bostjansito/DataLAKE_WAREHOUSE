"""DAG del data lake de noticias: RSS -> Bronze -> Silver (+Comprehend) -> Gold -> Glue -> Athena.

Etapas (dependencias explícitas):
  1. validar_configuracion       fuentes y acceso a S3, Glue, Athena (sin costo)
  2. extraer_fuente (x fuente)   un task mapeado por fuente RSS -> Bronze, con reintentos acotados
     resumen_extraccion          complete | partial | failed (una fuente caída NO es "sin noticias")
  3. limpiar_validar_deduplicar  Bronze -> estado preparado (cuarentena de rechazados)
  4. enriquecer_comprehend       solo noticias nuevas o con texto analizado distinto (caché por hash)
  5. publicar_silver             Parquet en v=<write_id> + cambio de partición en Glue
  6. construir_gold              agregados de las fechas afectadas (sin publicar)
  7. actualizar_glue             publica Gold y verifica las particiones de Silver y Gold
  8. validar_athena              reglas de calidad sobre lo publicado
  9. registrar_estado            control/runs/run_id=<lote>/dag.json (se ejecuta siempre)

Parámetros (Trigger DAG w/ config):
  bronze_run_id     reprocesa ese lote de Bronze sin consultar los RSS
  rebuild           reconstruye Silver desde todo Bronze
  fuente_caida      source_id cuya URL se reemplaza por una inexistente (demostración de fallo parcial)
  simular_fallo     falla publicar_silver en el primer intento (el reintento recupera sin duplicar)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from airflow.models.param import Param
from airflow.operators.python import get_current_context
from airflow.utils.state import TaskInstanceState
from airflow.utils.trigger_rule import TriggerRule

log = logging.getLogger("noticias.dag")

DEFAULT_ARGS = {
    "owner": "datalake",
    "retries": 2,                       # reintentos acotados para fallos transitorios
    "retry_delay": timedelta(seconds=30),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=20),
}


def _settings():
    from noticias.settings import load_settings, setup_logging
    setup_logging()
    return load_settings()


def _run_stamp() -> str:
    """Identificador del lote derivado de la ejecución del DAG: estable entre reintentos.

    - Programadas: FIN del intervalo (logical_date es el inicio, una hora antes de la extracción real).
    - Manuales: el momento del disparo (logical_date). Su data_interval_end es el fin del último
      intervalo completo y se repetiría entre disparos manuales de la misma hora.
    Así el identificador es único por ejecución y sigue el orden real de las extracciones, que es el
    que decide qué versión de una noticia es la vigente.
    """
    ctx = get_current_context()
    dag_run = ctx["dag_run"]
    moment = ctx["data_interval_end"] if dag_run.run_type == "scheduled" else dag_run.logical_date
    return moment.strftime("%Y%m%dT%H%M%SZ")


@dag(
    dag_id="noticias_datalake",
    description="RSS de El Tiempo -> S3 (Bronze/Silver/Gold) + Comprehend + Glue + Athena",
    schedule="0 * * * *",               # cada hora durante el laboratorio
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,                  # control de concurrencia: nunca dos escrituras a la vez
    max_active_tasks=4,
    default_args=DEFAULT_ARGS,
    is_paused_upon_creation=False,
    tags=["datalake", "noticias"],
    params={
        "bronze_run_id": Param("", type="string", description="Lote de Bronze a reprocesar (vacío = extraer)"),
        "rebuild": Param(False, type="boolean", description="Reconstruir Silver desde todo Bronze"),
        "fuente_caida": Param("", type="string", description="source_id a simular como no disponible"),
        "simular_fallo": Param(False, type="boolean", description="Falla publicar_silver en el 1er intento"),
    },
    render_template_as_native_obj=True,
)
def noticias_datalake():

    @task
    def validar_configuracion() -> dict:
        import boto3
        settings = _settings()
        params = get_current_context()["params"]
        ident = boto3.client("sts", region_name=settings.region).get_caller_identity()
        boto3.client("s3", region_name=settings.region).head_bucket(Bucket=settings.bucket)
        glue = boto3.client("glue", region_name=settings.region)
        glue.get_database(Name=settings.glue_database)
        tables = [t["Name"] for t in glue.get_tables(DatabaseName=settings.glue_database)["TableList"]]
        boto3.client("athena", region_name=settings.region).get_work_group(WorkGroup=settings.athena_workgroup)
        source_ids = [s.source_id for s in settings.sources]
        if params["fuente_caida"] and params["fuente_caida"] not in source_ids:
            raise AirflowFailException(f"fuente_caida={params['fuente_caida']} no está en {source_ids}")
        if params["bronze_run_id"] and params["rebuild"]:
            raise AirflowFailException("Use bronze_run_id o rebuild, no ambos")
        log.info("run_id=%s task=validar_configuracion rol=%s bucket=%s tablas=%d fuentes=%s",
                 _run_stamp(), ident["Arn"], settings.bucket, len(tables), source_ids)
        reprocess = bool(params["bronze_run_id"] or params["rebuild"])
        return {"run_id": _run_stamp(), "sources": [] if reprocess else source_ids}

    @task
    def fuentes(cfg: dict) -> list[str]:
        return cfg["sources"]

    @task(max_active_tis_per_dag=3)
    def extraer_fuente(source_id: str) -> dict:
        import dataclasses

        import requests
        from noticias.ingest import OK_STATUSES, extract_source
        from noticias.storage import GlueCatalog, S3Store

        ctx = get_current_context()
        settings = _settings()
        run_id = _run_stamp()
        src = next(s for s in settings.sources if s.source_id == source_id)
        if ctx["params"]["fuente_caida"] == source_id:
            src = dataclasses.replace(src, url=src.url.replace(".xml", "-no-existe.xml"))
        s3 = S3Store(settings.bucket, settings.region)
        catalog = GlueCatalog(settings.glue_database, settings.region)
        with requests.Session() as session:
            record = extract_source(src, run_id, s3, catalog, settings, session)
        if record["status"] not in OK_STATUSES:
            ti = ctx["ti"]
            if ti.try_number <= ti.max_tries:
                # Puede ser transitorio: Airflow reintenta. En el último intento queda registrado el fallo
                # y la ejecución continúa como parcial con las demás fuentes.
                raise RuntimeError(f"source={source_id} run_id={run_id} status={record['status']} "
                                   f"error={record['error_message']} (intento {ti.try_number})")
            log.error("source=%s run_id=%s task=extract agotados los reintentos: fuente no disponible",
                      source_id, run_id)
        return {k: record.get(k) for k in ("source_id", "status", "error_message", "items_received", "bronze_key")}

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def resumen_extraccion(cfg: dict, resultados: list[dict]) -> dict:
        from noticias import control
        from noticias.ingest import OK_STATUSES
        from noticias.settings import iso, utc_now
        from noticias.storage import S3Store

        settings = _settings()
        params = get_current_context()["params"]
        run_id = cfg["run_id"]
        if params["bronze_run_id"] or params["rebuild"]:
            mode = "rebuild" if params["rebuild"] else "reprocess"
            log.info("run_id=%s task=resumen_extraccion modo=%s lote=%s sin consultar RSS",
                     run_id, mode, params["bronze_run_id"] or "todo Bronze")
            return {"run_id": run_id, "status": mode, "bronze_run_ids": [params["bronze_run_id"]] if params["bronze_run_id"] else []}
        resultados = [r for r in (resultados or []) if r]
        ok = [r for r in resultados if r["status"] in OK_STATUSES]
        expected = len(cfg["sources"])
        status = "complete" if len(ok) == expected else ("partial" if ok else "failed")
        summary = {"run_id": run_id, "stage": "extract", "status": status, "finished_at": iso(utc_now()),
                   "sources_ok": [r["source_id"] for r in ok],
                   "sources_failed": [r for r in resultados if r["status"] not in OK_STATUSES]
                   + [{"source_id": s, "status": "task_failed"} for s in cfg["sources"]
                      if s not in {r["source_id"] for r in resultados}],
                   "bronze_run_ids": [run_id]}
        control.write_run_status(S3Store(settings.bucket, settings.region), run_id, "extract", summary)
        log.info("run_id=%s task=resumen_extraccion status=%s ok=%d esperadas=%d", run_id, status, len(ok), expected)
        if status == "failed":
            raise AirflowFailException(f"run_id={run_id}: ninguna fuente disponible")
        return summary

    @task
    def limpiar_validar_deduplicar(extraccion: dict) -> dict:
        from noticias.silver import prepare_silver
        params = get_current_context()["params"]
        return prepare_silver(_settings(), extraccion["run_id"], run_ids=extraccion["bronze_run_ids"] or None,
                              rebuild=bool(params["rebuild"]))

    @task
    def enriquecer_comprehend(prep: dict) -> dict:
        from noticias.silver import enrich_silver
        return enrich_silver(_settings(), prep["job_id"])

    @task
    def publicar_silver(prep: dict, _enriquecido: dict) -> dict:
        from noticias.silver import publish_silver
        ctx = get_current_context()
        fail = bool(ctx["params"]["simular_fallo"]) and ctx["ti"].try_number == 1
        return publish_silver(_settings(), prep["job_id"], simulate_failure=fail)

    @task
    def construir_gold(silver: dict) -> dict:
        from noticias.gold import run_gold
        return run_gold(_settings(), run_id=silver["run_id"], dates=silver["affected_dates"], publish=False)

    @task
    def actualizar_glue(gold: dict) -> dict:
        from noticias.gold import publish_gold
        return publish_gold(_settings(), gold["run_id"])

    @task(retries=1)
    def validar_athena(glue: dict) -> dict:
        from noticias.validate import run_validations
        return run_validations(_settings(), glue["run_id"])

    @task(trigger_rule=TriggerRule.ALL_DONE, retries=0)
    def registrar_estado() -> dict:
        from noticias import control
        from noticias.settings import iso, utc_now
        from noticias.storage import S3Store

        ctx = get_current_context()
        settings = _settings()
        run_id = _run_stamp()
        tis = [t for t in ctx["dag_run"].get_task_instances() if t.task_id != "registrar_estado"]
        tareas = {}
        for t in tis:
            key = t.task_id if t.map_index < 0 else f"{t.task_id}[{t.map_index}]"
            tareas[key] = {"state": t.state, "try_number": t.try_number}
        failed = [k for k, v in tareas.items() if v["state"] in (TaskInstanceState.FAILED, TaskInstanceState.UPSTREAM_FAILED)]
        extract = ctx["ti"].xcom_pull(task_ids="resumen_extraccion") or {}
        hard_failed = [k for k in failed if not k.startswith("extraer_fuente")]
        if hard_failed or not extract:
            status = "failed"
        elif extract.get("status") == "partial" or failed:
            status = "partial"
        else:
            status = "complete"
        resultado = {"run_id": run_id, "dag_run_id": ctx["dag_run"].run_id, "status": status,
                     "extraction": extract.get("status"), "params": dict(ctx["params"]),
                     "silver": ctx["ti"].xcom_pull(task_ids="publicar_silver"),
                     "validations": (ctx["ti"].xcom_pull(task_ids="validar_athena") or {}).get("checks"),
                     "tasks": tareas, "finished_at": iso(utc_now())}
        control.write_run_status(S3Store(settings.bucket, settings.region), run_id, "dag", resultado)
        log.info("run_id=%s task=registrar_estado status=%s fallidas=%s", run_id, status, failed)
        if status == "failed":
            raise AirflowFailException(f"run_id={run_id} terminó con estado failed: {hard_failed}")
        return {"run_id": run_id, "status": status}

    cfg = validar_configuracion()
    extracciones = extraer_fuente.expand(source_id=fuentes(cfg))
    resumen = resumen_extraccion(cfg, extracciones)
    prep = limpiar_validar_deduplicar(resumen)
    enr = enriquecer_comprehend(prep)
    silver = publicar_silver(prep, enr)
    gold = construir_gold(silver)
    glue = actualizar_glue(gold)
    checks = validar_athena(glue)
    [cfg, resumen, checks] >> registrar_estado()


noticias_datalake()

if os.environ.get("DATALAKE_BUCKET") is None:
    log.warning("DATALAKE_BUCKET no está definido en el entorno de Airflow")
