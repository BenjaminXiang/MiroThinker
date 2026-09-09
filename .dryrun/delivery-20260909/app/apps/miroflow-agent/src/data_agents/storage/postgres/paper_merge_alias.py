from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PaperMergeAliasInput:
    old_paper_id: str
    canonical_paper_id: str
    merge_reason: str
    evidence_source: str | None = None
    run_id: UUID | str | None = None


@dataclass(frozen=True, slots=True)
class PaperMergeAliasUpsertResult:
    alias_id: UUID | str


def upsert_paper_merge_alias(
    conn: Any,
    alias: PaperMergeAliasInput,
) -> PaperMergeAliasUpsertResult:
    old_paper_id = alias.old_paper_id.strip()
    canonical_paper_id = alias.canonical_paper_id.strip()
    merge_reason = alias.merge_reason.strip()
    if not old_paper_id:
        raise ValueError("old_paper_id is required")
    if not canonical_paper_id:
        raise ValueError("canonical_paper_id is required")
    if old_paper_id == canonical_paper_id:
        raise ValueError("old_paper_id must differ from canonical_paper_id")
    if not merge_reason:
        raise ValueError("merge_reason is required")

    row = conn.execute(
        """
        INSERT INTO paper_merge_alias (
            old_paper_id,
            canonical_paper_id,
            merge_reason,
            evidence_source,
            run_id
        )
        VALUES (
            %(old_paper_id)s,
            %(canonical_paper_id)s,
            %(merge_reason)s,
            %(evidence_source)s,
            %(run_id)s
        )
        ON CONFLICT ON CONSTRAINT uq_paper_merge_alias_old_paper
        DO UPDATE
           SET canonical_paper_id = EXCLUDED.canonical_paper_id,
               merge_reason = EXCLUDED.merge_reason,
               evidence_source = COALESCE(
                   EXCLUDED.evidence_source,
                   paper_merge_alias.evidence_source
               ),
               run_id = COALESCE(EXCLUDED.run_id, paper_merge_alias.run_id),
               updated_at = now()
        RETURNING alias_id
        """,
        {
            "old_paper_id": old_paper_id,
            "canonical_paper_id": canonical_paper_id,
            "merge_reason": merge_reason,
            "evidence_source": _optional_clean(alias.evidence_source),
            "run_id": alias.run_id,
        },
    ).fetchone()
    return PaperMergeAliasUpsertResult(alias_id=_row_value(row, "alias_id", 0))


def resolve_canonical_paper_id(conn: Any, paper_id: str) -> str:
    normalized_paper_id = paper_id.strip()
    if not normalized_paper_id:
        raise ValueError("paper_id is required")
    row = conn.execute(
        """
        WITH RECURSIVE merge_chain AS (
          SELECT old_paper_id,
                 canonical_paper_id,
                 1 AS depth
            FROM paper_merge_alias
           WHERE old_paper_id = %(paper_id)s
          UNION ALL
          SELECT alias.old_paper_id,
                 alias.canonical_paper_id,
                 merge_chain.depth + 1 AS depth
            FROM paper_merge_alias alias
            JOIN merge_chain
              ON alias.old_paper_id = merge_chain.canonical_paper_id
           WHERE merge_chain.depth < 10
        )
        SELECT canonical_paper_id
          FROM merge_chain
         ORDER BY depth DESC
         LIMIT 1
        """,
        {"paper_id": normalized_paper_id},
    ).fetchone()
    if row is None:
        return normalized_paper_id
    return str(_row_value(row, "canonical_paper_id", 0))


def _optional_clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError):
        return row[index]
