"""V018 paper summary_zh migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION_PATH = (
    Path(__file__).parent.parent.parent
    / "alembic"
    / "versions"
    / "V018_add_paper_summary_zh.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v018_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v018_revision_chain():
    migration = _load_migration()

    assert migration.revision == "V018"
    assert migration.down_revision == "V017"


def test_v018_upgrade_adds_nullable_summary_zh(monkeypatch):
    migration = _load_migration()
    added: list[tuple[str, str, object, bool]] = []

    class _Op:
        def add_column(self, table_name, column) -> None:
            added.append((table_name, column.name, column.type, column.nullable))

    monkeypatch.setattr(migration, "op", _Op())

    migration.upgrade()

    assert [(table, name, nullable) for table, name, _, nullable in added] == [
        ("paper", "summary_zh", True),
    ]
    assert isinstance(added[0][2], migration.sa.Text)


def test_v018_downgrade_drops_summary_zh(monkeypatch):
    migration = _load_migration()
    dropped: list[tuple[str, str]] = []

    class _Op:
        def drop_column(self, table_name, column_name) -> None:
            dropped.append((table_name, column_name))

    monkeypatch.setattr(migration, "op", _Op())

    migration.downgrade()

    assert dropped == [("paper", "summary_zh")]
