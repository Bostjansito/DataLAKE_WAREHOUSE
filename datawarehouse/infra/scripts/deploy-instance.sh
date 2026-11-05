#!/bin/bash
# Run as root only from a root-owned staging directory prepared by remote-deploy.sh.
set -euo pipefail
STAGED_APP=$(cd "$(dirname "$0")/../.." && pwd)
STAGED_CONFIG=${1:?Root-owned staged runtime configuration required}
# Never execute interpreters/installers or write through paths in the service-owned
# tree as root. An existing deployment may contain user-replaced files or symlinks.
runuser -u ecommerce -- /bin/bash --noprofile --norc -s -- "$STAGED_APP" "$STAGED_CONFIG" <<'APP_INSTALL'
set -euo pipefail
umask 077
APP=/opt/ecommerce/app
mkdir -p "$APP"
cp -R -- "$1/." "$APP/"
cp -- "$2" /opt/ecommerce/runtime.json
chmod 600 /opt/ecommerce/runtime.json
cd "$APP"
/usr/bin/python3.11 -m venv /opt/ecommerce/runtime
/opt/ecommerce/runtime/bin/pip install -r requirements.txt
/opt/ecommerce/runtime/bin/pip install --no-deps .
/usr/bin/python3.11 -m venv /opt/ecommerce/airflow-venv
/opt/ecommerce/airflow-venv/bin/pip install 'apache-airflow==2.10.5' --constraint https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.11.txt
/usr/bin/python3.11 -m venv /opt/ecommerce/dbt
/opt/ecommerce/dbt/bin/pip install 'dbt-core==1.9.4' 'dbt-redshift==1.9.4'
install -m 0755 infra/scripts/runtime.py /opt/ecommerce/runtime.py
/opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/dbt/bin/dbt deps --project-dir "$APP/dbt" --profiles-dir "$APP/dbt"
/opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/airflow-venv/bin/airflow db migrate
/opt/ecommerce/runtime/bin/python /opt/ecommerce/runtime.py /opt/ecommerce/airflow-venv/bin/python "$APP/infra/scripts/create-airflow-admin.py"
APP_INSTALL
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
