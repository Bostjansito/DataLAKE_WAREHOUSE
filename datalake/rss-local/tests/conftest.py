"""Test isolation: inherited production settings must never turn local tests into AWS calls."""
import pytest


@pytest.fixture(autouse=True)
def local_only_environment(monkeypatch):
    monkeypatch.delenv("LAKE_BUCKET", raising=False)
    monkeypatch.setenv("LAKE_FEEDS", "config/feeds.json")
    monkeypatch.setenv("LAKE_ENRICHMENT", "disabled")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
