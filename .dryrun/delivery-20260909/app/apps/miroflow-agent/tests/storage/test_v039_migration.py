"""V039 company upload production-hardening migration checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    APP_ROOT
    / "alembic"
    / "versions"
    / "V039_add_company_upload_hardening_fields.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v039_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v039_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V039"
    assert migration.down_revision == "V038"


def test_v039_adds_runner_report_and_progress_fields() -> None:
    migration = _load_migration()
    source = _MIGRATION_PATH.read_text(encoding="utf-8")

    for column_name in (
        "runner_pid",
        "runner_log_path",
        "runner_heartbeat_at",
        "runner_last_seen_at",
        "last_completed_company_id",
        "miss_reason_buckets",
        "quality_report",
    ):
        assert column_name in source
    assert "ix_company_enrichment_batch_runner_heartbeat" in source
    assert "drop_column(\"company_enrichment_batch\", \"quality_report\")" in source
    assert hasattr(migration, "upgrade")
    assert hasattr(migration, "downgrade")
