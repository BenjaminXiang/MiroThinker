from __future__ import annotations

from threading import Event, Thread

from backend.services.canonical_v2_keepwarm import AdaptiveIdleKeepwarm


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_idle_cycle_runs_once_only_after_a_complete_idle_interval() -> None:
    clock = _Clock()
    calls: list[str] = []
    coordinator = AdaptiveIdleKeepwarm(
        cycle=lambda: calls.append("cycle"),
        idle_seconds=300.0,
        monotonic=clock,
    )

    coordinator.mark_activity()
    clock.advance(299.0)
    assert coordinator.run_scheduled_cycle() is False
    clock.advance(1.0)
    assert coordinator.run_scheduled_cycle() is True
    assert coordinator.run_scheduled_cycle() is False

    assert calls == ["cycle"]


def test_real_activity_suppresses_the_next_idle_cycle() -> None:
    clock = _Clock()
    calls: list[str] = []
    coordinator = AdaptiveIdleKeepwarm(
        cycle=lambda: calls.append("cycle"),
        idle_seconds=300.0,
        monotonic=clock,
    )

    clock.advance(300.0)
    coordinator.mark_activity()

    assert coordinator.run_scheduled_cycle() is False
    assert calls == []


def test_keepwarm_cycles_never_overlap() -> None:
    clock = _Clock()
    entered = Event()
    release = Event()

    def blocking_cycle() -> None:
        entered.set()
        assert release.wait(timeout=1.0)

    coordinator = AdaptiveIdleKeepwarm(
        cycle=blocking_cycle,
        idle_seconds=300.0,
        monotonic=clock,
    )
    clock.advance(300.0)
    worker = Thread(target=coordinator.run_scheduled_cycle)
    worker.start()
    assert entered.wait(timeout=1.0)

    assert coordinator.run_scheduled_cycle() is False

    release.set()
    worker.join(timeout=1.0)
    assert not worker.is_alive()


def test_start_is_idempotent_and_stop_interrupts_the_wait() -> None:
    coordinator = AdaptiveIdleKeepwarm(
        cycle=lambda: None,
        idle_seconds=300.0,
    )

    coordinator.start()
    first_worker = coordinator.worker
    coordinator.start()

    assert coordinator.worker is first_worker
    assert first_worker is not None and first_worker.is_alive()

    coordinator.stop()

    assert not first_worker.is_alive()
