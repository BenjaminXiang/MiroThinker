"""Embedding (vector) lane resilience: a short consecutive-failure breaker.

One provider, one lane: the vector lane depends on a single remote embedding
endpoint. When that endpoint is unreachable from the serving host — a customer
site behind a firewall the school network cannot reach — the lane fails on every
turn, and each attempt costs a full connect/read wait.

This breaker converts "fail on every turn" into "fail twice, then stay out of
the way until the window closes". State lives in the process, shared by the two
consumers of the same embedding adapter:

* the vector lane reads, which must report the lane as unavailable instead of
  killing the turn, and its outer wait expiry (``note_lane_timeout``) counts as
  one more transport failure;
* the provider keep-warm cycle, which must not pay for a provider it knows is
  down.

Only *transport* failures count. Integrity failures of the embedding result stay
where they are (``_ValidatingEmbeddingAdapter``), because a wrong-dimension or
non-finite vector is not a reason to stop asking the provider.
"""

from __future__ import annotations

from datetime import UTC, datetime
import threading
from typing import Any

#: Consecutive transport failures that open the breaker. Two is enough to tell a
#: dead endpoint from a single lost packet, and small enough that a customer box
#: stops paying the lane's wait after two turns.
BREAKER_FAILURE_THRESHOLD = 2
#: How long the lane stays out. Long enough to cover an operator restart of the
#: embedding server, short enough that the lane comes back on its own.
BREAKER_WINDOW_SECONDS = 300.0


class EmbeddingLaneBreaker:
    """Consecutive-failure breaker for the embedding endpoint (one lane)."""

    def __init__(
        self,
        *,
        failure_threshold: int = BREAKER_FAILURE_THRESHOLD,
        window_seconds: float = BREAKER_WINDOW_SECONDS,
        clock: Any = None,
    ) -> None:
        self._failure_threshold = max(1, int(failure_threshold))
        self._window_seconds = max(0.0, float(window_seconds))
        self._clock: Any = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._state = "closed"
        self._failures = 0
        self._opened_at: Any = None
        self._reason: str | None = None

    def state(self, lane: str = "vector") -> str:
        with self._lock:
            return self._state

    def reason(self, lane: str = "vector") -> str | None:
        with self._lock:
            return self._reason

    def attempt_allowed(self, lane: str = "vector") -> tuple[bool, str]:
        """May a real provider call be issued now? Returns (allowed, state)."""

        with self._lock:
            if self._state != "open":
                return True, self._state
            opened_at = self._opened_at
            elapsed = (
                (self._clock() - opened_at).total_seconds()
                if opened_at is not None
                else 0.0
            )
            if elapsed >= self._window_seconds:
                self._state = "probe"
                return True, "probe"
            return False, "open"

    def record(
        self, lane: str = "vector", *, ok: bool, reason: str | None = None
    ) -> str:
        """Record one attempt outcome; returns the state after recording."""

        with self._lock:
            if ok:
                self._failures = 0
                self._state = "closed"
                self._opened_at = None
                self._reason = None
                return self._state
            self._failures += 1
            if reason:
                self._reason = reason
            if self._state == "probe" or self._failures >= self._failure_threshold:
                self._state = "open"
                self._opened_at = self._clock()
            return self._state

    def note_lane_timeout(self, lane: str = "vector") -> None:
        """The lane's outer wait expired: the provider did not answer in budget.

        The abandoned call records its own failure when it finally returns; this
        keeps the count tied to what a user actually waited for, so a black-holed
        route opens the breaker after two turns instead of two times the
        provider's own (much longer) request timeout.
        """

        self.record(reason="timeout", ok=False)


_BREAKER = EmbeddingLaneBreaker()


def embedding_lane_breaker() -> EmbeddingLaneBreaker:
    """The process-scoped breaker shared by the lane read and the keep-warm."""

    return _BREAKER


def reset_embedding_lane_breaker() -> None:
    """Replace the process-scoped breaker (tests, and a fresh scratch boot)."""

    global _BREAKER
    _BREAKER = EmbeddingLaneBreaker()


__all__ = [
    "BREAKER_FAILURE_THRESHOLD",
    "BREAKER_WINDOW_SECONDS",
    "EmbeddingLaneBreaker",
    "embedding_lane_breaker",
    "reset_embedding_lane_breaker",
]
