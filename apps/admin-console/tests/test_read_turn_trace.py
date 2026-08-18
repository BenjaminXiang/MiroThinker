"""Task 1.1.4 — turn-trace reader CLI tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
import json

from scripts import read_turn_trace as reader
from backend.services.canonical_v2_turn_trace import (
    TurnTraceCollector,
    TurnTraceJournalStore,
)

TODAY = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _write_turn(store: TurnTraceJournalStore, ordinal: int, *, degradation: str = "none") -> str:
    collector = TurnTraceCollector(
        session_id="sess-r", turn_ordinal=ordinal, ts_start=TODAY,
    )
    collector.set_interpretation(
        query_raw=f"query-{ordinal}", question_frame="",
        inferred_domains=("company",), subject_candidates=(),
    )
    collector.record_lane_counts("web", in_=5, retained=3, filtered=2)
    if degradation != "none":
        collector.set_degradation(degradation)
    trace = collector.finalize(
        status="degraded" if degradation != "none" else "ok",
        answer_subject="云迹科技",
        citation_count=2,
        ts_end=TODAY + timedelta(seconds=1),
    )
    store.write_turn(trace)
    return trace.trace_id


def _store(tmp_path: Path) -> TurnTraceJournalStore:
    return TurnTraceJournalStore(root_dir=tmp_path, clock=lambda: TODAY)


def test_default_view_lists_turns_with_stage_summary(
    tmp_path: Path, capsys,
) -> None:
    store = _store(tmp_path)
    _write_turn(store, 1)
    _write_turn(store, 2, degradation="web-lane-unavailable")
    assert reader.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "sess-r#1" in out
    assert "sess-r#2" in out
    assert "degradation=web-lane-unavailable" in out
    assert "lanes(web:5/3" in out


def test_session_and_degradation_filters(tmp_path: Path, capsys) -> None:
    store = _store(tmp_path)
    _write_turn(store, 1)
    _write_turn(store, 2, degradation="web-lane-unavailable")
    assert reader.main(
        ["--dir", str(tmp_path), "--degradation", "web-lane-unavailable"]
    ) == 0
    out = capsys.readouterr().out
    assert "sess-r#2" in out
    assert "sess-r#1" not in out


def test_expand_prints_full_record(tmp_path: Path, capsys) -> None:
    store = _store(tmp_path)
    trace_id = _write_turn(store, 1)
    assert reader.main(["--dir", str(tmp_path), "--expand", trace_id]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["trace_id"] == trace_id
    assert payload["lanes"]["web"] == {"in": 5, "retained": 3, "filtered": 2}


def test_missing_day_reports_no_files(tmp_path: Path) -> None:
    assert reader.main(["--dir", str(tmp_path), "--date", "2020-01-01"]) == 1
