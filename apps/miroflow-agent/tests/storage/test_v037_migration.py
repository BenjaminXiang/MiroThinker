"""V037 company evidence source tier migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    APP_ROOT
    / "alembic"
    / "versions"
    / "V037_add_company_evidence_source_tier.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v037_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v037_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V037"
    assert migration.down_revision == "V036"


def test_v037_adds_source_tier_to_product_and_scenario_evidence() -> None:
    _load_migration()
    source = _MIGRATION_PATH.read_text(encoding="utf-8")

    assert "company_product_evidence" in source
    assert "company_application_scenario_evidence" in source
    assert "source_tier" in source
    assert 'drop_column("company_product_evidence", "source_tier")' in source
    assert 'drop_column("company_application_scenario_evidence", "source_tier")' in source
