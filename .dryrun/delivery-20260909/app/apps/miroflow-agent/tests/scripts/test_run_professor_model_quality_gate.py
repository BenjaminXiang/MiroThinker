# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from argparse import Namespace

from scripts.run_professor_model_quality_gate import (
    _accumulate,
    _base_only_result,
    _empty_summary,
    _worker_slot,
)
import scripts.run_professor_model_quality_gate as script


def test_base_only_keeps_ready_candidate_for_model_gate() -> None:
    result = _base_only_result("PROF-1", "ready")

    assert result.base_quality_status == "ready"
    assert result.final_quality_status == "needs_review"
    assert result.model_called is False
    assert result.skip_reason == "base_ready_requires_model"


def test_base_only_preserves_non_ready_status_for_writeback() -> None:
    result = _base_only_result("PROF-1", "needs_enrichment")

    assert result.base_quality_status == "needs_enrichment"
    assert result.final_quality_status == "needs_enrichment"
    assert result.model_called is False
    assert result.skip_reason == "base_gate_needs_enrichment"


def test_accumulate_tracks_ready_candidates_separately() -> None:
    args = Namespace(
        write=False,
        worker_count=1,
        worker_index=0,
        limit=10,
        include_ready=False,
        base_only=True,
    )
    summary = _empty_summary(
        args=args,
        model="base-only",
        llm_profile="base-only",
        checkpoint_path=__file__,
        run_id=None,
        selected=1,
    )

    _accumulate(
        summary,
        {
            "status": "processed",
            "model_called": False,
            "wrote": False,
            "final_quality_status": "needs_review",
            "skip_reason": "base_ready_requires_model",
            "usage": {},
        },
    )

    assert summary["processed"] == 1
    assert summary["skipped_base"] == 1
    assert summary["ready_candidate"] == 1
    assert summary["needs_review"] == 1


def test_worker_slot_is_stable_and_bounded() -> None:
    first = [_worker_slot(f"PROF-{idx}", 4) for idx in range(20)]
    second = [_worker_slot(f"PROF-{idx}", 4) for idx in range(20)]

    assert first == second
    assert all(0 <= slot < 4 for slot in first)
    assert len(set(first)) > 1


def test_run_stops_after_provider_billing_error(monkeypatch, tmp_path) -> None:
    class FakeConn:
        def close(self) -> None:
            pass

    processed: list[str] = []
    checkpoint = tmp_path / "checkpoint.jsonl"
    args = Namespace(
        database_url="postgresql://example",
        write=False,
        limit=3,
        offset=0,
        worker_count=1,
        worker_index=0,
        resume=None,
        checkpoint=checkpoint,
        llm_profile="deepseek-v4-pro",
        model=None,
        timeout=1.0,
        max_retries=0,
        sleep=0.0,
        confidence_threshold=0.75,
        base_only=False,
        include_ready=False,
    )

    monkeypatch.setattr(script, "resolve_dsn", lambda _dsn=None: "postgresql://example")
    monkeypatch.setattr(
        script,
        "resolve_professor_llm_settings",
        lambda *_args, **_kwargs: {
            "llm_profile": "deepseek-v4-pro",
            "local_llm_model": "deepseek-v4-pro",
            "local_llm_base_url": "https://example.test/v1",
            "local_llm_api_key": "key",
        },
    )
    monkeypatch.setattr(script, "_open_llm_client", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(script, "build_non_thinking_extra_body", lambda _model: {})
    monkeypatch.setattr(script.psycopg, "connect", lambda *_args, **_kwargs: FakeConn())
    monkeypatch.setattr(
        script,
        "_select_professor_ids",
        lambda *_args, **_kwargs: ["PROF-1", "PROF-2", "PROF-3"],
    )

    def fake_process_professor(_conn, *, professor_id: str, **_kwargs):
        processed.append(professor_id)
        return {
            "professor_id": professor_id,
            "status": "failed",
            "error": (
                "APIStatusError: Error code: 402 - "
                "{'error': {'message': 'Insufficient Balance'}}"
            ),
        }

    monkeypatch.setattr(script, "_process_professor", fake_process_professor)

    summary = script.run(args)

    assert processed == ["PROF-1"]
    assert summary["failed"] == 1
    assert summary["stopped_early"] is True
    assert "Insufficient Balance" in summary["provider_billing_error"]
    assert len(checkpoint.read_text(encoding="utf-8").splitlines()) == 1
