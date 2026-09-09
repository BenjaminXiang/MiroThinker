from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Sequence, TextIO

from psycopg import Connection

from src.data_agents.professor.post_full_quality_audit import (
    FieldDefectInput,
    FullRunEvidence,
    PostFullQualityMetrics,
    build_post_full_audit_report,
    format_post_full_audit_report,
)
from src.data_agents.storage.postgres.connection import connect


P7_SELECTED_SEED_IDS = (
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    18,
    19,
    20,
    21,
    24,
    25,
    26,
    27,
    28,
)
BLOCKED_SEED_IDS = (5,)


@dataclass(frozen=True, slots=True)
class PostFullAuditInputs:
    full_runs: list[FullRunEvidence]
    metrics: PostFullQualityMetrics
    field_defects: list[FieldDefectInput]


def load_post_full_audit_inputs(conn: Connection) -> PostFullAuditInputs:
    return PostFullAuditInputs(
        full_runs=_load_latest_full_runs(conn, P7_SELECTED_SEED_IDS),
        metrics=_load_quality_metrics(conn),
        field_defects=[_load_bresar_title_defect(conn)],
    )


def run(
    *,
    conn: Connection,
    output: TextIO = sys.stdout,
    selected_seed_ids: Sequence[int] = P7_SELECTED_SEED_IDS,
    blocked_seed_ids: Sequence[int] = BLOCKED_SEED_IDS,
) -> int:
    inputs = load_post_full_audit_inputs(conn)
    report = build_post_full_audit_report(
        selected_seed_ids=selected_seed_ids,
        full_runs=inputs.full_runs,
        metrics=inputs.metrics,
        blocked_seed_ids=blocked_seed_ids,
        field_defects=inputs.field_defects,
    )
    output.write(format_post_full_audit_report(report))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the read-only P8 post-full Professor quality audit."
    )
    parser.add_argument(
        "--database-url",
        dest="database_url",
        default=None,
        help="Postgres DSN. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--seed-id",
        dest="seed_ids",
        action="append",
        type=int,
        default=None,
        help="Restrict P7 full-run coverage validation to this seed id. May be repeated.",
    )
    parser.add_argument(
        "--blocked-seed-id",
        dest="blocked_seed_ids",
        action="append",
        type=int,
        default=None,
        help="Blocked carryover seed id. Defaults to seed 5. May be repeated.",
    )
    args = parser.parse_args(argv)
    selected_seed_ids = tuple(args.seed_ids) if args.seed_ids else P7_SELECTED_SEED_IDS
    blocked_seed_ids = (
        tuple(args.blocked_seed_ids) if args.blocked_seed_ids else BLOCKED_SEED_IDS
    )
    with connect(args.database_url) as pg_conn:
        return run(
            conn=pg_conn,
            selected_seed_ids=selected_seed_ids,
            blocked_seed_ids=blocked_seed_ids,
        )


def _load_latest_full_runs(
    conn: Connection,
    selected_seed_ids: Sequence[int],
) -> list[FullRunEvidence]:
    rows = conn.execute(
        """
        WITH run_rows AS (
          SELECT
            run_id::text AS run_id,
            COALESCE(
              NULLIF(run_scope->>'seed_id', '')::int,
              CASE WHEN seed_id ~ '^[0-9]+$' THEN seed_id::int ELSE NULL END
            ) AS resolved_seed_id,
            status,
            run_scope->>'trigger_mode' AS trigger_mode,
            run_scope->>'failure_class' AS failure_class,
            items_processed,
            items_failed,
            run_scope->>'written_profile_count' AS written_profile_count,
            run_scope->>'diagnostic_profile_count' AS diagnostic_profile_count,
            finished_at,
            started_at,
            created_at
          FROM pipeline_run
          WHERE run_scope->>'trigger_mode' = 'full'
        ), ranked AS (
          SELECT *,
                 ROW_NUMBER() OVER (
                   PARTITION BY resolved_seed_id
                   ORDER BY COALESCE(finished_at, started_at, created_at) DESC,
                            created_at DESC
                 ) AS rn
            FROM run_rows
           WHERE resolved_seed_id = ANY(%s::int[])
        )
        SELECT *
          FROM ranked
         WHERE rn = 1
         ORDER BY resolved_seed_id
        """,
        (list(selected_seed_ids),),
    ).fetchall()
    return [
        FullRunEvidence(
            seed_id=int(_record_value(row, "resolved_seed_id", 1)),
            run_id=str(_record_value(row, "run_id", 0)),
            status=str(_record_value(row, "status", 2)),
            trigger_mode=str(_record_value(row, "trigger_mode", 3)),
            failure_class=str(_record_value(row, "failure_class", 4)),
            items_processed=int(_record_value(row, "items_processed", 5) or 0),
            items_failed=int(_record_value(row, "items_failed", 6) or 0),
            written_profile_count=_optional_int(
                _record_value(row, "written_profile_count", 7)
            ),
            diagnostic_profile_count=_optional_int(
                _record_value(row, "diagnostic_profile_count", 8)
            ),
        )
        for row in rows
    ]


def _load_quality_metrics(conn: Connection) -> PostFullQualityMetrics:
    canonical_total = int(
        _record_value(
            conn.execute("SELECT COUNT(*) FROM professor").fetchone(),
            "count",
            0,
        )
        or 0
    )
    return PostFullQualityMetrics(
        canonical_total=canonical_total,
        quality_status_distribution=_load_distribution(
            conn,
            """
            SELECT COALESCE(quality_status, 'missing') AS key, COUNT(*) AS count
              FROM professor
             GROUP BY COALESCE(quality_status, 'missing')
             ORDER BY key
            """,
        ),
        run_id_coverage=_load_single_row_counts(
            conn,
            """
            SELECT
              COUNT(*) FILTER (WHERE run_id IS NOT NULL) AS with_run_id,
              COUNT(*) FILTER (WHERE run_id IS NULL) AS missing_run_id
              FROM professor
            """,
        ),
        official_source_page_coverage=_load_single_row_counts(
            conn,
            """
            SELECT
              COUNT(*) FILTER (WHERE sp.page_id IS NOT NULL AND sp.is_official_source) AS with_official_source_page,
              COUNT(*) FILTER (WHERE sp.page_id IS NULL OR NOT COALESCE(sp.is_official_source, false)) AS missing_official_source_page
              FROM professor p
              LEFT JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id
            """,
        ),
        primary_affiliation_coverage=_load_single_row_counts(
            conn,
            """
            SELECT
              COUNT(DISTINCT p.professor_id) FILTER (WHERE a.affiliation_id IS NOT NULL) AS with_primary_affiliation,
              COUNT(DISTINCT p.professor_id) FILTER (WHERE a.affiliation_id IS NULL) AS missing_primary_affiliation
              FROM professor p
              LEFT JOIN professor_affiliation a
                ON a.professor_id = p.professor_id
               AND a.is_primary
               AND a.is_current
            """,
        ),
        fact_coverage=_load_single_row_counts(
            conn,
            """
            SELECT
              COUNT(DISTINCT p.professor_id) FILTER (WHERE pf.fact_id IS NOT NULL) AS with_fact,
              COUNT(DISTINCT p.professor_id) FILTER (WHERE pf.fact_id IS NULL) AS missing_fact
              FROM professor p
              LEFT JOIN professor_fact pf
                ON pf.professor_id = p.professor_id
               AND pf.status = 'active'
            """,
        ),
        duplicate_identity_risk_groups=_load_duplicate_identity_risk_groups(conn),
        open_pipeline_issue_counts=_load_distribution(
            conn,
            """
            SELECT CONCAT_WS(':', COALESCE(reported_by, 'missing_reporter'), COALESCE(stage, 'missing_stage'), COALESCE(severity, 'missing_severity')) AS key,
                   COUNT(*) AS count
              FROM pipeline_issue
             WHERE NOT COALESCE(resolved, false)
             GROUP BY key
             ORDER BY key
            """,
        ),
    )


def _load_bresar_title_defect(conn: Connection) -> FieldDefectInput:
    row = conn.execute(
        """
        SELECT p.professor_id::text AS professor_id,
               p.canonical_name,
               a.title,
               sp.url
          FROM professor p
          LEFT JOIN professor_affiliation a
            ON a.professor_id = p.professor_id
           AND a.is_current
          LEFT JOIN source_page sp
            ON sp.page_id = COALESCE(a.source_page_id, p.primary_official_profile_page_id)
         WHERE p.canonical_name = 'BRESAR, Miha'
            OR sp.url = 'https://sds.cuhk.edu.cn/teacher/2238'
         ORDER BY a.is_primary DESC NULLS LAST, a.created_at DESC NULLS LAST
         LIMIT 1
        """
    ).fetchone()
    return FieldDefectInput(
        defect_id="cuhk-sds-bresar-title",
        professor_id=_optional_str(_record_value(row, "professor_id", 0))
        or "missing",
        canonical_name=_optional_str(_record_value(row, "canonical_name", 1))
        or "BRESAR, Miha",
        source_url=_optional_str(_record_value(row, "url", 3))
        or "https://sds.cuhk.edu.cn/teacher/2238",
        field_name="professor_affiliation.title",
        current_value=_optional_str(_record_value(row, "title", 2)),
        expected_value="助理教授",
    )


def _load_duplicate_identity_risk_groups(conn: Connection) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT canonical_name,
               COUNT(*) AS count,
               ARRAY_AGG(professor_id::text ORDER BY professor_id::text) AS professor_ids
          FROM professor
         WHERE canonical_name IS NOT NULL AND canonical_name <> ''
         GROUP BY canonical_name
        HAVING COUNT(*) > 1
         ORDER BY COUNT(*) DESC, canonical_name
         LIMIT 50
        """
    ).fetchall()
    return [
        {
            "canonical_name": str(_record_value(row, "canonical_name", 0)),
            "count": int(_record_value(row, "count", 1)),
            "professor_ids": list(_record_value(row, "professor_ids", 2) or []),
        }
        for row in rows
    ]


def _load_distribution(conn: Connection, query: str) -> dict[str, int]:
    rows = conn.execute(query).fetchall()
    return {
        str(_record_value(row, "key", 0)): int(_record_value(row, "count", 1) or 0)
        for row in rows
    }


def _load_single_row_counts(conn: Connection, query: str) -> dict[str, int]:
    row = conn.execute(query).fetchone()
    if row is None:
        return {}
    if isinstance(row, dict):
        return {str(key): int(value or 0) for key, value in row.items()}
    return {str(index): int(value or 0) for index, value in enumerate(row)}


def _record_value(record, key: str, index: int):
    if record is None:
        return None
    if isinstance(record, dict):
        return record.get(key)
    return record[index]


def _optional_int(value) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value) -> str | None:
    if value is None:
        return None
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
