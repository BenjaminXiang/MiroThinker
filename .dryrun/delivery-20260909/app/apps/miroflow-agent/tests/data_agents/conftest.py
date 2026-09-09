# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""W13-15: tests/data_agents/ autouse fixture to reset event loop per function.

test_roster_validation.py async tests use asyncio.run / asyncio.new_event_loop;
without proper teardown, subsequent tests that call asyncio.run get
'RuntimeError: This event loop is already running'.

This fixture forcibly resets the asyncio loop both BEFORE and AFTER each test
across all data_agents/* test files (prof + company + sibling .py).
"""
from __future__ import annotations

import asyncio
import warnings

import pytest


def _reset_event_loop() -> None:
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="There is no current event loop",
                category=DeprecationWarning,
            )
            loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop()
        if not loop.is_closed():
            loop.close()
    except (RuntimeError, AttributeError):
        pass
    asyncio.set_event_loop(asyncio.new_event_loop())


@pytest.fixture(autouse=True)
def _reset_event_loop_per_function():
    _reset_event_loop()
    yield
    _reset_event_loop()
