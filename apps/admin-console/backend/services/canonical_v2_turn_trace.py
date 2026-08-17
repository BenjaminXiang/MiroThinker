"""Turn-trace journal for Canonical V2 chat turns — one structured record per
turn covering every pipeline stage, so a failed replay turn can be attributed
to its diverging stage from the journal alone.

Companion to ``canonical_v2_access_log`` (which records turn OUTPUTS). This
module records the MIDDLE of the turn: session snapshot, interpretation, lane
counts, gate drops, web-provider outcomes, degradation reason.

Contracts (spec: add-turn-trace-observability):
- one ``TurnTrace`` per turn, emitted on success, degradation, or error;
- journal is append-only JSONL, one file per UTC day, retention-pruned;
- writing is fail-open: a journal failure must never break a chat turn
  (same contract as the access log), but failures are counted, never silent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import re
import secrets
from threading import Lock
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "canonical-v2-turn-trace-v1"

DegradationToken = Literal[
    "none",
    "web-lane-unavailable",
    "no-local-evidence",
    "subject-gate-empty",
    "clarification",
    "error",
]
_VALID_DEGRADATION_TOKENS = frozenset(
    {"none", "web-lane-unavailable", "no-local-evidence",
     "subject-gate-empty", "clarification", "error"}
)

TurnStatus = Literal["ok", "degraded", "error"]

_DAY_FILE_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.jsonl$")
DEFAULT_ROOT_DIR = Path("var") / "turn-trace"
DEFAULT_RETENTION_DAYS = 14


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("turn trace timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class WebLaneOutcome:
    """Per-provider per-view web outcome counters for one turn."""

    provider: str
    view: str
    attempted: int
    errored: int
    timed_out: int
    retried: int
    cache_hit: int
    breaker_state_before: str | None = None
    breaker_state_after: str | None = None


@dataclass(frozen=True, slots=True)
class TurnTrace:
    """One recorded turn; fields grouped per the spec's stage list."""

    trace_id: str
    session_id: str
    turn_ordinal: int
    ts_start: datetime
    ts_end: datetime
    query_raw: str
    question_frame: str
    inferred_domains: tuple[str, ...]
    subject_candidates: tuple[str, ...]
    session_snapshot: dict[str, Any]
    lanes: dict[str, dict[str, int]]
    gate_drops: dict[str, int]
    web_outcomes: tuple[WebLaneOutcome, ...]
    degradation: DegradationToken
    answer_subject: str | None
    citation_count: int
    status: TurnStatus
    error_detail: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "turn_ordinal": self.turn_ordinal,
            "ts_start": _utc_iso(self.ts_start),
            "ts_end": _utc_iso(self.ts_end),
            "query_raw": self.query_raw,
            "question_frame": self.question_frame,
            "inferred_domains": list(self.inferred_domains),
            "subject_candidates": list(self.subject_candidates),
            "session_snapshot": dict(self.session_snapshot),
            "lanes": {lane: dict(counts) for lane, counts in self.lanes.items()},
            "gate_drops": dict(self.gate_drops),
            "web_outcomes": [vars(outcome) for outcome in self.web_outcomes],
            "degradation": self.degradation,
            "answer_subject": self.answer_subject,
            "citation_count": self.citation_count,
            "status": self.status,
            "error_detail": self.error_detail,
        }


class TurnTraceCollector:
    """Accumulates stage events for one turn; thread-safe (lane threads report
    concurrently). Finalizes exactly once into a ``TurnTrace``."""

    def __init__(
        self,
        *,
        session_id: str,
        turn_ordinal: int,
        ts_start: datetime,
    ) -> None:
        self._lock = Lock()
        self._trace_id = "turn:trace:" + secrets.token_urlsafe(12)
        self._session_id = session_id
        self._turn_ordinal = turn_ordinal
        self._ts_start = ts_start
        self._query_raw = ""
        self._question_frame = ""
        self._inferred_domains: tuple[str, ...] = ()
        self._subject_candidates: tuple[str, ...] = ()
        self._session_snapshot: dict[str, Any] = {}
        self._lanes: dict[str, dict[str, int]] = {}
        self._gate_drops: dict[str, int] = {}
        self._web_outcomes: list[WebLaneOutcome] = []
        self._degradation: DegradationToken = "none"
        self._finalized = False

    @property
    def trace_id(self) -> str:
        return self._trace_id

    def set_session_snapshot(
        self,
        *,
        active_anchor_id: str | None,
        active_anchor_name: str | None,
        displayed_id_count: int,
        referent_hint: str | None = None,
    ) -> None:
        payload = {
            "active_anchor_id": active_anchor_id,
            "active_anchor_name": active_anchor_name,
            "displayed_id_count": displayed_id_count,
            "referent_hint": referent_hint,
        }
        with self._lock:
            self._session_snapshot = payload

    def set_interpretation(
        self,
        *,
        query_raw: str,
        question_frame: str,
        inferred_domains: tuple[str, ...],
        subject_candidates: tuple[str, ...],
    ) -> None:
        with self._lock:
            self._query_raw = query_raw
            self._question_frame = question_frame
            self._inferred_domains = tuple(inferred_domains)
            self._subject_candidates = tuple(subject_candidates)

    def record_lane_counts(
        self, lane: str, *, in_: int, retained: int, filtered: int,
    ) -> None:
        with self._lock:
            self._lanes[lane] = {"in": in_, "retained": retained, "filtered": filtered}

    def record_gate_drop(self, gate_name: str, count: int) -> None:
        with self._lock:
            self._gate_drops[gate_name] = (
                self._gate_drops.get(gate_name, 0) + count
            )

    def record_web_outcome(self, outcome: WebLaneOutcome) -> None:
        with self._lock:
            self._web_outcomes.append(outcome)

    def set_degradation(self, token: DegradationToken) -> None:
        if token not in _VALID_DEGRADATION_TOKENS:
            raise ValueError(f"unknown degradation token: {token}")
        with self._lock:
            if token != "none":
                self._degradation = token

    def pending_gate_drops(self) -> dict[str, int]:
        with self._lock:
            return dict(self._gate_drops)

    def finalize(
        self,
        *,
        status: TurnStatus,
        answer_subject: str | None,
        citation_count: int,
        ts_end: datetime,
        error_detail: str | None = None,
    ) -> TurnTrace:
        with self._lock:
            if self._finalized:
                raise RuntimeError("TurnTraceCollector already finalized")
            self._finalized = True
            if status == "error":
                self._degradation = "error"
            return TurnTrace(
                trace_id=self._trace_id,
                session_id=self._session_id,
                turn_ordinal=self._turn_ordinal,
                ts_start=self._ts_start,
                ts_end=ts_end,
                query_raw=self._query_raw,
                question_frame=self._question_frame,
                inferred_domains=self._inferred_domains,
                subject_candidates=self._subject_candidates,
                session_snapshot=dict(self._session_snapshot),
                lanes={lane: dict(counts) for lane, counts in self._lanes.items()},
                gate_drops=dict(self._gate_drops),
                web_outcomes=tuple(self._web_outcomes),
                degradation=self._degradation,
                answer_subject=answer_subject,
                citation_count=citation_count,
                status=status,
                error_detail=error_detail,
            )


class TurnTraceJournalStore:
    """Append-only JSONL journals, one file per UTC day, retention-pruned.

    Fail-open: write/prune failures are logged and counted, never raised.
    """

    def __init__(
        self,
        root_dir: Path | None = None,
        *,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if root_dir is None:
            env_dir = os.getenv("TURN_TRACE_DIR", "").strip()
            root_dir = Path(env_dir) if env_dir else DEFAULT_ROOT_DIR
        self._root_dir = Path(root_dir)
        self._retention_days = retention_days
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = Lock()
        self.write_failure_count = 0

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    def write_turn(self, trace: TurnTrace) -> None:
        try:
            line = json.dumps(trace.to_json_dict(), ensure_ascii=False)
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("turn trace clock must be timezone-aware")
            day = now.astimezone(UTC).date().isoformat()
            with self._lock:
                self._root_dir.mkdir(parents=True, exist_ok=True)
                day_file = self._root_dir / f"{day}.jsonl"
                with day_file.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                self._prune_locked(now)
        except (OSError, ValueError) as exc:
            with self._lock:
                self.write_failure_count += 1
            logger.warning(
                "Canonical V2 turn trace write failed: %s: %s",
                type(exc).__name__,
                exc,
            )

    def _prune_locked(self, now: datetime) -> None:
        cutoff = now.astimezone(UTC).date() - timedelta(days=self._retention_days)
        for entry in self._root_dir.iterdir():
            match = _DAY_FILE_PATTERN.match(entry.name)
            if match is None:
                continue
            file_day = date.fromisoformat("-".join(match.groups()))
            if file_day >= cutoff:
                continue
            try:
                entry.unlink()
            except OSError as exc:
                logger.warning(
                    "turn trace prune failed for %s: %s", entry.name, exc,
                )


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_RETENTION_DAYS",
    "DEFAULT_ROOT_DIR",
    "DegradationToken",
    "TurnStatus",
    "TurnTrace",
    "TurnTraceCollector",
    "TurnTraceJournalStore",
    "WebLaneOutcome",
]
