"""V041 homepage recursion page ledger migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    APP_ROOT
    / "alembic"
    / "versions"
    / "V041_add_homepage_recursion_page_ledger.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v041_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v041_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V041"
    assert migration.down_revision == "V040"


def test_v041_adds_homepage_recursion_ledger_table() -> None:
    migration = _load_migration()
    source = _MIGRATION_PATH.read_text(encoding="utf-8")

    assert "homepage_recursion_page_ledger" in source
    assert "processed" in source
    assert "zero_extraction" in source
    assert "fetch_failed" in source
    assert "skipped" in source
    assert "uq_homepage_recursion_page_ledger_scope" in source
    assert "ix_homepage_recursion_page_ledger_status" in source
    assert hasattr(migration, "upgrade")
    assert hasattr(migration, "downgrade")
