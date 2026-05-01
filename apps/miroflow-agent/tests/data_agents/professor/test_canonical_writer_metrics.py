from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.data_agents.canonical.professor import Professor
from src.data_agents.professor.canonical_writer import upsert_professor_metrics


def _conn_with_paper_count(count: int) -> MagicMock:
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = {"n": count}
    conn.execute.return_value = cursor
    return conn


def _sql_at(conn: MagicMock, index: int) -> str:
    return " ".join(conn.execute.call_args_list[index].args[0].split())


def _params_at(conn: MagicMock, index: int) -> tuple[object, ...]:
    return conn.execute.call_args_list[index].args[1]


def test_upsert_professor_metrics_writes_openalex_metrics() -> None:
    conn = _conn_with_paper_count(2)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-1",
        h_index=37,
        citation_count=5_000_000_000,
        metrics_source="openalex",
        run_id="00000000-0000-0000-0000-000000000001",
    )

    assert conn.execute.call_count == 2
    assert _params_at(conn, 1) == (
        37,
        5_000_000_000,
        2,
        "openalex",
        "00000000-0000-0000-0000-000000000001",
        "PROF-1",
    )


def test_upsert_professor_metrics_writes_verified_link_only_zero_count() -> None:
    conn = _conn_with_paper_count(0)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-2",
        h_index=None,
        citation_count=None,
        metrics_source="verified_link_only",
        run_id=None,
    )

    assert _params_at(conn, 1) == (
        None,
        None,
        0,
        "verified_link_only",
        None,
        "PROF-2",
    )


def test_upsert_professor_metrics_allows_mixed_source() -> None:
    conn = _conn_with_paper_count(4)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-3",
        h_index=12,
        citation_count=None,
        metrics_source="mixed",
        run_id="run-1",
    )

    assert _params_at(conn, 1) == (12, None, 4, "mixed", "run-1", "PROF-3")


def test_upsert_professor_metrics_all_failure_preserves_old_values() -> None:
    conn = MagicMock()

    upsert_professor_metrics(
        conn,
        professor_id="PROF-4",
        h_index=None,
        citation_count=None,
        metrics_source=None,
        run_id="run-1",
    )

    conn.execute.assert_not_called()


def test_upsert_professor_metrics_rejects_unknown_source() -> None:
    conn = MagicMock()

    with pytest.raises(ValueError, match="invalid metrics_source"):
        upsert_professor_metrics(
            conn,
            professor_id="PROF-5",
            h_index=None,
            citation_count=None,
            metrics_source="google_scholar",
            run_id=None,
        )

    conn.execute.assert_not_called()


def test_upsert_professor_metrics_requires_source_for_openalex_values() -> None:
    conn = MagicMock()

    with pytest.raises(ValueError, match="metrics_source is required"):
        upsert_professor_metrics(
            conn,
            professor_id="PROF-6",
            h_index=1,
            citation_count=None,
            metrics_source=None,
            run_id=None,
        )

    conn.execute.assert_not_called()


def test_upsert_professor_metrics_uses_verified_link_count_sql() -> None:
    conn = _conn_with_paper_count(9)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-7",
        h_index=1,
        citation_count=2,
        metrics_source="openalex",
        run_id=None,
    )

    assert _sql_at(conn, 0) == (
        "SELECT count(*)::int AS n FROM professor_paper_link "
        "WHERE professor_id = %s AND link_status = 'verified'"
    )
    assert _params_at(conn, 0) == ("PROF-7",)


def test_upsert_professor_metrics_skips_merged_professors() -> None:
    conn = _conn_with_paper_count(1)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-8",
        h_index=3,
        citation_count=4,
        metrics_source="openalex",
        run_id=None,
    )

    update_sql = _sql_at(conn, 1)
    assert "identity_status <> 'merged_into'" in update_sql


def test_upsert_professor_metrics_computed_at_not_newer_than_refresh() -> None:
    conn = _conn_with_paper_count(1)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-9",
        h_index=3,
        citation_count=4,
        metrics_source="openalex",
        run_id=None,
    )

    update_sql = _sql_at(conn, 1)
    assert "metrics_computed_at = LEAST(now(), COALESCE(last_refreshed_at, now()))" in update_sql


def test_upsert_professor_metrics_does_not_commit() -> None:
    conn = _conn_with_paper_count(1)

    upsert_professor_metrics(
        conn,
        professor_id="PROF-10",
        h_index=3,
        citation_count=4,
        metrics_source="openalex",
        run_id=None,
    )

    conn.commit.assert_not_called()


def test_professor_model_accepts_metrics_and_rejects_unknown_source() -> None:
    prof = Professor(
        professor_id="PROF-11",
        canonical_name="张三",
        discipline_family="computer_science",
        h_index=0,
        citation_count=0,
        paper_count=0,
        metrics_source="openalex",
    )

    assert prof.h_index == 0
    assert prof.citation_count == 0
    assert prof.paper_count == 0

    with pytest.raises(ValidationError):
        Professor(
            professor_id="PROF-12",
            canonical_name="李四",
            discipline_family="computer_science",
            metrics_source="google_scholar",
        )
