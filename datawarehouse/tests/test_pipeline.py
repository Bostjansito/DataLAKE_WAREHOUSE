"""Offline regression coverage. AWS/Redshift acceptance still requires deployment."""
import hashlib
import io
from unittest.mock import Mock

import pytest

from aws_dw import cli
from aws_dw.extraction import extractor
from aws_dw.load import loader


@pytest.mark.parametrize("value", ["", "01", "-1", "366", "1;DROP TABLE raw.x", "1_2", "١"])
def test_batch_identifier_rejects_non_source_batches(value):
    with pytest.raises(ValueError):
        extractor.validate_batch_id(value)


@pytest.mark.parametrize("value", ["0", "1", "365"])
def test_source_batch_identifier(value):
    assert extractor.validate_batch_id(value) == value


def test_payload_is_conditionally_created_and_checksummed(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "bucket")
    client = Mock()
    uploaded = {}
    def put(**kwargs):
        uploaded.update(kwargs)
        uploaded["Body"] = kwargs["Body"].read()
    client.put_object.side_effect = put
    info = extractor._payload(client, "mysql", "customers", "1", ["id", "name"], [(1, "á,quoted")])
    assert uploaded["IfNoneMatch"] == "*"
    assert info["sha256"] == hashlib.sha256(uploaded["Body"]).hexdigest()
    assert info["bytes"] == len(uploaded["Body"])
    assert info["rows"] == 1
    assert "/batch_id=1/" in info["key"]


def test_existing_manifest_never_reopens_source(monkeypatch):
    existing = {"batch_id": "1", "source": "mysql", "entities": {}}
    monkeypatch.setattr(extractor, "s3_client", Mock())
    monkeypatch.setattr(extractor, "read_manifest", Mock(return_value=existing))
    source = Mock(side_effect=AssertionError("must not contact source"))
    monkeypatch.setattr(extractor, "get_mysql_connection", source)
    assert extractor.extract_mysql_to_s3("1") is existing
    source.assert_not_called()


def test_mongo_flatten_preserves_nested_business_attributes():
    row = extractor._flatten("reviews", {"review_id": 7, "customer": {"customer_id": 3},
                                         "product": {"product_id": 4}, "rating": 5,
                                         "verification": {"purchase_confirmed": True}})
    assert row[:4] == (7, 3, 4, 5)
    assert '"purchase_confirmed": true' in row[-1]


def test_integrity_failure_stops_replay(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "bucket")
    client = Mock()
    client.get_object.return_value = {"Body": io.BytesIO(b"corrupt")}
    # boto StreamingBody exposes iter_chunks, unlike BytesIO.
    body = client.get_object.return_value["Body"]
    body.iter_chunks = lambda chunk_size: iter([b"corrupt"])
    with pytest.raises(ValueError, match="integrity"):
        extractor.verify_payload(client, {"key": "x", "sha256": "0" * 64, "bytes": 7})


def test_load_cli_reads_only_s3(monkeypatch, tmp_path):
    monkeypatch.setenv("DW_LOCK_PATH", str(tmp_path / "lock"))
    load = Mock()
    monkeypatch.setattr(loader, "load_batch", load)
    monkeypatch.setattr(cli, "extract", Mock(side_effect=AssertionError("source extraction forbidden")))
    assert cli.main(["load", "--batch-id", "2"]) == 0
    load.assert_called_once_with("2")


def test_seed_forwards_original_source_flags(monkeypatch):
    from ecommerce_dw.sources import generate_data
    seed = Mock()
    monkeypatch.setattr(generate_data, "main", seed)
    cli.main(["seed", "--customer-count", "7", "--bad-records", "1"])
    seed.assert_called_once_with(["--customer-count", "7", "--bad-records", "1"])


def test_successful_replay_skips_sources_copy_and_snapshots(monkeypatch, tmp_path):
    monkeypatch.setenv("DW_LOCK_PATH", str(tmp_path / "lock"))
    monkeypatch.setattr(loader, "batch_status", lambda batch: "succeeded")
    setup = Mock()
    copy = Mock()
    dbt = Mock()
    monkeypatch.setattr(cli, "setup", setup)
    monkeypatch.setattr(loader, "load_batch", copy)
    monkeypatch.setattr(cli, "run_dbt", dbt)
    cli.pipeline("1", tmp_path, replay=True)
    setup.assert_not_called()
    copy.assert_not_called()
    dbt.assert_not_called()


def test_controlled_failure_retains_pending_and_recovery_uses_s3(monkeypatch, tmp_path):
    monkeypatch.setenv("DW_LOCK_PATH", str(tmp_path / "lock"))
    monkeypatch.setattr(loader, "batch_status", lambda batch: "pending")
    setup, copy, dbt, extract = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(cli, "setup", setup)
    monkeypatch.setattr(loader, "load_batch", copy)
    monkeypatch.setattr(cli, "run_dbt", dbt)
    monkeypatch.setattr(cli, "extract", extract)
    with pytest.raises(RuntimeError, match="Controlled failure"):
        cli.pipeline("1", tmp_path, fail_after_load=True)
    dbt.assert_not_called()
    cli.pipeline("1", tmp_path)
    extract.assert_not_called()
    assert all(call.kwargs == {"replay": True} for call in setup.call_args_list)
    dbt.assert_called_once_with("1", tmp_path)


def test_dbt_order_and_success_quality_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(loader, "batch_status", lambda batch: "pending")
    mark = Mock()
    monkeypatch.setattr(loader, "mark_batch_succeeded", mark)
    run = Mock()
    monkeypatch.setattr(cli.subprocess, "run", run)
    cli.run_dbt("1", tmp_path)
    assert [call.args[0][1] for call in run.call_args_list] == ["deps", "seed", "run", "snapshot", "run", "test"]
    assert run.call_args_list[2].args[0][2:5] == ["--select", "intermediate", "quarantine"]
    mark.assert_called_once_with("1")
    mark.reset_mock()
    run.side_effect = RuntimeError("dbt quality rejected batch")
    with pytest.raises(RuntimeError, match="quality"):
        cli.run_dbt("1", tmp_path)
    mark.assert_not_called()


def test_incremental_mysql_filters_fact_ids_but_captures_dimensions(monkeypatch):
    # MagicMock supplies the context manager used by real database cursors.
    from unittest.mock import MagicMock
    connection = MagicMock()
    cur = connection.cursor.return_value.__enter__.return_value
    cur.fetchmany.return_value = []
    monkeypatch.setattr(extractor, "get_mysql_connection", lambda: connection)
    monkeypatch.setattr(extractor, "_payload", lambda *args: {"rows": 3})
    def capture(source, batch, action):
        manifest = {"batch_id": batch, "entities": {}}
        action(Mock(), manifest)
        return manifest
    monkeypatch.setattr(extractor, "_capture", capture)
    extractor.extract_mysql_to_s3("2")
    selects = [(call.args[0], call.args[1]) for call in cur.execute.call_args_list
               if call.args[0].startswith("SELECT")]
    assert len(selects) == 4
    assert "WHERE" not in selects[0][0] and "WHERE" not in selects[1][0]
    assert selects[2][1] == (1_000_020, 1_000_023)
    assert selects[3][1] == (10_000_020, 10_000_023)


def test_incomplete_incremental_is_not_published(monkeypatch):
    client = Mock()
    monkeypatch.setattr(extractor, "s3_client", lambda: client)
    monkeypatch.setattr(extractor, "read_manifest", lambda *args, **kwargs: None)
    def action(s3, manifest):
        manifest["entities"] = {"orders": {"rows": 0}, "order_items": {"rows": 0}}
    with pytest.raises(ValueError, match="Incomplete"):
        extractor._capture("mysql", "1", action)
    client.put_object.assert_not_called()


def test_reserved_raw_schema_is_quoted_in_initialization(monkeypatch):
    from contextlib import contextmanager
    from psycopg2 import sql
    cursor = Mock()
    @contextmanager
    def warehouse():
        yield cursor
    monkeypatch.setattr(loader, "warehouse", warehouse)
    loader.initialize()
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert statements[0] == 'CREATE SCHEMA IF NOT EXISTS "raw"'
    assert 'CREATE TABLE IF NOT EXISTS "raw"."batch_ledger"' in statements[1]
    for statement in statements[2:]:
        identifiers = [part for part in statement.seq if isinstance(part, sql.Identifier)]
        assert len(identifiers) == 1
        assert identifiers[0].strings[0] == "raw"


def test_ledger_queries_quote_reserved_raw_schema(monkeypatch):
    from contextlib import contextmanager
    cursor = Mock()
    cursor.fetchone.return_value = ("pending",)
    @contextmanager
    def warehouse():
        yield cursor
    monkeypatch.setattr(loader, "warehouse", warehouse)
    monkeypatch.setattr(loader, "initialize", lambda: None)
    assert loader.batch_status("1") == "pending"
    loader.mark_batch_succeeded("1")
    loader.get_load_stats("1")
    for call in cursor.execute.call_args_list:
        assert '"raw"."batch_ledger"' in call.args[0]
