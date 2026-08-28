"""Per-provider web-lane timeouts (fix-web-lane-timeout-and-utf8-truncation).

Measured from the serving host 2026-08-28 (/tmp/bocha-latency-log.json):
Bocha 280–403 ms incl. summary=true; Serper 1732/2017/2780 ms over 3 calls.
The old shared formula `timeout_ms * 0.00045` gave the main lane 0.675 s and
person probes 1.35 s per provider — structurally below Serper's latency, so
the Serper leg ALWAYS timed out, tripped the breaker (3 fails / 60 s), and
left the lane single-legged; any Bocha jitter then surfaced as
web-lane-unavailable outage wording.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data_agents.canonical_v2.knowledge_serving_isolated import _DualWebLaneAdapter


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def test_main_lane_timeouts_split_by_provider():
    adapter = _DualWebLaneAdapter(
        timeout_ms=1500, max_snapshot_bytes=1024, clock=_clock
    )
    assert adapter._bocha.timeout == 2.0
    assert adapter._serper.timeout == 4.0


def test_probe_lane_timeouts_split_by_provider():
    adapter = _DualWebLaneAdapter(
        timeout_ms=3000, max_snapshot_bytes=1024, clock=_clock
    )
    # timeout_ms * 0.0009 = 2.7 s for the domestic provider; Serper floor 4.0 s.
    assert adapter._bocha.timeout == pytest.approx(2.7)
    assert adapter._serper.timeout == 4.0


def test_outer_wait_per_provider_has_margin():
    adapter = _DualWebLaneAdapter(
        timeout_ms=1500, max_snapshot_bytes=1024, clock=_clock
    )
    assert adapter._outer_wait_seconds("bocha-v1") == 2.5
    assert adapter._outer_wait_seconds("serper-v1") == 4.5


def test_explicit_providers_are_not_overridden():
    class _Fixed:
        timeout = 9.9

        def search(self, query):  # pragma: no cover - not called here
            raise AssertionError("not called")

    bocha = _Fixed()
    serper = _Fixed()
    adapter = _DualWebLaneAdapter(
        timeout_ms=1500,
        max_snapshot_bytes=1024,
        clock=_clock,
        bocha=bocha,
        serper=serper,
    )
    assert adapter._bocha is bocha
    assert adapter._serper is serper
    # outer waits still key off the per-provider attempt budget
    assert adapter._outer_wait_seconds("serper-v1") == 4.5
