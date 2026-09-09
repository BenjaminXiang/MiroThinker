"""V014 company narrative fields migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION_PATH = (
    Path(__file__).parent.parent.parent
    / "alembic"
    / "versions"
    / "V014_add_company_narrative_fields.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v014_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v014_revision_chain():
    migration = _load_migration()

    assert migration.revision == "V014"
    assert migration.down_revision == "V013"


def test_v014_upgrade_adds_nullable_text_columns(monkeypatch):
    migration = _load_migration()
    added: list[tuple[str, str, object, bool]] = []

    class _Op:
        def add_column(self, table_name, column) -> None:
            added.append((table_name, column.name, column.type, column.nullable))

    monkeypatch.setattr(migration, "op", _Op())

    migration.upgrade()

    assert [(table, name, nullable) for table, name, _, nullable in added] == [
        ("company", "profile_summary", True),
        ("company", "technology_route_summary", True),
    ]
    assert all(isinstance(column_type, migration.sa.Text) for _, _, column_type, _ in added)


def test_v014_downgrade_drops_columns_in_reverse_order(monkeypatch):
    migration = _load_migration()
    dropped: list[tuple[str, str]] = []

    class _Op:
        def drop_column(self, table_name, column_name) -> None:
            dropped.append((table_name, column_name))

    monkeypatch.setattr(migration, "op", _Op())

    migration.downgrade()

    assert dropped == [
        ("company", "technology_route_summary"),
        ("company", "profile_summary"),
    ]
