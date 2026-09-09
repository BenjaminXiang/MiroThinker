"""V036 structured company team-member fields migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    APP_ROOT
    / "alembic"
    / "versions"
    / "V036_add_company_team_member_structured_fields.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v036_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v036_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V036"
    assert migration.down_revision == "V035"


def test_v036_adds_structured_team_member_fields() -> None:
    migration = _load_migration()
    source = _MIGRATION_PATH.read_text(encoding="utf-8")

    assert "structured_background" in source
    assert "structured_experience_highlights" in source
    assert "structured_relevance" in source
    assert "structured_confidence" in source
    assert "structured_evidence_span" in source
    assert "structured_raw_text" in source
    assert "drop_column(\"company_team_member\", \"structured_raw_text\")" in source
    assert hasattr(migration, "upgrade")
    assert hasattr(migration, "downgrade")
