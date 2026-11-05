"""Exercise deployment shell routing locally using offline CLI executables."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "infra" / "scripts"


@pytest.fixture
def offline_cli(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "commands.jsonl"
    # Only these fakes can be reached as AWS/Terraform; neither contacts a network.
    # A venv interpreter path may contain spaces, which kernel shebang parsing
    # treats as arguments; resolve python3 through PATH instead.
    body = (
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "name = pathlib.Path(sys.argv[0]).name\n"
        "with open(os.environ['OFFLINE_COMMAND_LOG'], 'a') as stream:\n"
        "    stream.write(json.dumps([name, *sys.argv[1:]]) + '\\n')\n"
        "if name == 'terraform':\n"
        "    print('offline-bucket' if sys.argv[-1] == 'raw_bucket' else "
        "json.dumps({'AWS_REGION': 'us-east-1', 'MYSQL_HOST': 'mysql.example.test', "
        "'MYSQL_PORT': 3306, 'MYSQL_DATABASE': 'ecommerce', 'MYSQL_SECRET_ARN': 'managed-secret'}))\n"
        "elif name == 'aws' and sys.argv[1:3] == ['ssm', 'send-command']:\n"
        "    print('offline-command-id')\n"
    )
    for name in ("aws", "terraform"):
        executable = bin_dir / name
        executable.write_text(body)
        executable.chmod(0o755)
    env = os.environ.copy()
    env.update(PATH=f"{bin_dir}:{env['PATH']}", OFFLINE_COMMAND_LOG=str(log), AWS_REGION="us-east-1")
    return env, log


def test_upload_uses_terraform_runtime_output_and_allowlisted_bundle(tmp_path, offline_cli):
    env, log = offline_cli
    project = tmp_path / "application"
    scripts = project / "infra" / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(SCRIPTS / "upload-bundle.sh", scripts / "upload-bundle.sh")
    for directory in ("src", "dags", "dbt"):
        (project / directory).mkdir()
        (project / directory / "included.txt").write_text("offline fixture")
    for filename in ("requirements.txt", "pyproject.toml"):
        (project / filename).write_text("")
    (project / ".env").write_text("DO_NOT_PACKAGE=offline-marker")
    result = subprocess.run(["bash", str(scripts / "upload-bundle.sh")], cwd=tmp_path,
                            env=env, capture_output=True, text=True, check=True)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls[0][-3:] == ["output", "-raw", "raw_bucket"]
    assert calls[1][-3:] == ["output", "-json", "runtime_config"]
    build = project / "infra" / ".build"
    bundle, = build.glob("bundle-*.tar.gz")
    config_path = bundle.with_name(bundle.name.removesuffix(".tar.gz") + ".runtime.json")
    config = json.loads(config_path.read_text())
    assert config["MYSQL_SECRET_ARN"] == "managed-secret"
    assert "MYSQL_PASSWORD" not in config
    assert config_path.stat().st_mode & 0o077 == 0
    with tarfile.open(bundle) as archive:
        names = archive.getnames()
    assert ".env" not in names
    assert "src/included.txt" in names
    assert "infra/scripts/upload-bundle.sh" in names
    uploads = [call for call in calls if call[:3] == ["aws", "s3", "cp"]]
    assert uploads[0][4] == f"s3://offline-bucket/deploy/{bundle.name}"
    assert uploads[1][4] == f"s3://offline-bucket/deploy/{config_path.name}"
    assert "managed-secret" not in result.stdout
    # Even back-to-back uploads must not overwrite an earlier deployment config.
    subprocess.run(["bash", str(scripts / "upload-bundle.sh")], cwd=tmp_path,
                   env=env, capture_output=True, text=True, check=True)
    bundles = list(build.glob("bundle-*.tar.gz"))
    configs = list(build.glob("bundle-*.runtime.json"))
    assert len(bundles) == len(configs) == 2
    assert {path.name.removesuffix(".tar.gz") for path in bundles} == {
        path.name.removesuffix(".runtime.json") for path in configs}
    assert config_path.read_text() == json.dumps(config) + "\n"


def test_remote_deploy_downloads_matching_config_and_runs_installer(tmp_path, offline_cli):
    env, log = offline_cli
    bundle = "s3://offline-bucket/deploy/bundle-20261105T000000Z.tar.gz"
    subprocess.run(["bash", str(SCRIPTS / "remote-deploy.sh"), "i-offline", bundle],
                   cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    call, = [json.loads(line) for line in log.read_text().splitlines()]
    assert call[:3] == ["aws", "ssm", "send-command"]
    assert call[call.index("--instance-ids") + 1] == "i-offline"
    params = json.loads(call[call.index("--parameters") + 1])
    commands = params["commands"]
    assert f'aws s3 cp {bundle} "$STAGE/bundle.tar.gz"' in commands
    paired_config = bundle.removesuffix(".tar.gz") + ".runtime.json"
    assert f'aws s3 cp {paired_config} "$STAGE/runtime.json"' in commands
    assert 'STAGE=$(mktemp -d /var/tmp/ecommerce-deploy.XXXXXXXX)' in commands
    assert 'trap \'rm -rf -- "$STAGE"\' EXIT' in commands
    assert 'tar --no-same-owner -xzf "$STAGE/bundle.tar.gz" -C "$STAGE/app"' in commands
    assert commands[-1] == 'bash "$STAGE/app/infra/scripts/deploy-instance.sh" "$STAGE/runtime.json"'
    assert commands.index('chmod -R a+rX,go-w "$STAGE"') < len(commands) - 1
    # SSM root never downloads, extracts, or executes from the writable app tree.
    assert all("/opt/ecommerce" not in command for command in commands)


def test_installer_confines_user_writable_paths_to_unprivileged_block():
    # Inspect the privilege boundary without invoking runuser, systemd or root.
    script = (SCRIPTS / "deploy-instance.sh").read_text()
    root_before, remainder = script.split("<<'APP_INSTALL'\n", 1)
    user_install, root_after = remainder.split("\nAPP_INSTALL\n", 1)
    assert 'runuser -u ecommerce -- /bin/bash --noprofile --norc -s -- "$STAGED_APP" "$STAGED_CONFIG"' in root_before
    assert "/opt/ecommerce" not in root_before
    assert 'cp -R -- "$1/." "$APP/"' in user_install
    assert 'cp -- "$2" /opt/ecommerce/runtime.json' in user_install
    assert "chmod 600 /opt/ecommerce/runtime.json" in user_install
    assert "/usr/bin/python3.11 -m venv /opt/ecommerce/runtime" in user_install
    assert "/opt/ecommerce/runtime/bin/pip install -r requirements.txt" in user_install
    assert "/opt/ecommerce/airflow-venv/bin/pip install" in user_install
    assert "/opt/ecommerce/dbt/bin/pip install" in user_install
    assert "chown" not in script
    assert "systemctl daemon-reload" in root_after
    # User paths in root's systemd declarations are data, not shell execution.
    for line in root_after.splitlines():
        if "/opt/ecommerce" in line:
            assert line.startswith(("WorkingDirectory=", "ExecStart="))


@pytest.mark.parametrize("bundle", ["s3://offline-bucket/bundle.tar.gz", "https://example.test/bundle.tar.gz"])
def test_remote_rejects_non_deployment_uri_without_aws_call(tmp_path, offline_cli, bundle):
    env, log = offline_cli
    result = subprocess.run(["bash", str(SCRIPTS / "remote-deploy.sh"), "i-offline", bundle],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert not log.exists()
