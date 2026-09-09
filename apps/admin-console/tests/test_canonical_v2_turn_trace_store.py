"""Unit tests for the Canonical V2 turn-trace model, collector, and journal.

RED-first per .agents/runs/add-turn-trace-observability/verification-contract.md
(unit-level TDD is permitted for these deterministic pieces).
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.services.canonical_v2_turn_trace import (
    TurnTrace,
    TurnTraceCollector,
    TurnTraceJournalStore,
)


def _fixed_start() -> datetime:
    return datetime(2026, 8, 18, 12, 0, 0, tzinfo=UTC)


def _make_collector(session_id: str = "sess-1") -> TurnTraceCollector:
    collector = TurnTraceCollector(
        session_id=session_id,
        turn_ordinal=2,
        ts_start=_fixed_start(),
    )
    collector.set_session_snapshot(
        active_anchor_id="prof:123",
        active_anchor_name="张三",
        displayed_id_count=5,
        referent_hint="该中心",
    )
    collector.set_interpretation(
        query_raw="该中心有哪些论文",
        question_frame="professor-paper",
        inferred_domains=("professor", "paper"),
        subject_candidates=("张三", "李四"),
    )
    return collector


class TestTurnTraceRecord:
    def test_collector_finalizes_all_stages_into_one_record(self) -> None:
        collector = _make_collector()
        collector.record_lane_counts("local", in_=12, retained=9, filtered=3)
        collector.record_lane_counts("web", in_=8, retained=4, filtered=4)
        collector.record_gate_drop("web_subject_consistency", 3)
        collector.record_web_outcome(
            provider="bocha-v1",
            view="view-1",
            attempted=2,
            errored=1,
            timed_out=0,
            retried=1,
            cache_hit=0,
        )
        collector.set_degradation("web-lane-unavailable")
        trace = collector.finalize(
            status="degraded",
            answer_subject="张三",
            citation_count=3,
            ts_end=_fixed_start() + timedelta(seconds=2),
        )
        assert isinstance(trace, TurnTrace)
        assert trace.session_id == "sess-1"
        assert trace.turn_ordinal == 2
        assert trace.session_snapshot["active_anchor_name"] == "张三"
        assert trace.lanes["local"] == {"in": 12, "retained": 9, "filtered": 3}
        assert trace.gate_drops == {"web_subject_consistency": 3}
        assert trace.web_outcomes[0].provider == "bocha-v1"
        assert trace.degradation == "web-lane-unavailable"
        assert trace.answer_subject == "张三"
        assert trace.citation_count == 3
        assert trace.status == "degraded"

    def test_trace_serializes_to_one_json_line(self) -> None:
        collector = _make_collector()
        collector.record_web_outcome(
            provider="bocha-v1",
            view="view-1",
            attempted=1,
            errored=1,
            timed_out=0,
            retried=0,
            cache_hit=0,
            breaker_state_before="closed",
            breaker_state_after="open",
        )
        trace = collector.finalize(
            status="ok",
            answer_subject=None,
            citation_count=0,
            ts_end=_fixed_start() + timedelta(milliseconds=800),
        )
        payload = trace.to_json_dict()
        line = json.dumps(payload, ensure_ascii=False)
        assert "\n" not in line
        restored = json.loads(line)
        assert restored["degradation"] == "none"
        assert restored["status"] == "ok"
        # Slotted WebLaneOutcome must serialize explicitly (vars() fails).
        assert restored["web_outcomes"][0]["breaker_state_after"] == "open"

    def test_unknown_degradation_token_rejected(self) -> None:
        collector = _make_collector()
        with pytest.raises(ValueError):
            collector.set_degradation("made-up-token")

    def test_finalize_twice_raises(self) -> None:
        collector = _make_collector()
        collector.finalize(
            status="ok", answer_subject=None, citation_count=0,
            ts_end=_fixed_start(),
        )
        with pytest.raises(RuntimeError):
            collector.finalize(
                status="ok", answer_subject=None, citation_count=0,
                ts_end=_fixed_start(),
            )


class TestCollectorThreadSafety:
    def test_concurrent_gate_drops_all_counted(self) -> None:
        collector = _make_collector()
        barrier = threading.Barrier(4)

        def bump() -> None:
            barrier.wait()
            for _ in range(50):
                collector.record_gate_drop("web_subject_consistency", 1)

        threads = [threading.Thread(target=bump) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert collector.pending_gate_drops() == {"web_subject_consistency": 200}


class TestTurnTraceJournalStore:
    def _store(
        self, root: Path, retention_days: int = 14,
        clock: "datetime | None" = None,
    ) -> TurnTraceJournalStore:
        return TurnTraceJournalStore(
            root_dir=root, retention_days=retention_days,
            clock=clock or _fixed_start,
        )

    def _trace_for(self, ordinal: int) -> TurnTrace:
        collector = TurnTraceCollector(
            session_id="sess-j", turn_ordinal=ordinal, ts_start=_fixed_start(),
        )
        return collector.finalize(
            status="ok", answer_subject=None, citation_count=0,
            ts_end=_fixed_start() + timedelta(seconds=1),
        )

    def test_appends_jsonl_lines_under_day_file(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        store.write_turn(self._trace_for(1))
        store.write_turn(self._trace_for(2))
        day_file = tmp_path / "2026-08-18.jsonl"
        assert day_file.is_file()
        lines = day_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["turn_ordinal"] == 1
        assert json.loads(lines[1])["turn_ordinal"] == 2

    def test_day_rollover_creates_new_file(self, tmp_path: Path) -> None:
        times = {"now": _fixed_start()}

        def clock() -> datetime:
            return times["now"]

        store = self._store(tmp_path, clock=clock)
        store.write_turn(self._trace_for(1))
        times["now"] = _fixed_start() + timedelta(days=1)
        store.write_turn(self._trace_for(2))
        assert (tmp_path / "2026-08-18.jsonl").is_file()
        assert (tmp_path / "2026-08-19.jsonl").is_file()

    def test_prunes_files_older_than_retention(self, tmp_path: Path) -> None:
        store = self._store(tmp_path, retention_days=7)
        stale = tmp_path / "2026-08-01.jsonl"
        stale.write_text("{}\n", encoding="utf-8")
        keep = tmp_path / "2026-08-15.jsonl"
        keep.write_text("{}\n", encoding="utf-8")
        store.write_turn(self._trace_for(1))
        assert not stale.exists()
        assert keep.exists()

    def test_non_day_files_never_pruned(self, tmp_path: Path) -> None:
        store = self._store(tmp_path, retention_days=7)
        unrelated = tmp_path / "notes.txt"
        unrelated.write_text("keep me", encoding="utf-8")
        store.write_turn(self._trace_for(1))
        assert unrelated.exists()

    def test_write_failure_is_fail_open_and_counted(
        self, tmp_path: Path,
    ) -> None:
        blocker = tmp_path / "turn-trace"
        blocker.write_text("a file, not a dir", encoding="utf-8")
        store = self._store(blocker)
        store.write_turn(self._trace_for(1))  # must not raise
        assert store.write_failure_count == 1

    def test_default_root_from_env(self, tmp_path: Path, monkeypatch) -> None:
        env_dir = tmp_path / "from-env"
        monkeypatch.setenv("TURN_TRACE_DIR", str(env_dir))
        store = TurnTraceJournalStore()
        assert store.root_dir == env_dir
