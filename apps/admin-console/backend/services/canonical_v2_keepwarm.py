"""Lifecycle-owned adaptive keep-warm for the isolated Canonical V2 app."""

from __future__ import annotations

from collections.abc import Callable
import logging
from threading import Event, Lock, Thread
from time import monotonic


logger = logging.getLogger(__name__)


class AdaptiveIdleKeepwarm:
    """Run one non-overlapping callback per complete idle interval."""

    def __init__(
        self,
        *,
        cycle: Callable[[], None],
        idle_seconds: float,
        monotonic: Callable[[], float] = monotonic,
        wait: Callable[[float], bool] | None = None,
    ) -> None:
        if idle_seconds <= 0:
            raise ValueError("idle_seconds must be positive")
        self._cycle = cycle
        self._idle_seconds = idle_seconds
        self._monotonic = monotonic
        self._lock = Lock()
        self._stop_event = Event()
        self._wait = wait or self._stop_event.wait
        self._last_activity = monotonic()
        self._cycle_running = False
        self._worker: Thread | None = None

    @property
    def worker(self) -> Thread | None:
        with self._lock:
            return self._worker

    def mark_activity(self) -> None:
        with self._lock:
            self._last_activity = self._monotonic()

    def run_scheduled_cycle(self) -> bool:
        with self._lock:
            now = self._monotonic()
            if (
                self._cycle_running
                or now - self._last_activity < self._idle_seconds
            ):
                return False
            self._cycle_running = True
            self._last_activity = now
        try:
            self._cycle()
        except Exception:  # noqa: BLE001 - keep-warm must not stop the lifecycle worker
            logger.warning("Canonical V2 idle keep-warm cycle failed", exc_info=True)
        finally:
            with self._lock:
                self._cycle_running = False
        return True

    def start(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._stop_event.clear()
            worker = Thread(
                target=self._run,
                name="canonical-v2-idle-keepwarm",
                daemon=True,
            )
            self._worker = worker
            worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        worker = self.worker
        if worker is not None:
            worker.join(timeout=30.0)

    def _run(self) -> None:
        while not self._wait(self._remaining_idle_seconds()):
            self.run_scheduled_cycle()

    def _remaining_idle_seconds(self) -> float:
        with self._lock:
            elapsed = self._monotonic() - self._last_activity
        return max(0.0, self._idle_seconds - elapsed)


__all__ = ["AdaptiveIdleKeepwarm"]
