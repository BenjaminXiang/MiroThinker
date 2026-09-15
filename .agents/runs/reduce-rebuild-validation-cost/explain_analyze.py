"""Capture EXPLAIN (ANALYZE, TIMING OFF, BUFFERS) for the per-row validator
predicates of the canonical_v2 build path, before and after the fix.

The SQL text is copied verbatim from the validator bodies in
`canonical_v2_alembic/versions/C2_0007_bind_human_review_provenance.py`, with
`NEW.release_id` / `NEW.decision_id` replaced by literals from the database.

Usage: uv run python explain_analyze.py <dbname> <label>
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

DB = sys.argv[1]
LABEL = sys.argv[2]
PORT = sys.argv[3] if len(sys.argv) > 3 else "55458"
OUT_DIR = Path(__file__).resolve().parent

PROBE_DECISION = "field-decision:manifest-sha256:000f"
QUERIES: tuple[tuple[str, str], ...] = (
    (
        "field_human_review_assertion_branch",
        # C2_0007 lines 1170-1180 (block ①), NEW.release_id/decision_id as literals.
        """
        SELECT 1
        FROM knowledge.canonical_decision AS human_decision
        WHERE human_decision.method = 'human_review'
          AND human_decision.human_review_resolution
                ->'review_case'->>'release_id' = %(release_id)s
          AND human_decision.human_review_resolution
                ->'review_case'->>'originating_record_id' = %(decision_id)s
        """,
    ),
    (
        "field_human_review_release_guard",
        # the new release-level guard term
        """
        SELECT 1
        FROM knowledge.canonical_decision AS human_decision
        WHERE human_decision.method = 'human_review'
          AND human_decision.human_review_resolution
                ->'review_case'->>'release_id' = %(release_id)s
        """,
    ),
    (
        "relationship_human_review_assertion_branch",
        # C2_0007 lines 1486-1496 (block ①)
        """
        SELECT 1
        FROM knowledge.relationship_decision AS human_decision
        WHERE human_decision.method = 'human_review'
          AND human_decision.human_review_resolution
                ->'review_case'->>'release_id' = %(release_id)s
          AND human_decision.human_review_resolution
                ->'review_case'->>'originating_record_id' = %(decision_id)s
        """,
    ),
    (
        "identity_human_review_decision_branch",
        # C2_0007 lines 1820-1837 (first EXISTS)
        """
        SELECT 1
        FROM knowledge.identity_decision AS decision
        LEFT JOIN knowledge.identity_decision_context AS context
          ON context.release_id = decision.release_id
         AND context.decision_id = decision.decision_id
        LEFT JOIN knowledge.identity_candidate_verdict AS verdict
          ON verdict.release_id = context.release_id
         AND verdict.decision_run_id = context.decision_run_id
         AND verdict.verdict_id = context.candidate_verdict_id
        WHERE decision.release_id = %(release_id)s
          AND decision.method = 'human_review'
          AND (
              verdict.verdict_id IS NULL
              OR verdict.method <> 'human_review'
              OR verdict.verdict_content->'human_review_resolution'
                 IS DISTINCT FROM decision.human_review_resolution
          )
        """,
    ),
    (
        "field_temporal_assertion_branch",
        # C2_0008 validate_field_temporal_binding (decision state probe + join)
        """
        SELECT decision.state
        FROM knowledge.canonical_decision AS decision
        WHERE decision.release_id = %(release_id)s
          AND decision.decision_id = %(decision_id)s
        """,
    ),
    (
        "domain_inclusion_assertion_owner",
        # C2_0009 validate_domain_inclusion_assertion_owner (owner lookup)
        """
        SELECT 1
        FROM knowledge.current_source_identity_assignment AS assignment
        WHERE assignment.release_id = %(release_id)s
          AND assignment.source_identity_id = %(source_identity_id)s
          AND assignment.canonical_identity_id = %(canonical_identity_id)s
        """,
    ),
)


def main() -> None:
    dsn = f"postgresql://miroflow@127.0.0.1:{PORT}/{DB}"
    lines: list[str] = [f"# EXPLAIN (ANALYZE, TIMING OFF, BUFFERS) — label={LABEL}"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET statement_timeout = '300s'")
        release_id = conn.execute(
            "SELECT release_id FROM knowledge.canonical_decision "
            "GROUP BY release_id ORDER BY count(*) DESC LIMIT 1"
        ).fetchone()[0]
        decision_id = conn.execute(
            "SELECT decision_id FROM knowledge.canonical_decision "
            "WHERE release_id = %s AND method <> 'human_review' "
            "ORDER BY decision_id LIMIT 1",
            (release_id,),
        ).fetchone()[0]
        source_identity_id, canonical_identity_id = conn.execute(
            "SELECT source_identity_id, canonical_identity_id "
            "FROM knowledge.current_source_identity_assignment "
            "WHERE release_id = %s ORDER BY source_identity_id LIMIT 1",
            (release_id,),
        ).fetchone()
        params = {
            "release_id": release_id,
            "decision_id": decision_id,
            "source_identity_id": source_identity_id,
            "canonical_identity_id": canonical_identity_id,
        }
        lines.append(
            f"# database={DB} release_id={release_id} decision_id={decision_id}\n"
        )
        for name, sql in QUERIES:
            plan = conn.execute(
                "EXPLAIN (ANALYZE, TIMING OFF, BUFFERS) " + sql, params
            ).fetchall()
            lines.append(f"\n===== {name} =====")
            lines.extend(row[0] for row in plan)
            lines.append("")
    report = "\n".join(lines)
    path = OUT_DIR / f"explain-analyze-{LABEL}.txt"
    path.write_text(report + "\n")
    print(report)
    print(f"\nwritten: {path}")


if __name__ == "__main__":
    main()
