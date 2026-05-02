from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="Legacy SQLite domain tests retired; Postgres coverage is in test_domains_postgres.py"
)


def test_legacy_sqlite_domains_retired() -> None:
    pass
