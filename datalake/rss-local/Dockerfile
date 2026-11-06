FROM apache/airflow:2.10.5-python3.11
USER airflow
COPY --chown=airflow:root pyproject.toml /opt/lake/pyproject.toml
COPY --chown=airflow:root lake /opt/lake/lake
RUN pip install --no-cache-dir "apache-airflow==2.10.5" /opt/lake
COPY --chown=airflow:root config /opt/lake/config
COPY --chown=airflow:root dags /opt/airflow/dags
WORKDIR /opt/lake
