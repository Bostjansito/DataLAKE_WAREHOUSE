#!/bin/bash
# Run as root through SSM after downloading/extracting the explicit bundle.
set -euo pipefail
APP=/opt/ecommerce/app
cd "$APP"
python3.11 -m venv /opt/ecommerce/runtime
/opt/ecommerce/runtime/bin/pip install -r requirements.txt
/opt/ecommerce/runtime/bin/pip install --no-deps .
python3.11 -m venv /opt/ecommerce/airflow-venv
/opt/ecommerce/airflow-venv/bin/pip install 'apache-airflow==2.10.5' --constraint https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.11.txt
python3.11 -m venv /opt/ecommerce/dbt
/opt/ecommerce/dbt/bin/pip install 'dbt-core==1.9.4' 'dbt-redshift==1.9.4'
install -m 0755 infra/scripts/runtime.py /opt/ecommerce/runtime.py
chown -R ecommerce:ecommerce /opt/ecommerce
runuser -u ecommerce -- /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/dbt/bin/dbt deps --project-dir "$APP/dbt" --profiles-dir "$APP/dbt"
runuser -u ecommerce -- /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/airflow-venv/bin/airflow db migrate
runuser -u ecommerce -- /opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/airflow-venv/bin/python "$APP/infra/scripts/create-airflow-admin.py"
cat > /etc/systemd/system/ecommerce-airflow.service <<'UNIT'
[Unit]
Description=Ecommerce Airflow scheduler (single-process teaching environment)
After=network-online.target
Wants=network-online.target
[Service]
User=ecommerce
Group=ecommerce
WorkingDirectory=/opt/ecommerce/app
ExecStart=/opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/airflow-venv/bin/airflow scheduler
Restart=on-failure
UMask=0077
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/ecommerce-airflow-web.service <<'UNIT'
[Unit]
Description=Ecommerce Airflow UI (loopback only)
After=network-online.target ecommerce-airflow.service
Wants=network-online.target
[Service]
User=ecommerce
Group=ecommerce
WorkingDirectory=/opt/ecommerce/app
ExecStart=/opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/airflow-venv/bin/airflow webserver --hostname 127.0.0.1 --port 8080 --workers 1
Restart=on-failure
UMask=0077
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now ecommerce-airflow ecommerce-airflow-web
