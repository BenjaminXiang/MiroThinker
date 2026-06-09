"""V038 company signal event review status migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    APP_ROOT
    / "alembic"
    / "versions"
    / "V038_allow_company_signal_event_needs_review.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v038_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v038_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V038"
    assert migration.down_revision == "V037"


def test_v038_extends_company_signal_event_status_constraint() -> None:
    source = _MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ck_company_signal_event_status" in source
    assert "needs_review" in source
    assert "company_signal_event" in source
