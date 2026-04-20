# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.16 phase 2 — pipeline_run lifecycle helpers.

V007 added `run_id: uuid` columns to professor / professor_affiliation /
professor_fact / professor_paper_link / paper / patent / source_page and
filled every existing row with a synthetic `legacy_backfill` run. That
migration intentionally left new writes uncoupled: writers accept
`run_id=None` and the column stays NULL until the next periodic backfill.

Phase 2 wires `run_id` through the write path. A pipeline entrypoint:

    run_id = open_pipeline_run(conn, run_kind="professor_v3", run_scope={...})
    try:
        # ... pass run_id to every write_professor_bundle / upsert_paper / ... call
        close_pipeline_run(conn, run_id, status="succeeded", items_processed=N)
    except Exception as exc:
        close_pipeline_run(conn, run_id, status="failed", error_summary={"msg": str(exc)})
        raise

Both helpers are synchronous and transactional-friendly — they just
execute INSERT / UPDATE on the caller's connection so they share the
outer transaction's atomicity. Timestamps use `now()` server-side to
avoid clock-skew issues.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from psycopg import Connection


def open_pipeline_run(
    conn: Connection,
    *,
    run_kind: str,
    run_scope: dict[str, Any] | None = None,
    seed_id: str | None = None,
    parent_run_id: UUID | str | None = None,
    triggered_by: str | None = None,
) -> UUID:
    """Insert a new pipeline_run row and return its generated `run_id`.

    `run_kind` must match the ck_pipeline_run_kind CHECK constraint
    (see V001_init_source_layer.py for the allowed set). `run_scope`
    is a free-form jsonb describing what this run is processing
    (e.g. {"institution": "sustech", "limit": 50}).
    """
    scope_json = json.dumps(run_scope or {}, ensure_ascii=False)
    row = conn.execute(
        """
        INSERT INTO pipeline_run (
            run_kind, run_scope, seed_id, parent_run_id,
            started_at, status, triggered_by
        )
        VALUES (%s, %s::jsonb, %s, %s, now(), 'running', %s)
        RETURNING run_id
        """,
        (run_kind, scope_json, seed_id, parent_run_id, triggered_by),
    ).fetchone()
    if row is None:
        raise RuntimeError("pipeline_run INSERT did not return a row")
    # psycopg returns dict_row by default; accept both shapes
    return row["run_id"] if isinstance(row, dict) else row[0]


def close_pipeline_run(
    conn: Connection,
    run_id: UUID | str,
    *,
    status: str,
    items_processed: int | None = None,
    items_failed: int | None = None,
    error_summary: dict[str, Any] | None = None,
) -> None:
    """Mark a pipeline_run as finished with terminal `status`.

    Status must satisfy the run_status CHECK: 'succeeded' | 'failed' |
    'partial' | 'cancelled'. For in-progress cancellation mid-script use
    'cancelled'; catch-and-rethrow patterns typically call with 'failed'.
    """
    error_json = json.dumps(error_summary, ensure_ascii=False) if error_summary else None
    conn.execute(
        """
        UPDATE pipeline_run
           SET finished_at = now(),
               status = %s,
               items_processed = COALESCE(%s, items_processed),
               items_failed = COALESCE(%s, items_failed),
               error_summary = COALESCE(%s::jsonb, error_summary)
         WHERE run_id = %s
        """,
        (status, items_processed, items_failed, error_json, run_id),
    )
