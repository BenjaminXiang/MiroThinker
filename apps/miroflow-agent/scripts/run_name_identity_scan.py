# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.17 — rescan stored canonical_name_en values with the name gate.

The script is dry-run by default. Use ``--apply`` to insert ``pipeline_issue``
rows and optionally clear obviously wrong ``canonical_name_en`` values.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings
from src.data_agents.professor.name_identity_gate import (
    NameIdentityCandidate,
    batch_verify_name_identity,
)
from src.data_agents.storage.postgres.connection import resolve_dsn
_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_17_scan"
DESCRIPTION_TEMPLATE = (
    "canonical_name_en rejected for {canonical_name}: {candidate_name_en}"
)


@dataclass(frozen=True, slots=True)
class _ProfessorRow:
    professor_id: str
    canonical_name: str
    canonical_name_en: str
    institution: str | None
    source_url: str | None


@dataclass
class _ScanStats:
    examined: int = 0
    rejected: int = 0
    issues_inserted: int = 0
    clear_updates: int = 0
    would_clear: int = 0


def _build_llm_settings() -> tuple[object, str]:
    """Return (openai-compatible client, model string) using shared LLM profile resolver."""
    from openai import OpenAI

    settings = resolve_professor_llm_settings("gemma4")
    api_key = settings.get("local_llm_api_key") or "EMPTY"
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=api_key,
    )
    return client, settings["local_llm_model"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rescan professor.canonical_name_en with the Round 7.17 gate."
    )
    parser.add_argument(
        "--database-url",
        help="Postgres DSN. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--institution",
        help="Only scan professors whose primary institution matches this value.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Insert pipeline_issue rows (default is dry-run).",
    )
    parser.add_argument(
        "--confirm-real-db",
        action="store_true",
        help="Required if the DSN targets miroflow_real.",
    )
    parser.add_argument(
        "--auto-clear-threshold",
        type=float,
        default=None,
        help="If 1 - confidence >= threshold, also clear canonical_name_en.",
    )
    return parser.parse_args()


def _load_rows(
    conn: psycopg.Connection, *, institution: str | None
) -> list[_ProfessorRow]:
    params: list[object] = []
    where = [
        "p.canonical_name IS NOT NULL",
        "btrim(p.canonical_name) <> ''",
        "p.canonical_name_en IS NOT NULL",
        "btrim(p.canonical_name_en) <> ''",
    ]
    if institution:
        where.append("pa.institution = %s")
        params.append(institution)

    rows = conn.execute(
        f"""
        SELECT p.professor_id,
               p.canonical_name,
               p.canonical_name_en,
               pa.institution,
               sp.url AS source_url
          FROM professor p
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id = p.professor_id
           AND pa.is_primary = true
          LEFT JOIN source_page sp
            ON sp.page_id = p.primary_official_profile_page_id
         WHERE {" AND ".join(where)}
         ORDER BY COALESCE(pa.institution, ''), p.professor_id
        """,
        params,
    ).fetchall()
    return [
        _ProfessorRow(
            professor_id=row["professor_id"],
            canonical_name=row["canonical_name"],
            canonical_name_en=row["canonical_name_en"],
            institution=row["institution"],
            source_url=row["source_url"],
        )
        for row in rows
    ]


def _should_auto_clear(
    decision, *, threshold: float | None
) -> bool:
    if threshold is None or decision.error is not None:
        return False
    return (1.0 - decision.confidence) >= threshold


def _issue_snapshot(row: _ProfessorRow, decision) -> dict[str, object]:
    return {
        "type": "name_extraction_report",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "professor": {
            "professor_id": row.professor_id,
            "canonical_name": row.canonical_name,
            "canonical_name_en": row.canonical_name_en,
            "institution": row.institution,
            "source_url": row.source_url,
        },
        "gate_decision": {
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
            "error": decision.error,
        },
    }


def _insert_issue(
    conn: psycopg.Connection,
    *,
    row: _ProfessorRow,
    decision,
) -> int:
    description = DESCRIPTION_TEMPLATE.format(
        canonical_name=row.canonical_name,
        candidate_name_en=row.canonical_name_en,
    )
    snapshot = json.dumps(_issue_snapshot(row, decision), ensure_ascii=False)
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id,
            institution,
            stage,
            severity,
            description,
            evidence_snapshot,
            reported_by
        )
        VALUES (%s, %s, 'name_extraction', 'medium', %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            row.professor_id,
            row.institution,
            description,
            snapshot,
            _REPORTED_BY,
        ),
    )
    return cursor.rowcount


def _clear_name_en(conn: psycopg.Connection, *, professor_id: str) -> int:
    cursor = conn.execute(
        """
        UPDATE professor
           SET canonical_name_en = NULL
         WHERE professor_id = %s
        """,
        (professor_id,),
    )
    return cursor.rowcount


def main() -> int:
    args = _parse_args()
    if (
        args.auto_clear_threshold is not None
        and not 0.0 <= args.auto_clear_threshold <= 1.0
    ):
        print("--auto-clear-threshold must be between 0 and 1", file=sys.stderr)
        return 2

    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print(
            "Refusing to scan miroflow_real without --confirm-real-db.",
            file=sys.stderr,
        )
        return 2

    llm_client, llm_model = _build_llm_settings()
    stats = _ScanStats()

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        rows = _load_rows(conn, institution=args.institution)
        candidates = [
            NameIdentityCandidate(
                canonical_name=row.canonical_name,
                candidate_name_en=row.canonical_name_en,
                source_url=row.source_url,
            )
            for row in rows
        ]
        decisions = batch_verify_name_identity(
            candidates,
            llm_client=llm_client,
            llm_model=llm_model,
        )

        for row, decision in zip(rows, decisions, strict=True):
            stats.examined += 1
            if decision.accepted:
                continue

            stats.rejected += 1
            should_clear = _should_auto_clear(
                decision, threshold=args.auto_clear_threshold
            )
            if args.apply:
                stats.issues_inserted += _insert_issue(conn, row=row, decision=decision)
                if should_clear:
                    stats.clear_updates += _clear_name_en(
                        conn, professor_id=row.professor_id
                    )
            elif should_clear:
                stats.would_clear += 1

        if not args.apply:
            conn.rollback()

    print(f"Examined: {stats.examined}")
    print(f"Rejected: {stats.rejected}")
    print(f"Apply mode: {args.apply}")
    print(f"Pipeline issues inserted: {stats.issues_inserted}")
    if args.apply:
        print(f"canonical_name_en cleared: {stats.clear_updates}")
    else:
        print(f"Would clear canonical_name_en: {stats.would_clear}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
