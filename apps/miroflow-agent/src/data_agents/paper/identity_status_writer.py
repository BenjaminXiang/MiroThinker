# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Reversible ``paper.identity_status`` writes for the paper identity gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from src.data_agents.paper.title_quality import is_plausible_paper_title
from src.data_agents.storage.postgres.pipeline_run import require_real_run_id

_REPORTED_BY = "paper_identity_scan"
_STAGE = "identity_gate"


@dataclass(frozen=True, slots=True)
class IdentityStatusDecision:
    action: Literal["reject", "no_change"]
    reason: str


@dataclass(frozen=True, slots=True)
class RejectionResult:
    paper_id: str
    identity_updated: bool
    prior_identity_status: str
    issues_filed: int


@dataclass(frozen=True, slots=True)
class RestoreResult:
    paper_id: str
    restored: bool
    prior_identity_status: str | None
    issues_resolved: int


def decide_identity_status_rejection(
    *,
    has_verified_link: bool,
    canonical_source: str,
    title_clean: str | None,
) -> IdentityStatusDecision:
    """Return the conservative row-level identity gate decision.

    Reject only when ALL hold: no verified professor link, prof-page-only
    discovery, and a plausible (non-garbage) title. Garbage-title rows are
    left ``unverified`` for parser cleanup rather than mislabeled rejected.
    """
    if has_verified_link or canonical_source != "prof_page_only":
        return IdentityStatusDecision(action="no_change", reason="guard_not_met")
    if not is_plausible_paper_title(title_clean):
        return IdentityStatusDecision(action="no_change", reason="implausible_title")
    return IdentityStatusDecision(
        action="reject",
        reason="no_verified_professor_link_for_prof_page_only_paper",
    )


def apply_identity_status_rejection(
    conn: Any,
    *,
    paper_id: str,
    run_id: str,
    evidence: dict[str, Any],
    prior_identity_status: str,
    stage: str = _STAGE,
    reported_by: str = _REPORTED_BY,
) -> RejectionResult:
    """Set ``paper.identity_status='rejected'`` and file trace evidence.

    The writer intentionally leaves ``quality_status`` untouched. Re-applying
    the same rejection preserves the originally recorded prior status.
    """
    real_run_id = require_real_run_id(
        run_id,
        writer_name="apply_identity_status_rejection",
    )
    existing_issue = _fetch_open_issue(
        conn, paper_id=paper_id, stage=stage, reported_by=reported_by
    )
    recorded_prior = _prior_identity_status(existing_issue) or prior_identity_status

    cursor = conn.execute(
        """
        UPDATE paper
           SET identity_status = 'rejected',
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
           AND identity_status != 'rejected'
        """,
        (real_run_id, paper_id),
    )
    identity_updated = int(getattr(cursor, "rowcount", 0) or 0) > 0

    issues_filed = 0
    if existing_issue is None:
        target = _fetch_issue_target(conn, paper_id=paper_id)
        snapshot = {
            "issue_type": f"paper_{stage}_rejection",
            "stage": stage,
            "paper_id": paper_id,
            "run_id": str(real_run_id),
            "prior_identity_status": recorded_prior,
            "gate_decision": evidence,
        }
        insert_cursor = conn.execute(
            """
            INSERT INTO pipeline_issue (
                professor_id,
                link_id,
                institution,
                stage,
                severity,
                description,
                evidence_snapshot,
                reported_by
            )
            VALUES (%s, %s::uuid, %s, %s, 'medium', %s, %s::jsonb, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                target.get("professor_id"),
                target.get("link_id"),
                target.get("institution") or "paper_identity_status",
                stage,
                f"paper identity status rejected {paper_id}",
                json.dumps(snapshot, ensure_ascii=False, default=str),
                reported_by,
            ),
        )
        issues_filed = int(getattr(insert_cursor, "rowcount", 0) or 0)

    return RejectionResult(
        paper_id=paper_id,
        identity_updated=identity_updated,
        prior_identity_status=str(recorded_prior),
        issues_filed=issues_filed,
    )


def restore_identity_status(conn: Any, *, paper_id: str) -> RestoreResult:
    """Restore the exact prior identity status and resolve the open issue."""
    issue = _fetch_open_issue(conn, paper_id=paper_id)
    if issue is None:
        return RestoreResult(
            paper_id=paper_id,
            restored=False,
            prior_identity_status=None,
            issues_resolved=0,
        )

    prior_status = _prior_identity_status(issue) or "unverified"
    cursor = conn.execute(
        """
        UPDATE paper
           SET identity_status = %s,
               updated_at = now()
         WHERE paper_id = %s
           AND identity_status = 'rejected'
        """,
        (prior_status, paper_id),
    )
    restored = int(getattr(cursor, "rowcount", 0) or 0) > 0

    issue_id = _row_get(issue, "issue_id")
    resolve_cursor = conn.execute(
        """
        UPDATE pipeline_issue
           SET resolved = true,
               resolved_at = now(),
               resolution_notes = %s,
               resolution_round = %s
         WHERE issue_id = %s
           AND resolved = false
        """,
        (
            f"paper identity status restored to {prior_status}",
            "paper_identity_scan_restore",
            issue_id,
        ),
    )
    return RestoreResult(
        paper_id=paper_id,
        restored=restored,
        prior_identity_status=str(prior_status),
        issues_resolved=int(getattr(resolve_cursor, "rowcount", 0) or 0),
    )


def _fetch_open_issue(
    conn: Any,
    *,
    paper_id: str,
    stage: str | None = None,
    reported_by: str | None = None,
) -> dict[str, Any] | None:
    clauses = ["evidence_snapshot->>'paper_id' = %s", "resolved = false"]
    params: list[Any] = [paper_id]
    if stage is not None:
        clauses.append("stage = %s")
        params.append(stage)
    if reported_by is not None:
        clauses.append("reported_by = %s")
        params.append(reported_by)
    row = conn.execute(
        f"""
        SELECT issue_id::text AS issue_id,
               evidence_snapshot
          FROM pipeline_issue
         WHERE {' AND '.join(clauses)}
         ORDER BY reported_at DESC
         LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return dict(row) if row is not None else None


def _fetch_issue_target(conn: Any, *, paper_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT ppl.link_id::text AS link_id,
               ppl.professor_id,
               pa.institution
          FROM professor_paper_link ppl
          JOIN professor prof
            ON prof.professor_id = ppl.professor_id
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id = ppl.professor_id
           AND pa.is_primary = true
         WHERE ppl.paper_id = %s
         ORDER BY CASE ppl.link_status
                    WHEN 'rejected' THEN 0
                    WHEN 'candidate' THEN 1
                    WHEN 'verified' THEN 2
                    ELSE 3
                  END,
                  ppl.updated_at DESC
         LIMIT 1
        """,
        (paper_id,),
    ).fetchone()
    if row is None:
        return {"link_id": None, "professor_id": None, "institution": "paper_identity_status"}
    return dict(row)


def _prior_identity_status(issue: dict[str, Any] | None) -> str | None:
    if issue is None:
        return None
    snapshot = _snapshot(issue)
    prior = snapshot.get("prior_identity_status")
    return str(prior) if prior else None


def _snapshot(issue: dict[str, Any]) -> dict[str, Any]:
    raw = _row_get(issue, "evidence_snapshot") or {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _row_get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, TypeError):
        return None
