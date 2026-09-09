"""V033 company enrichment/product migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    APP_ROOT
    / "alembic"
    / "versions"
    / "V033_add_company_enrichment_product_tables.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v033_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v033_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V033"
    assert migration.down_revision == "V032"


def test_v033_adds_company_enrichment_tables_and_news_provenance() -> None:
    migration = _load_migration()
    source = _MIGRATION_PATH.read_text(encoding="utf-8")

    assert "company_product" in source
    assert "company_product_evidence" in source
    assert "source_adapter" in source
    assert "extraction_diagnostics" in source
    assert hasattr(migration, "upgrade")
    assert hasattr(migration, "downgrade")
