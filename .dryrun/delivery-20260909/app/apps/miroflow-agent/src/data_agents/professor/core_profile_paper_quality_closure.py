"""Seed-scoped closure for Professor core profile and Paper quality."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from psycopg.types.json import Jsonb

from .output_summaries import (
    run_output_summary_backfill,
    select_professors_for_research_vector_refresh,
)
from .quality_gate import (
    evaluate_professor_quality,
    load_professor_canonical_states,
    persist_professor_quality_evaluation,
)

CLOSURE_STAGE_ORDER: tuple[str, ...] = (
    "homepage_paper_ingest",
    "title_enrichment_merge",
    "paper_enrichment",
    "paper_quality_promotion",
    "professor_output_summaries",
    "professor_quality_re_evaluation",
    "index_refresh_selection",
)

_REPORTED_BY = "professor_core_profile_paper_quality_closure"
_APP_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_ROOT = _APP_ROOT / "scripts"


@dataclass(frozen=True, slots=True)
class ClosureContext:
    conn: Any
    seed_id: int
    run_id: str
    trigger_mode: str
    limit: int | None
    professor_ids: tuple[str, ...] = ()
    dsn: str | None = None
    publication_extractor: Any = None


@dataclass(frozen=True, slots=True)
class ClosureStageResult:
    stage: str
    status: str
    counts: Mapping[str, int] = field(default_factory=dict)
    professor_ids: tuple[str, ...] = ()
    paper_ids: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ClosureIssue:
    seed_id: int
    run_id: str
    professor_id: str | None
    stage: str
    reason: str
    severity: str = "high"
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClosureIssueWriteResult:
    inserted: bool
    issue_id: str | None = None


@dataclass(frozen=True, slots=True)
class SeedQualityClosureReport:
    seed_id: int
    run_id: str
    status: str
    ready_promotion_allowed: bool
    stages: tuple[ClosureStageResult, ...] = ()
    stage_counts: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    issues: tuple[ClosureIssue, ...] = ()
    skip_reason: str | None = None
    index_refresh_professor_ids: tuple[str, ...] = ()
    index_refresh_paper_ids: tuple[str, ...] = ()


ClosureStageRunner = Callable[[ClosureContext], ClosureStageResult]
ClosureIssueWriter = Callable[[Any, ClosureIssue], Any]


def should_run_seed_quality_closure(
    *,
    seed_status: str | None,
    trigger_mode: str,
    limit: int | None,
) -> bool:
    return seed_status == "success" and trigger_mode == "full" and limit is None


def run_seed_quality_closure(
    *,
    conn: Any,
    seed_id: int,
    run_id: str,
    trigger_mode: str,
    limit: int | None,
    professor_ids: tuple[str, ...] = (),
    stage_runners: Mapping[str, ClosureStageRunner] | None = None,
    issue_writer: ClosureIssueWriter | None = None,
    dsn: str | None = None,
    publication_extractor: Any = None,
    commit_after_stage: bool = False,
) -> SeedQualityClosureReport:
    """Run the post-seed Professor/Paper quality closure in contract order."""
    if not should_run_seed_quality_closure(
        seed_status="success",
        trigger_mode=trigger_mode,
        limit=limit,
    ):
        return SeedQualityClosureReport(
            seed_id=seed_id,
            run_id=run_id,
            status="skipped",
            ready_promotion_allowed=False,
            skip_reason="sample_or_limited_seed_run",
        )

    context = ClosureContext(
        conn=conn,
        seed_id=seed_id,
        run_id=run_id,
        trigger_mode=trigger_mode,
        limit=limit,
        professor_ids=professor_ids,
        dsn=dsn,
        publication_extractor=publication_extractor,
    )
    runners = dict(stage_runners or build_default_stage_runners())
    write_issue = issue_writer or (
        lambda target_conn, issue: upsert_closure_stage_issue(
            target_conn,
            seed_id=issue.seed_id,
            run_id=issue.run_id,
            professor_id=issue.professor_id,
            stage=issue.stage,
            reason=issue.reason,
            severity=issue.severity,
            evidence=issue.evidence,
        )
    )

    stages: list[ClosureStageResult] = []
    stage_counts: dict[str, Mapping[str, int]] = {}
    issues: list[ClosureIssue] = []
    index_refresh_professor_ids: tuple[str, ...] = ()
    index_refresh_paper_ids: tuple[str, ...] = ()

    for stage in CLOSURE_STAGE_ORDER:
        runner = runners.get(stage)
        if runner is None:
            new_issues = _closure_issues_for_failure(
                context=context,
                stage=stage,
                reason=f"missing closure stage runner: {stage}",
            )
            for issue in new_issues:
                write_issue(conn, issue)
            issues.extend(new_issues)
            reason = new_issues[0].reason if new_issues else "missing stage runner"
            stages.append(ClosureStageResult(stage=stage, status="failed", reason=reason))
            return _closure_report(
                seed_id=seed_id,
                run_id=run_id,
                stages=stages,
                stage_counts=stage_counts,
                issues=issues,
                status="failed",
                index_refresh_professor_ids=index_refresh_professor_ids,
                index_refresh_paper_ids=index_refresh_paper_ids,
            )
        try:
            result = runner(context)
        except Exception as exc:  # noqa: BLE001
            reason = f"{exc.__class__.__name__}: {exc}"
            new_issues = _closure_issues_for_failure(
                context=context,
                stage=stage,
                reason=reason,
            )
            for issue in new_issues:
                write_issue(conn, issue)
            issues.extend(new_issues)
            stages.append(ClosureStageResult(stage=stage, status="failed", reason=reason))
            return _closure_report(
                seed_id=seed_id,
                run_id=run_id,
                stages=stages,
                stage_counts=stage_counts,
                issues=issues,
                status="failed",
                index_refresh_professor_ids=index_refresh_professor_ids,
                index_refresh_paper_ids=index_refresh_paper_ids,
            )

        if result.stage != stage:
            raise ValueError(
                f"closure stage runner returned {result.stage!r}; expected {stage!r}"
            )
        stages.append(result)
        stage_counts[stage] = dict(result.counts)
        if stage == "index_refresh_selection":
            index_refresh_professor_ids = result.professor_ids
            index_refresh_paper_ids = result.paper_ids
        if commit_after_stage:
            commit = getattr(conn, "commit", None)
            if callable(commit):
                commit()
        if result.status == "failed":
            new_issues = _closure_issues_for_failure(
                context=context,
                stage=stage,
                reason=result.reason or f"{stage} failed",
                professor_ids=result.professor_ids or context.professor_ids,
            )
            for issue in new_issues:
                write_issue(conn, issue)
            issues.extend(new_issues)
            return _closure_report(
                seed_id=seed_id,
                run_id=run_id,
                stages=stages,
                stage_counts=stage_counts,
                issues=issues,
                status="failed",
                index_refresh_professor_ids=index_refresh_professor_ids,
                index_refresh_paper_ids=index_refresh_paper_ids,
            )

    return _closure_report(
        seed_id=seed_id,
        run_id=run_id,
        stages=stages,
        stage_counts=stage_counts,
        issues=issues,
        status="success",
        index_refresh_professor_ids=index_refresh_professor_ids,
        index_refresh_paper_ids=index_refresh_paper_ids,
    )


def build_default_stage_runners() -> dict[str, ClosureStageRunner]:
    return {
        "homepage_paper_ingest": _run_homepage_paper_ingest_stage,
        "title_enrichment_merge": _run_title_enrichment_stage,
        "paper_enrichment": _run_paper_enrichment_stage,
        "paper_quality_promotion": _run_paper_quality_promotion_selection_stage,
        "professor_output_summaries": _run_professor_output_summaries_stage,
        "professor_quality_re_evaluation": _run_professor_quality_re_evaluation_stage,
        "index_refresh_selection": _run_index_refresh_selection_stage,
    }


def upsert_closure_stage_issue(
    conn: Any,
    *,
    seed_id: int,
    run_id: str,
    professor_id: str | None,
    stage: str,
    reason: str,
    severity: str = "high",
    evidence: Mapping[str, Any] | None = None,
) -> ClosureIssueWriteResult:
    """Upsert one visible pipeline issue for a failed closure stage."""
    issue_evidence = {
        "issue_type": "professor_core_profile_paper_quality_closure_stage_failed",
        "seed_id": seed_id,
        "run_id": str(run_id),
        "professor_id": professor_id,
        "closure_stage": stage,
        "reason": reason,
        **dict(evidence or {}),
    }
    institution = None if professor_id else f"professor_seed:{seed_id}"
    description = _closure_issue_description(
        seed_id=seed_id,
        professor_id=professor_id,
        stage=stage,
        reason=reason,
    )
    existing = conn.execute(
        """
        SELECT issue_id
          FROM pipeline_issue
         WHERE professor_id IS NOT DISTINCT FROM %s
           AND institution IS NOT DISTINCT FROM %s
           AND stage = 'data_quality_flag'
           AND reported_by = %s
           AND description_hash = md5(%s)
           AND resolved = false
         LIMIT 1
        """,
        (professor_id, institution, _REPORTED_BY, description),
    ).fetchone()
    if existing is not None:
        issue_id = _row_value(existing, "issue_id", 0)
        conn.execute(
            """
            UPDATE pipeline_issue
               SET evidence_snapshot = %s,
                   severity = %s,
                   reported_at = GREATEST(reported_at, now())
             WHERE issue_id = %s
            """,
            (Jsonb(issue_evidence), severity, issue_id),
        )
        return ClosureIssueWriteResult(inserted=False, issue_id=str(issue_id))

    conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, institution, stage, severity,
            description, evidence_snapshot, reported_by
        )
        VALUES (%s, %s, 'data_quality_flag', %s, %s, %s, %s)
        """,
        (
            professor_id,
            institution,
            severity,
            description,
            Jsonb(issue_evidence),
            _REPORTED_BY,
        ),
    )
    return ClosureIssueWriteResult(inserted=True)


def load_professor_ids_for_seed_run(
    conn: Any,
    *,
    seed_id: int,
    run_id: str,
) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT professor_id
          FROM professor
         WHERE run_id = %s
         ORDER BY professor_id
        """,
        (run_id,),
    ).fetchall()
    professor_ids = tuple(str(_row_value(row, "professor_id", 0)) for row in rows)
    if professor_ids:
        return professor_ids

    rows = conn.execute(
        """
        WITH latest_seed_run AS (
            SELECT run_id
              FROM pipeline_run
             WHERE run_kind = 'roster_crawl'
               AND run_scope->>'seed_id' = %s
             ORDER BY started_at DESC
             LIMIT 1
        )
        SELECT professor_id
          FROM professor
         WHERE run_id IN (SELECT run_id FROM latest_seed_run)
         ORDER BY professor_id
        """,
        (str(seed_id),),
    ).fetchall()
    return tuple(str(_row_value(row, "professor_id", 0)) for row in rows)


def _run_homepage_paper_ingest_stage(context: ClosureContext) -> ClosureStageResult:
    from ..paper.homepage_ingest import run_homepage_paper_ingest

    report = run_homepage_paper_ingest(
        context.conn,
        seed_id=context.seed_id,
        publication_extractor=context.publication_extractor,
        include_owned_homepage_pages=True,
    )
    return ClosureStageResult(
        stage="homepage_paper_ingest",
        status="success",
        counts={
            "profs_processed": int(report.profs_processed),
            "papers_linked_total": int(report.papers_linked_total),
            "pipeline_issues_filed": int(report.pipeline_issues_filed),
        },
    )


def _run_title_enrichment_stage(context: ClosureContext) -> ClosureStageResult:
    payload = _run_json_script_stage(
        context,
        "run_paper_title_enrichment_backfill.py",
        ["--seed-id", str(context.seed_id)],
    )
    return ClosureStageResult(
        stage="title_enrichment_merge",
        status="success",
        counts=_int_counts(payload),
    )


def _run_paper_enrichment_stage(context: ClosureContext) -> ClosureStageResult:
    payload = _run_json_script_stage(
        context,
        "run_paper_summary_zh_backfill.py",
        ["--seed-id", str(context.seed_id), "--enrich-doi-metadata"],
    )
    return ClosureStageResult(
        stage="paper_enrichment",
        status="success",
        counts=_int_counts(payload),
    )


def _run_paper_quality_promotion_selection_stage(
    context: ClosureContext,
) -> ClosureStageResult:
    professor_ids = _professor_ids_for_context(context)
    if not professor_ids:
        return ClosureStageResult(
            stage="paper_quality_promotion",
            status="failed",
            reason="no professor ids resolved for seed-scoped paper quality promotion",
        )
    rows = context.conn.execute(
        """
        SELECT COALESCE(p.quality_status, 'needs_enrichment') AS quality_status,
               count(DISTINCT p.paper_id)::int AS n
          FROM professor_paper_link AS ppl
          JOIN paper AS p ON p.paper_id = ppl.paper_id
         WHERE ppl.link_status = 'verified'
           AND ppl.professor_id = ANY(%s)
           AND COALESCE(p.identity_status, 'unverified') NOT IN ('rejected', 'merged')
         GROUP BY COALESCE(p.quality_status, 'needs_enrichment')
        """,
        (list(professor_ids),),
    ).fetchall()
    counts = {
        f"paper_quality_{_row_value(row, 'quality_status', 0)}": int(
            _row_value(row, "n", 1) or 0
        )
        for row in rows
    }
    return ClosureStageResult(
        stage="paper_quality_promotion",
        status="success",
        counts=counts,
    )


def _run_professor_output_summaries_stage(context: ClosureContext) -> ClosureStageResult:
    professor_ids = _professor_ids_for_context(context)
    if not professor_ids:
        return ClosureStageResult(
            stage="professor_output_summaries",
            status="failed",
            reason="no professor ids resolved for seed-scoped output summaries",
        )
    llm_client, llm_model, extra_body = _open_professor_output_summary_llm()
    report = run_output_summary_backfill(
        context.conn,
        run_id=context.run_id,
        llm_client=llm_client,
        llm_model=llm_model,
        dry_run=False,
        professor_ids=professor_ids,
        extra_body=extra_body,
    )
    return ClosureStageResult(
        stage="professor_output_summaries",
        status="success" if report.failed == 0 else "failed",
        counts={
            "eligible": report.eligible,
            "processed": report.processed,
            "skipped": report.skipped,
            "failed": report.failed,
            "paper_summaries_written": report.paper_summaries_written,
            "patent_summaries_written": report.patent_summaries_written,
        },
        professor_ids=report.refresh_professor_ids,
        reason="professor output summaries failed" if report.failed else "",
    )


def _run_professor_quality_re_evaluation_stage(
    context: ClosureContext,
) -> ClosureStageResult:
    professor_ids = _professor_ids_for_context(context)
    if not professor_ids:
        return ClosureStageResult(
            stage="professor_quality_re_evaluation",
            status="failed",
            reason="no professor ids resolved for seed-scoped quality re-evaluation",
        )
    states = load_professor_canonical_states(context.conn, list(professor_ids))
    evaluations = [evaluate_professor_quality(state) for state in states]
    for evaluation in evaluations:
        persist_professor_quality_evaluation(context.conn, evaluation)
    counts: dict[str, int] = {"evaluated": len(evaluations), "written": len(evaluations)}
    for evaluation in evaluations:
        key = f"quality_{evaluation.quality_status}"
        counts[key] = counts.get(key, 0) + 1
    return ClosureStageResult(
        stage="professor_quality_re_evaluation",
        status="success",
        counts=counts,
        professor_ids=professor_ids,
    )


def _run_index_refresh_selection_stage(context: ClosureContext) -> ClosureStageResult:
    professor_scope_ids = _professor_ids_for_context(context)
    if not professor_scope_ids:
        return ClosureStageResult(
            stage="index_refresh_selection",
            status="failed",
            reason="no professor ids resolved for seed-scoped index refresh selection",
        )
    professor_ids = select_professors_for_research_vector_refresh(
        context.conn,
        run_id=context.run_id,
    )
    paper_rows = context.conn.execute(
        """
        SELECT DISTINCT p.paper_id
          FROM professor_paper_link AS ppl
          JOIN paper AS p ON p.paper_id = ppl.paper_id
         WHERE ppl.professor_id = ANY(%s)
           AND p.quality_status = 'ready'
         ORDER BY p.paper_id
        """,
        (list(professor_scope_ids),),
    ).fetchall()
    paper_ids = tuple(str(_row_value(row, "paper_id", 0)) for row in paper_rows)
    return ClosureStageResult(
        stage="index_refresh_selection",
        status="success",
        counts={
            "professors_selected": len(professor_ids),
            "papers_selected": len(paper_ids),
        },
        professor_ids=professor_ids,
        paper_ids=paper_ids,
    )


def _run_json_script_stage(
    context: ClosureContext,
    script_name: str,
    args: list[str],
) -> dict[str, Any]:
    if not context.dsn:
        raise ValueError(f"{script_name} requires dsn")
    env = os.environ.copy()
    env["DATABASE_URL"] = context.dsn
    completed = subprocess.run(
        [sys.executable, str(_SCRIPTS_ROOT / script_name), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{script_name} exited {completed.returncode}: "
            f"{(completed.stderr or completed.stdout).strip()[:1000]}"
        )
    return _parse_json_from_stdout(completed.stdout)


def _parse_json_from_stdout(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        if not line.startswith("{"):
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            return payload
    raise ValueError("stage script did not print a JSON object")


def _open_professor_output_summary_llm():
    from scripts.run_paper_summary_zh_backfill import _open_llm_client

    return _open_llm_client()


def _professor_ids_for_context(context: ClosureContext) -> tuple[str, ...]:
    if context.professor_ids:
        return context.professor_ids
    return load_professor_ids_for_seed_run(
        context.conn,
        seed_id=context.seed_id,
        run_id=context.run_id,
    )


def _int_counts(payload: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, value in payload.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            counts[key] = value
    return counts


def _closure_report(
    *,
    seed_id: int,
    run_id: str,
    stages: list[ClosureStageResult],
    stage_counts: Mapping[str, Mapping[str, int]],
    issues: list[ClosureIssue],
    status: str,
    index_refresh_professor_ids: tuple[str, ...],
    index_refresh_paper_ids: tuple[str, ...],
) -> SeedQualityClosureReport:
    return SeedQualityClosureReport(
        seed_id=seed_id,
        run_id=run_id,
        status=status,
        ready_promotion_allowed=status == "success",
        stages=tuple(stages),
        stage_counts=dict(stage_counts),
        issues=tuple(issues),
        index_refresh_professor_ids=index_refresh_professor_ids,
        index_refresh_paper_ids=index_refresh_paper_ids,
    )


def _closure_issues_for_failure(
    *,
    context: ClosureContext,
    stage: str,
    reason: str,
    professor_ids: tuple[str, ...] | None = None,
) -> list[ClosureIssue]:
    scoped_professor_ids = professor_ids if professor_ids is not None else context.professor_ids
    targets: tuple[str | None, ...] = scoped_professor_ids or (None,)
    return [
        ClosureIssue(
            seed_id=context.seed_id,
            run_id=context.run_id,
            professor_id=professor_id,
            stage=stage,
            reason=reason,
            evidence={
                "trigger_mode": context.trigger_mode,
                "limit": context.limit,
            },
        )
        for professor_id in targets
    ]


def _closure_issue_description(
    *,
    seed_id: int,
    professor_id: str | None,
    stage: str,
    reason: str,
) -> str:
    target = professor_id or f"seed:{seed_id}"
    return (
        "[professor_core_profile_paper_quality_closure] "
        f"stage={stage} target={target} reason={reason[:500]}"
    )


def _row_value(row: object, key: str, index: int) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return row[index]  # type: ignore[index]
