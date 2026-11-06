"""Run from datalake/rss-local: .venv/bin/python scripts/smoke.py. No AWS requests."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

# A project installed with `pip install -e .[test]` is required.
from lake.cli import execute, parser
from lake.storage import LocalStore


def main():
    evidence = Path("evidence")
    evidence.mkdir(exist_ok=True)
    command = [sys.executable, "-m", "pytest", "-q", "--junitxml=evidence/test-results.xml"]
    result = subprocess.run(command, text=True, capture_output=True)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "aws_resources_created": False, "aws_api_calls_in_smoke": False,
              "nlp_test_mode": "controlled test doubles; published demo uses skipped_disabled, not AWS results",
              "command": command, "returncode": result.returncode,
              "pytest_stdout": result.stdout, "pytest_stderr": result.stderr}
    if result.returncode == 0:
        # Explicit empty bucket overrides an inherited LAKE_BUCKET; NLP always disabled.
        root = ".local-lake/smoke/" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        report["local_root"] = root
        base = ["--root", root, "--bucket", "", "--enrichment", "disabled", "--feeds", "config/feeds.json"]
        first = execute(parser().parse_args(["run", *base, "--run-id", "initial", "--fixture-dir", "tests/fixtures/initial"]))
        store = LocalStore(root)
        bronze = store.list("bronze/")
        replay = execute(parser().parse_args(["run", *base, "--run-id", "initial", "--replay"]))
        assert replay == first
        rebuilt = execute(parser().parse_args(["run", *base, "--run-id", "rebuild", "--from-bronze", "initial"]))
        assert store.list("bronze/") == bronze
        assert rebuilt["tables"]["news"]["row_count"] == first["tables"]["news"]["row_count"]
        test_results = ET.parse("evidence/test-results.xml")
        report.update(tests=[{"name": t.attrib["name"], "seconds": t.attrib.get("time"),
                              "passed": len(t.findall("failure")) == len(t.findall("error")) == 0}
                             for t in test_results.iter("testcase")],
                      initial_metrics=first["metrics"], rebuilt_metrics=rebuilt["metrics"],
                      replay_equal=True, bronze_unchanged=True,
                      bronze_files=bronze, snapshot=rebuilt,
                      fixture_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in sorted(Path("tests/fixtures/initial").glob("*.xml"))})
    Path("evidence/local-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidencia real: evidence/local-smoke.json y evidence/test-results.xml")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
