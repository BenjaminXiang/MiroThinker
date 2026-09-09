"""Cross-layer turn-trace propagation for Canonical V2 serving.

The admin-console chat adapter owns the per-turn ``TurnTraceCollector``; the
serving layer (this package) must not import admin-console code, and every
frozen execution interface (``LaneRequest`` call, adapter constructors) must
stay signature-exact. The bridge is therefore a context-local reporter:

- the chat adapter sets the reporter for the duration of one turn;
- serving code reads it via ``current_turn_trace()`` and duck-calls the
  methods below (absent reporter = no-op, so build/isolated paths are
  untouched);
- executor threads do NOT inherit the context — callers that fan out to
  threads must read ``current_turn_trace()`` on the submitting thread and pass
  the reporter down explicitly.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Protocol, runtime_checkable


@runtime_checkable
class TurnTraceReporter(Protocol):
    """Structural contract; implemented by the admin-console collector."""

    def record_gate_drop(self, gate_name: str, count: int) -> None: ...

    def record_web_outcome(
        self,
        *,
        provider: str,
        view: str,
        attempted: int,
        errored: int,
        timed_out: int,
        retried: int,
        cache_hit: int,
        breaker_state_before: str | None = None,
        breaker_state_after: str | None = None,
    ) -> None: ...

    def set_degradation(self, token: str) -> None: ...

    def record_lane_counts(
        self, lane: str, *, in_: int, retained: int, filtered: int
    ) -> None: ...


_TURN_TRACE_REPORTER: ContextVar[TurnTraceReporter | None] = ContextVar(
    "canonical_v2_turn_trace_reporter", default=None
)


def set_turn_trace_reporter(reporter: TurnTraceReporter) -> object:
    """Bind the reporter for the current turn; returns the reset token."""
    return _TURN_TRACE_REPORTER.set(reporter)


def reset_turn_trace_reporter(token: object) -> None:
    _TURN_TRACE_REPORTER.reset(token)  # type: ignore[arg-type]


def current_turn_trace() -> TurnTraceReporter | None:
    return _TURN_TRACE_REPORTER.get()


__all__ = [
    "TurnTraceReporter",
    "current_turn_trace",
    "reset_turn_trace_reporter",
    "set_turn_trace_reporter",
]
