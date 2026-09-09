"""V034 structured company business fields migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    APP_ROOT
    / "alembic"
    / "versions"
    / "V034_add_company_structured_business_fields.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v034_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v034_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V034"
    assert migration.down_revision == "V033"


def test_v034_adds_product_structure_and_application_scenario_tables() -> None:
    migration = _load_migration()
    source = _MIGRATION_PATH.read_text(encoding="utf-8")

    assert "product_category" in source
    assert "target_customers" in source
    assert "application_scenarios" in source
    assert "technical_tags" in source
    assert "company_application_scenario" in source
    assert "company_application_scenario_evidence" in source
    assert "drop_table(\"company_application_scenario_evidence\")" in source
    assert "drop_table(\"company_application_scenario\")" in source
    assert hasattr(migration, "upgrade")
    assert hasattr(migration, "downgrade")
