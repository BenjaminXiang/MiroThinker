from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import UUID

import pytest

from scripts.run_professor_fact_backfill import _open_llm_client, main
from src.data_agents.professor.fact_extraction import (
    ExtractedProfessorFact,
    run_professor_fact_backfill,
)


class _FakeConn:
    def __init__(self) -> None:
        self.rows = [
            {
                "professor_id": "PROF-OK",
                "canonical_name": "OK Professor",
                "profile_raw_text": "OK raw text",
                "profile_summary": None,
                "primary_official_profile_page_id": UUID(
                    "11111111-1111-1111-1111-111111111111"
                ),
            },
            {
                "professor_id": "PROF-FAIL",
                "canonical_name": "Fail Professor",
                "profile_raw_text": "Fail raw text",
                "profile_summary": None,
                "primary_official_profile_page_id": UUID(
                    "22222222-2222-2222-2222-222222222222"
                ),
            },
        ]
        self.persisted: list[str] = []
        self.summaries: list[str] = []
        self.re_evaluated: list[str] = []
        self.issues: list[tuple[str, str]] = []
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_runner_isolates_professor_failures_and_re_evaluates_successes() -> None:
    conn = _FakeConn()

    def extractor(row: dict[str, object]) -> list[ExtractedProfessorFact]:
        if row["professor_id"] == "PROF-FAIL":
            raise RuntimeError("LLM malformed output")
        return [
            ExtractedProfessorFact(
                fact_type="education",
                value_raw="PhD, Example University",
                value_normalized="phd example university",
                evidence_span="PhD, Example University",
                confidence=0.91,
            )
        ]

    def persister(
        conn: _FakeConn,
        *,
        professor_id: str,
        source_page_id: UUID,
        run_id: str,
        facts: list[ExtractedProfessorFact],
    ) -> object:
        del source_page_id, run_id
        conn.persisted.append(professor_id)

        class Report:
            inserted = len(facts)
            updated = 0
            skipped = 0

        return Report()

    def summary_writer(
        conn: _FakeConn,
        row: dict[str, object],
        *,
        run_id: str,
    ) -> bool:
        del run_id
        conn.summaries.append(str(row["professor_id"]))
        return True

    def re_evaluator(conn: _FakeConn, professor_id: str) -> None:
        conn.re_evaluated.append(professor_id)

    def issue_logger(conn: _FakeConn, professor_id: str, error: Exception) -> None:
        conn.issues.append((professor_id, str(error)))

    report = run_professor_fact_backfill(
        conn,
        llm_client=object(),
        llm_model="mock-model",
        run_id="33333333-3333-3333-3333-333333333333",
        extractor=extractor,
        persister=persister,
        summary_writer=summary_writer,
        quality_re_evaluator=re_evaluator,
        issue_logger=issue_logger,
    )

    assert report.processed == 1
    assert report.failed == 1
    assert report.facts_written == 1
    assert report.summaries_written == 1
    assert report.re_evaluated == 1
    assert conn.persisted == ["PROF-OK"]
    assert conn.summaries == ["PROF-OK"]
    assert conn.re_evaluated == ["PROF-OK"]
    assert conn.issues == [("PROF-FAIL", "LLM malformed output")]
    assert conn.commits == 1
    assert conn.rollbacks == 1


def test_open_llm_client_uses_professor_profile_without_proxy_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example.test:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.test:8080")

    before = {
        "HTTP_PROXY": "http://proxy.example.test:8080",
        "HTTPS_PROXY": "http://proxy.example.test:8080",
    }

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(
        "scripts.run_professor_fact_backfill.OpenAI",
        FakeOpenAI,
    )
    monkeypatch.setattr(
        "scripts.run_professor_fact_backfill.resolve_professor_llm_settings",
        lambda profile, include_profile: {
            "local_llm_base_url": "http://localhost:8000/v1",
            "local_llm_api_key": "EMPTY",
            "local_llm_model": "mock-model",
        },
    )

    client, model, extra_body = _open_llm_client("gemma4")

    assert isinstance(client, FakeOpenAI)
    assert client.kwargs["base_url"] == "http://localhost:8000/v1"
    assert client.kwargs["api_key"] == "EMPTY"
    assert client.kwargs["timeout"] == 90.0
    assert client.kwargs["http_client"].trust_env is False
    assert model == "mock-model"
    assert extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert {key: os.environ[key] for key in before} == before


def test_main_dry_run_does_not_open_pipeline_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeConn:
        def close(self) -> None:
            pass

    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setattr(
        "scripts.run_professor_fact_backfill._open_database_connection",
        lambda dsn: FakeConn(),
    )
    monkeypatch.setattr(
        "scripts.run_professor_fact_backfill.preflight_professor_fact_backfill",
        lambda conn: SimpleNamespace(
            total_professors=1,
            eligible_count=1,
            skipped_missing_profile_raw_text=0,
            missing_profile_summary_count=1,
            missing_fact_counts={},
            existing_active_fact_counts={},
        ),
    )
    monkeypatch.setattr(
        "scripts.run_professor_fact_backfill._open_llm_client",
        lambda profile: (object(), "mock-model", {}),
    )

    def fail_open_pipeline_run(*args: object, **kwargs: object) -> UUID:
        raise AssertionError("dry-run must not write pipeline_run")

    monkeypatch.setattr(
        "scripts.run_professor_fact_backfill.open_pipeline_run",
        fail_open_pipeline_run,
    )
    monkeypatch.setattr(
        "scripts.run_professor_fact_backfill.close_pipeline_run",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "scripts.run_professor_fact_backfill.run_professor_fact_backfill",
        lambda *args, **kwargs: SimpleNamespace(
            processed=1,
            skipped=0,
            failed=0,
            facts_written=2,
            summaries_written=0,
            re_evaluated=0,
            errors=[],
        ),
    )

    main(["--dry-run", "--limit", "1"])

    output = capsys.readouterr().out
    assert '"dry_run": true' in output
    assert '"run_id": "00000000-0000-0000-0000-000000000000"' in output
