"""V042 professor profile section and paper merge alias migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    APP_ROOT
    / "alembic"
    / "versions"
    / "V042_add_professor_profile_section_paper_merge_alias.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v042_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v042_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V042"
    assert migration.down_revision == "V041"


def test_v042_adds_profile_section_and_paper_merge_alias_tables() -> None:
    migration = _load_migration()
    source = _MIGRATION_PATH.read_text(encoding="utf-8")

    assert "professor_profile_section" in source
    assert "research_overview" in source
    assert "source_text_hash" in source
    assert "generation_method" in source
    assert "paper_merge_alias" in source
    assert "old_paper_id" in source
    assert "canonical_paper_id" in source
    assert "ck_paper_merge_alias_not_self" in source
    assert "uq_professor_profile_section_source" in source
    assert "uq_paper_merge_alias_old_paper" in source
    assert "op.drop_table(\"paper_merge_alias\")" in source
    assert "op.drop_table(\"professor_profile_section\")" in source
    assert hasattr(migration, "upgrade")
    assert hasattr(migration, "downgrade")
