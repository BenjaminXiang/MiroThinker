"""V035 company enrichment batch operations migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    APP_ROOT
    / "alembic"
    / "versions"
    / "V035_add_company_enrichment_batch_ops.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v035_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v035_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V035"
    assert migration.down_revision == "V034"


def test_v035_adds_enrichment_batch_audit_and_review_tables() -> None:
    migration = _load_migration()
    source = _MIGRATION_PATH.read_text(encoding="utf-8")

    assert "company_enrichment_batch" in source
    assert "company_enrichment_company_state" in source
    assert "company_enrichment_search_audit" in source
    assert "company_enrichment_review_action" in source
    assert "query_text" in source
    assert "miss_reason" in source
    assert "previous_status" in source
    assert "new_status" in source
    assert "drop_table(\"company_enrichment_review_action\")" in source
    assert "drop_table(\"company_enrichment_search_audit\")" in source
    assert "drop_table(\"company_enrichment_company_state\")" in source
    assert "drop_table(\"company_enrichment_batch\")" in source
    assert hasattr(migration, "upgrade")
    assert hasattr(migration, "downgrade")
