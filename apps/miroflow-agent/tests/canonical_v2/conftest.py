from __future__ import annotations

import pytest


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """Keep destructive Canonical V2 migration tests on one database process."""
    del config
    return 0
