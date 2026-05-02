from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="Legacy SQLite dashboard fixture retired; Postgres dashboard coverage is integration-only"
)


def test_legacy_sqlite_dashboard_fixture_retired() -> None:
    pass
