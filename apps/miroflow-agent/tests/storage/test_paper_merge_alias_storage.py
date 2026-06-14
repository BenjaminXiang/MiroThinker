from __future__ import annotations

from uuid import UUID

from src.data_agents.storage.postgres.paper_merge_alias import (
    PaperMergeAliasInput,
    resolve_canonical_paper_id,
    upsert_paper_merge_alias,
)


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cursor(self.row)


def test_upsert_paper_merge_alias_rejects_self_alias() -> None:
    conn = _Conn({"alias_id": UUID("00000000-0000-0000-0000-000000000044")})

    try:
        upsert_paper_merge_alias(
            conn,
            PaperMergeAliasInput(
                old_paper_id="PAPER-1",
                canonical_paper_id="PAPER-1",
                merge_reason="test",
            ),
        )
    except ValueError as exc:
        assert "old_paper_id must differ" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("expected ValueError")

    assert conn.calls == []


def test_upsert_paper_merge_alias_writes_queryable_mapping() -> None:
    alias_id = UUID("00000000-0000-0000-0000-000000000045")
    conn = _Conn({"alias_id": alias_id})

    result = upsert_paper_merge_alias(
        conn,
        PaperMergeAliasInput(
            old_paper_id="PAPER-OLD",
            canonical_paper_id="PAPER-CANON",
            merge_reason="title_enrichment_backfill:crossref",
            evidence_source="professor_homepage",
            run_id="11111111-1111-1111-1111-111111111111",
        ),
    )

    assert result.alias_id == alias_id
    sql, params = conn.calls[0]
    assert "ON CONFLICT ON CONSTRAINT uq_paper_merge_alias_old_paper" in sql
    assert params["old_paper_id"] == "PAPER-OLD"
    assert params["canonical_paper_id"] == "PAPER-CANON"


def test_resolve_canonical_paper_id_returns_alias_target_or_original() -> None:
    conn = _Conn({"canonical_paper_id": "PAPER-CANON"})

    assert resolve_canonical_paper_id(conn, "PAPER-OLD") == "PAPER-CANON"
    sql, params = conn.calls[0]
    assert "WITH RECURSIVE merge_chain" in sql
    assert params == {"paper_id": "PAPER-OLD"}

    missing = _Conn(None)
    assert resolve_canonical_paper_id(missing, "PAPER-KEEP") == "PAPER-KEEP"
