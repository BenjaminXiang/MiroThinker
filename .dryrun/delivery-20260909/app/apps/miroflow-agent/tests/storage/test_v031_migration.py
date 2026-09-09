"""V031 paper full-text raw PDF provenance migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    APP_ROOT
    / "alembic"
    / "versions"
    / "V031_add_paper_full_text_raw_pdf_provenance.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v031_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v031_revision_chain():
    migration = _load_migration()

    assert migration.revision == "V031"
    assert migration.down_revision == "V030"


def test_v031_adds_raw_pdf_provenance_columns() -> None:
    migration = _load_migration()
    source = _MIGRATION_PATH.read_text(encoding="utf-8")

    assert "pdf_byte_size" in source
    assert "raw_pdf_storage_ref" in source
    assert hasattr(migration, "upgrade")
    assert hasattr(migration, "downgrade")
