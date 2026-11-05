#!/usr/bin/env python3
"""Create the UI administrator in-process: no password in argv or logs."""
from contextlib import redirect_stderr, redirect_stdout
import io
import logging
import os
from pathlib import Path
import secrets

password_file = Path("/opt/ecommerce/airflow/admin-password")
if not password_file.exists():
    password = secrets.token_urlsafe(32)
    # Match Airflow 2.10.5's FAB users_create implementation without its CLI audit.
    # Do not let exception messages or third-party logging expose credentials.
    logging.disable(logging.CRITICAL)
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            from airflow.providers.fab.auth_manager.cli_commands.utils import get_application_builder
            with get_application_builder() as appbuilder:
                role = appbuilder.sm.find_role("Admin")
                if not role or appbuilder.sm.find_user("admin"):
                    raise RuntimeError("Administrator role missing or existing user has no password file")
                user = appbuilder.sm.add_user("admin", "Warehouse", "Operator", "admin@localhost.invalid", role, password)
                if not user:
                    raise RuntimeError("Administrator creation failed")
        fd = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as target:
            target.write(password)
    except Exception:
        raise SystemExit("Airflow administrator provisioning failed; credential-bearing output withheld") from None
