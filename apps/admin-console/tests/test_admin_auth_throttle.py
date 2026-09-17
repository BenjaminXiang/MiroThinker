"""R3 — login throttling: 5 failures lock 60 s, doubling, success clears, cap.

Fixture source: injected clock; no test sleeps.
"""

from __future__ import annotations

from backend.services.admin_auth import AdminLoginThrottle


_KEY = "login:ops:10.0.0.9"


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _exhaust(throttle: AdminLoginThrottle, key: str = _KEY) -> int:
    """Record exactly max_failures failures; return the resulting lock seconds."""

    for _ in range(throttle.max_failures - 1):
        assert throttle.record_failure(key).allowed is True
    locked = throttle.record_failure(key)
    assert locked.allowed is False
    assert locked.remaining_attempts == 0
    return locked.retry_after_seconds


def test_a_single_failure_only_counts_down() -> None:
    throttle = AdminLoginThrottle(clock=_Clock())

    assert throttle.check(_KEY).allowed is True
    decision = throttle.record_failure(_KEY)

    assert decision.allowed is True
    assert decision.retry_after_seconds == 0
    assert decision.remaining_attempts == throttle.max_failures - 1


def test_five_failures_lock_for_sixty_seconds_then_recover() -> None:
    clock = _Clock()
    throttle = AdminLoginThrottle(clock=clock)

    assert _exhaust(throttle) == 60
    locked = throttle.check(_KEY)
    assert locked.allowed is False
    assert locked.retry_after_seconds == 60

    clock.advance(59)
    assert throttle.check(_KEY).allowed is False

    clock.advance(2)
    recovered = throttle.check(_KEY)
    assert recovered.allowed is True
    assert recovered.retry_after_seconds == 0
    assert recovered.remaining_attempts == throttle.max_failures


def test_continued_failures_double_the_lock() -> None:
    clock = _Clock()
    throttle = AdminLoginThrottle(clock=clock)
    durations = []

    for _ in range(3):
        durations.append(_exhaust(throttle))
        clock.advance(durations[-1] + 1)
        assert throttle.check(_KEY).allowed is True

    assert durations == [60, 120, 240]


def test_lock_duration_is_capped_at_thirty_minutes() -> None:
    clock = _Clock()
    throttle = AdminLoginThrottle(clock=clock)
    durations = []

    for _ in range(8):
        durations.append(_exhaust(throttle))
        clock.advance(durations[-1] + 1)

    assert throttle.max_lock_seconds == 1800
    assert max(durations) == 1800
    assert durations[-1] == 1800


def test_success_clears_the_failure_counter() -> None:
    clock = _Clock()
    throttle = AdminLoginThrottle(clock=clock)
    for _ in range(throttle.max_failures - 1):
        assert throttle.record_failure(_KEY).allowed is True

    throttle.record_success(_KEY)

    assert throttle.check(_KEY).remaining_attempts == throttle.max_failures
    for _ in range(throttle.max_failures - 1):
        assert throttle.record_failure(_KEY).allowed is True
    assert throttle.check(_KEY).allowed is True


def test_the_key_isolates_username_and_client_address() -> None:
    clock = _Clock()
    throttle = AdminLoginThrottle(clock=clock)
    _exhaust(throttle, "login:ops:10.0.0.9")

    assert throttle.check("login:ops:10.0.0.10").allowed is True
    assert throttle.check("login:ops2:10.0.0.9").allowed is True
    assert throttle.check("login:ops:10.0.0.9").allowed is False
