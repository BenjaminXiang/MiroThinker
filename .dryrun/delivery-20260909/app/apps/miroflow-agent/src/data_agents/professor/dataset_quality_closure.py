from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Sequence

from psycopg.types.json import Jsonb

from src.data_agents.storage.postgres.pipeline_run import require_real_run_id
from src.data_agents.storage.postgres.paper_merge_alias import (
    PaperMergeAliasInput,
    upsert_paper_merge_alias,
)
from src.data_agents.storage.postgres.professor_profile_section import (
    ProfessorProfileSectionInput,
    upsert_professor_profile_section,
)

from .core_profile_paper_quality_audit import (
    DatasetClosureBucketRow,
    DatasetClosureBuckets,
)
from .output_summaries import persist_professor_output_summaries
from .profile_summary_contract import is_valid_profile_summary
from .quality_gate import (
    evaluate_professor_quality,
    load_professor_canonical_states,
    persist_professor_quality_evaluation,
)

ClosureLaneName = Literal[
    "profile_summary_repair",
    "research_overview_backfill",
    "professor_paper_summary_generation",
    "duplicate_paper_merge",
]

ALL_CLOSURE_LANES: tuple[ClosureLaneName, ...] = (
    "profile_summary_repair",
    "research_overview_backfill",
    "professor_paper_summary_generation",
    "duplicate_paper_merge",
)

_LANE_TO_BLOCKER = {
    "profile_summary_repair": "ready_summary_lt_200",
    "research_overview_backfill": "missing_research_overview_zh",
    "professor_paper_summary_generation": "missing_professor_paper_summary",
    "duplicate_paper_merge": "duplicate_verified_paper_title_year_groups",
}

_LANE_VALIDATION_RULES = {
    "profile_summary_repair": ("profile_summary_200_300_zh_contract",),
    "research_overview_backfill": ("research_overview_zh_source_grounded",),
    "professor_paper_summary_generation": ("deduplicated_verified_paper_inputs",),
    "duplicate_paper_merge": ("safe_identifier_or_author_supported_merge",),
}

_LANE_ISSUE_STAGE = {
    "profile_summary_repair": "coverage",
    "research_overview_backfill": "coverage",
    "professor_paper_summary_generation": "paper_attribution",
    "duplicate_paper_merge": "paper_quality",
}

_RESIDUAL_RISK_REPORTED_BY = "professor_dataset_quality_closure"
_RESIDUAL_RISK_ISSUE_TYPE = "professor_dataset_quality_closure_residual_risk"


RowWriteStatus = Literal["written", "unchanged", "unresolved"]
ClosureRowWriter = Callable[
    [Any, DatasetClosureBucketRow, str],
    "ClosureRowWriteResult",
]


@dataclass(frozen=True, slots=True)
class LaneDryRunSummary:
    lane: ClosureLaneName
    blocker_type: str
    dataset_input_count: int
    input_count: int
    eligible_count: int
    proposed_write_count: int
    skipped_count: int
    validation_failure_count: int
    provider_failure_count: int
    affected_professor_ids: tuple[str, ...]
    affected_paper_ids: tuple[str, ...]
    skip_reason_counts: dict[str, int]
    validation_rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DatasetClosureDryRunReport:
    mode: str
    dry_run: bool
    write_allowed: bool
    bucket_limit: int
    selection_hash: str
    lanes: tuple[LaneDryRunSummary, ...]


@dataclass(frozen=True, slots=True)
class ClosureRowWriteResult:
    status: RowWriteStatus
    changed_professor_ids: tuple[str, ...] = ()
    changed_paper_ids: tuple[str, ...] = ()
    unresolved_reason: str | None = None
    rollback_evidence: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DatasetClosureWriters:
    profile_summary_writer: ClosureRowWriter | None = None
    research_overview_writer: ClosureRowWriter | None = None
    professor_paper_summary_writer: ClosureRowWriter | None = None
    duplicate_paper_merge_writer: ClosureRowWriter | None = None

    def for_lane(self, lane: ClosureLaneName) -> ClosureRowWriter | None:
        if lane == "profile_summary_repair":
            return self.profile_summary_writer
        if lane == "research_overview_backfill":
            return self.research_overview_writer
        if lane == "professor_paper_summary_generation":
            return self.professor_paper_summary_writer
        if lane == "duplicate_paper_merge":
            return self.duplicate_paper_merge_writer
        raise ValueError(f"unsupported closure lane: {lane}")


@dataclass(frozen=True, slots=True)
class LaneWriteBatchSummary:
    lane: ClosureLaneName
    blocker_type: str
    input_count: int
    attempted_count: int
    written_count: int
    unchanged_count: int
    skipped_count: int
    failed_count: int
    unresolved_issue_count: int
    changed_professor_ids: tuple[str, ...]
    changed_paper_ids: tuple[str, ...]
    rollback_evidence: tuple[dict[str, Any], ...]
    issues: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class DatasetClosureWriteReport:
    mode: str
    dry_run: bool
    write_allowed: bool
    run_id: str
    bucket_limit: int
    batch_size: int
    dry_run_selection_hash: str
    lanes: tuple[LaneWriteBatchSummary, ...]


@dataclass(frozen=True, slots=True)
class QualityReevaluationEvidence:
    evaluated_professor_ids: tuple[str, ...]
    before_distribution: dict[str, int]
    after_distribution: dict[str, int]
    failures: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class AffectedAuditEvidence:
    checked_professor_ids: tuple[str, ...]
    checked_paper_ids: tuple[str, ...]
    remaining_blocker_counts: dict[str, int]
    failures: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class ApiSampleEvidence:
    sampled_ids: tuple[str, ...]
    failures: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class IndexRefreshEvidence:
    professor_ids: tuple[str, ...]
    paper_ids: tuple[str, ...]
    skipped_reason: str | None = None
    failures: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class PostWriteVerificationCallbacks:
    quality_re_evaluator: (
        Callable[
            [Any, tuple[str, ...]],
            QualityReevaluationEvidence,
        ]
        | None
    ) = None
    affected_audit_checker: (
        Callable[
            [Any, tuple[str, ...], tuple[str, ...]],
            AffectedAuditEvidence,
        ]
        | None
    ) = None
    professor_detail_sampler: (
        Callable[
            [Any, tuple[str, ...]],
            ApiSampleEvidence,
        ]
        | None
    ) = None
    paper_detail_sampler: (
        Callable[
            [Any, tuple[str, ...]],
            ApiSampleEvidence,
        ]
        | None
    ) = None
    refresh_selector: (
        Callable[
            [Any, tuple[str, ...], tuple[str, ...], str],
            IndexRefreshEvidence,
        ]
        | None
    ) = None


@dataclass(frozen=True, slots=True)
class DatasetClosurePostWriteVerificationReport:
    mode: str
    status: str
    completion_allowed: bool
    run_id: str
    changed_professor_ids: tuple[str, ...]
    changed_paper_ids: tuple[str, ...]
    quality_re_evaluation: QualityReevaluationEvidence | None = None
    affected_audit: AffectedAuditEvidence | None = None
    admin_professor_detail_samples: ApiSampleEvidence | None = None
    paper_detail_samples: ApiSampleEvidence | None = None
    index_refresh_selection: IndexRefreshEvidence | None = None
    issues: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class ResidualRiskIssueFilingReport:
    mode: str
    run_id: str
    input_count: int
    inserted_count: int
    updated_count: int
    by_blocker: dict[str, int]


@dataclass(frozen=True, slots=True)
class ResidualRiskCoverageReport:
    mode: str
    status: str
    input_count: int
    covered_count: int
    unclassified_count: int
    covered_by_blocker: dict[str, int]
    unclassified_samples: tuple[dict[str, Any], ...] = ()


class DryRunEvidenceRequired(RuntimeError):
    pass


class DryRunEvidenceMismatch(RuntimeError):
    pass


def build_lane_dry_run_report(
    buckets: DatasetClosureBuckets,
    *,
    lanes: Sequence[ClosureLaneName],
) -> DatasetClosureDryRunReport:
    normalized_lanes = tuple(_normalize_lane(lane) for lane in lanes)
    summaries = tuple(
        _build_lane_summary(buckets, lane=lane) for lane in normalized_lanes
    )
    return DatasetClosureDryRunReport(
        mode="dry_run",
        dry_run=True,
        write_allowed=False,
        bucket_limit=buckets.bucket_limit,
        selection_hash=_selection_hash(
            bucket_limit=buckets.bucket_limit,
            lanes=normalized_lanes,
            summaries=summaries,
        ),
        lanes=summaries,
    )


def format_dataset_closure_dry_run_report(
    report: DatasetClosureDryRunReport,
) -> str:
    return (
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def format_dataset_closure_write_report(
    report: DatasetClosureWriteReport,
) -> str:
    return (
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def format_dataset_closure_post_write_verification_report(
    report: DatasetClosurePostWriteVerificationReport,
) -> str:
    return (
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def load_dry_run_evidence(path: str | Path) -> DatasetClosureDryRunReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dry-run evidence must be a JSON object")
    lanes_payload = payload.get("lanes")
    if not isinstance(lanes_payload, list):
        raise ValueError("dry-run evidence must include lanes")
    lanes = tuple(_lane_summary_from_payload(item) for item in lanes_payload)
    return DatasetClosureDryRunReport(
        mode=str(payload.get("mode") or ""),
        dry_run=bool(payload.get("dry_run")),
        write_allowed=bool(payload.get("write_allowed")),
        bucket_limit=int(payload.get("bucket_limit") or 0),
        selection_hash=str(payload.get("selection_hash") or ""),
        lanes=lanes,
    )


def require_dry_run_evidence_for_write(
    *,
    lanes: Sequence[ClosureLaneName],
    evidence_path: str | Path | None,
) -> None:
    if evidence_path is None:
        lane_list = ", ".join(lanes)
        raise DryRunEvidenceRequired(
            f"write mode requires matching dry-run evidence for lanes: {lane_list}"
        )
    path = Path(evidence_path)
    if not path.is_file():
        raise DryRunEvidenceRequired(
            f"write mode requires existing dry-run evidence file: {path}"
        )


def run_dataset_closure_write_batch(
    *,
    conn: Any,
    buckets: DatasetClosureBuckets,
    lanes: Sequence[ClosureLaneName],
    dry_run_evidence: DatasetClosureDryRunReport,
    run_id: str | None,
    batch_size: int = 20,
    writers: DatasetClosureWriters | None = None,
) -> DatasetClosureWriteReport:
    run_id = str(
        require_real_run_id(
            run_id,
            writer_name="professor_dataset_quality_closure",
        )
    )
    normalized_lanes = tuple(_normalize_lane(lane) for lane in lanes)
    batch_size = _normalize_batch_size(batch_size)
    current_evidence = build_lane_dry_run_report(buckets, lanes=normalized_lanes)
    _validate_dry_run_evidence(
        expected=current_evidence,
        actual=dry_run_evidence,
        lanes=normalized_lanes,
    )
    lane_summaries = tuple(
        _run_lane_write_batch(
            conn=conn,
            buckets=buckets,
            lane=lane,
            run_id=run_id,
            batch_size=batch_size,
            writer=(writers or DatasetClosureWriters()).for_lane(lane),
        )
        for lane in normalized_lanes
    )
    return DatasetClosureWriteReport(
        mode="write",
        dry_run=False,
        write_allowed=True,
        run_id=run_id,
        bucket_limit=buckets.bucket_limit,
        batch_size=batch_size,
        dry_run_selection_hash=dry_run_evidence.selection_hash,
        lanes=lane_summaries,
    )


def default_dataset_closure_writers() -> DatasetClosureWriters:
    return DatasetClosureWriters(
        profile_summary_writer=_write_profile_summary_from_candidate,
        research_overview_writer=_write_research_overview_from_candidate,
        professor_paper_summary_writer=_write_paper_summary_from_candidate,
        duplicate_paper_merge_writer=_write_duplicate_merge_alias_from_candidate,
    )


def default_post_write_verification_callbacks() -> PostWriteVerificationCallbacks:
    return PostWriteVerificationCallbacks(
        quality_re_evaluator=_rerun_professor_quality_re_evaluation,
        affected_audit_checker=_check_affected_id_closure_audit,
        professor_detail_sampler=_sample_admin_professor_detail_shape,
        paper_detail_sampler=_sample_paper_detail_shape,
        refresh_selector=_select_changed_ids_for_refresh,
    )


def build_post_write_verification_report(
    *,
    conn: Any,
    write_report: DatasetClosureWriteReport,
    callbacks: PostWriteVerificationCallbacks,
) -> DatasetClosurePostWriteVerificationReport:
    changed_professor_ids = _unique_sorted(
        professor_id
        for lane in write_report.lanes
        for professor_id in lane.changed_professor_ids
    )
    changed_paper_ids = _unique_sorted(
        paper_id for lane in write_report.lanes for paper_id in lane.changed_paper_ids
    )
    if not changed_professor_ids and not changed_paper_ids:
        return DatasetClosurePostWriteVerificationReport(
            mode="post_write_verification",
            status="skipped",
            completion_allowed=False,
            run_id=write_report.run_id,
            changed_professor_ids=(),
            changed_paper_ids=(),
            issues=(
                {
                    "stage": "post_write_verification",
                    "reason": "no changed professor or paper ids",
                },
            ),
        )

    issues: list[dict[str, Any]] = []
    quality = _call_quality_re_evaluator(
        conn,
        callbacks=callbacks,
        professor_ids=changed_professor_ids,
        issues=issues,
    )
    audit = _call_affected_audit_checker(
        conn,
        callbacks=callbacks,
        professor_ids=changed_professor_ids,
        paper_ids=changed_paper_ids,
        issues=issues,
    )
    professor_samples = _call_api_sampler(
        conn,
        sampler=callbacks.professor_detail_sampler,
        ids=changed_professor_ids,
        stage="admin_professor_detail_sample",
        issues=issues,
        required=bool(changed_professor_ids),
    )
    paper_samples = _call_api_sampler(
        conn,
        sampler=callbacks.paper_detail_sampler,
        ids=changed_paper_ids,
        stage="paper_detail_sample",
        issues=issues,
        required=bool(changed_paper_ids),
    )
    refresh = _call_refresh_selector(
        conn,
        callbacks=callbacks,
        professor_ids=changed_professor_ids,
        paper_ids=changed_paper_ids,
        run_id=write_report.run_id,
        issues=issues,
    )

    status = "failed" if issues else "success"
    return DatasetClosurePostWriteVerificationReport(
        mode="post_write_verification",
        status=status,
        completion_allowed=status == "success",
        run_id=write_report.run_id,
        changed_professor_ids=changed_professor_ids,
        changed_paper_ids=changed_paper_ids,
        quality_re_evaluation=quality,
        affected_audit=audit,
        admin_professor_detail_samples=professor_samples,
        paper_detail_samples=paper_samples,
        index_refresh_selection=refresh,
        issues=tuple(issues),
    )


def file_residual_risk_issues_for_buckets(
    *,
    conn: Any,
    buckets: DatasetClosureBuckets,
    run_id: str | None,
    lanes: Sequence[ClosureLaneName] | None = None,
) -> ResidualRiskIssueFilingReport:
    run_id = str(
        require_real_run_id(
            run_id,
            writer_name="professor_dataset_quality_closure_residual_risk",
        )
    )
    selected_rows = _selected_residual_rows(buckets, lanes=lanes)
    _require_full_bucket_coverage(buckets, rows=selected_rows)
    inserted = 0
    updated = 0
    for row in selected_rows:
        result = _upsert_residual_risk_issue(conn, row=row, run_id=run_id)
        if result == "inserted":
            inserted += 1
        else:
            updated += 1
    return ResidualRiskIssueFilingReport(
        mode="residual_risk_issue_filing",
        run_id=run_id,
        input_count=len(selected_rows),
        inserted_count=inserted,
        updated_count=updated,
        by_blocker=_count_rows_by_blocker(selected_rows),
    )


def build_residual_risk_coverage_report(
    *,
    conn: Any,
    buckets: DatasetClosureBuckets,
    lanes: Sequence[ClosureLaneName] | None = None,
) -> ResidualRiskCoverageReport:
    selected_rows = _selected_residual_rows(buckets, lanes=lanes)
    covered_by_blocker: dict[str, int] = {}
    unclassified: list[dict[str, Any]] = []
    for row in selected_rows:
        if _open_residual_risk_issue_exists(conn, row):
            covered_by_blocker[row.blocker_type] = (
                covered_by_blocker.get(row.blocker_type, 0) + 1
            )
            continue
        unclassified.append(
            {
                "blocker_type": row.blocker_type,
                "professor_id": row.professor_id,
                "paper_id": row.paper_id,
                "duplicate_group_id": row.duplicate_group_id,
                "remediation_lane": row.remediation_lane,
            }
        )
    return ResidualRiskCoverageReport(
        mode="residual_risk_coverage",
        status="complete" if not unclassified else "incomplete",
        input_count=len(selected_rows),
        covered_count=len(selected_rows) - len(unclassified),
        unclassified_count=len(unclassified),
        covered_by_blocker=dict(sorted(covered_by_blocker.items())),
        unclassified_samples=tuple(unclassified[:20]),
    )


def _rerun_professor_quality_re_evaluation(
    conn: Any,
    professor_ids: tuple[str, ...],
) -> QualityReevaluationEvidence:
    if not professor_ids:
        return QualityReevaluationEvidence(
            evaluated_professor_ids=(),
            before_distribution={},
            after_distribution={},
        )
    before = _quality_distribution_for_ids(conn, professor_ids)
    states = load_professor_canonical_states(conn, list(professor_ids))
    evaluations = tuple(evaluate_professor_quality(state) for state in states)
    for evaluation in evaluations:
        persist_professor_quality_evaluation(conn, evaluation)
    evaluated_ids = tuple(evaluation.professor_id for evaluation in evaluations)
    after: dict[str, int] = {}
    for evaluation in evaluations:
        status = str(evaluation.quality_status)
        after[status] = after.get(status, 0) + 1
    failures = tuple(
        {
            "stage": "professor_quality_re_evaluation",
            "id": professor_id,
            "reason": "missing_quality_state",
        }
        for professor_id in professor_ids
        if professor_id not in set(evaluated_ids)
    )
    return QualityReevaluationEvidence(
        evaluated_professor_ids=evaluated_ids,
        before_distribution=before,
        after_distribution=dict(sorted(after.items())),
        failures=failures,
    )


def _check_affected_id_closure_audit(
    conn: Any,
    professor_ids: tuple[str, ...],
    paper_ids: tuple[str, ...],
) -> AffectedAuditEvidence:
    remaining = _remaining_professor_blockers_for_ids(conn, professor_ids)
    duplicate_count = _remaining_duplicate_paper_groups_for_ids(
        conn,
        professor_ids=professor_ids,
        paper_ids=paper_ids,
    )
    if duplicate_count:
        remaining["duplicate_verified_paper_title_year_groups"] = duplicate_count
    remaining = {key: count for key, count in remaining.items() if count}
    failures = ()
    if remaining:
        failures = (
            {
                "stage": "affected_id_closure_audit",
                "reason": "remaining_blockers",
                "remaining_blocker_counts": remaining,
            },
        )
    return AffectedAuditEvidence(
        checked_professor_ids=professor_ids,
        checked_paper_ids=paper_ids,
        remaining_blocker_counts=remaining,
        failures=failures,
    )


def _sample_admin_professor_detail_shape(
    conn: Any,
    professor_ids: tuple[str, ...],
) -> ApiSampleEvidence:
    if not professor_ids:
        return ApiSampleEvidence(sampled_ids=())
    rows = conn.execute(
        """
        SELECT p.professor_id,
               p.profile_summary,
               p.paper_summary,
               EXISTS (
                 SELECT 1
                   FROM professor_profile_section pps
                  WHERE pps.professor_id = p.professor_id
                    AND pps.section_type = 'research_overview'
                    AND pps.language = 'zh'
                    AND NULLIF(BTRIM(pps.content), '') IS NOT NULL
               ) AS has_research_overview_zh,
               (
                 SELECT COUNT(*)::int
                   FROM professor_paper_link ppl
                  WHERE ppl.professor_id = p.professor_id
                    AND ppl.link_status = 'verified'
               ) AS verified_paper_count
          FROM professor p
         WHERE p.professor_id = ANY(%s)
         ORDER BY p.professor_id
        """,
        (list(professor_ids),),
    ).fetchall()
    by_id = {str(_row_value(row, "professor_id", 0)): row for row in rows}
    failures: list[dict[str, Any]] = []
    for professor_id in professor_ids:
        row = by_id.get(professor_id)
        if row is None:
            failures.append(
                {
                    "stage": "admin_professor_detail_sample",
                    "id": professor_id,
                    "reason": "not_found",
                }
            )
            continue
        if not _optional_text(_row_value(row, "profile_summary", 1)):
            failures.append(
                {
                    "stage": "admin_professor_detail_sample",
                    "id": professor_id,
                    "reason": "missing_profile_summary",
                }
            )
    return ApiSampleEvidence(
        sampled_ids=tuple(
            professor_id for professor_id in professor_ids if professor_id in by_id
        ),
        failures=tuple(failures),
    )


def _sample_paper_detail_shape(
    conn: Any,
    paper_ids: tuple[str, ...],
) -> ApiSampleEvidence:
    if not paper_ids:
        return ApiSampleEvidence(sampled_ids=())
    rows = conn.execute(
        """
        SELECT p.paper_id,
               p.title_clean,
               p.quality_status,
               (COUNT(ppl.link_id) FILTER (
                 WHERE ppl.link_status = 'verified'
               ))::int AS verified_professor_count
          FROM paper p
          LEFT JOIN professor_paper_link ppl ON ppl.paper_id = p.paper_id
         WHERE p.paper_id = ANY(%s)
         GROUP BY p.paper_id, p.title_clean, p.quality_status
         ORDER BY p.paper_id
        """,
        (list(paper_ids),),
    ).fetchall()
    by_id = {str(_row_value(row, "paper_id", 0)): row for row in rows}
    failures: list[dict[str, Any]] = []
    for paper_id in paper_ids:
        row = by_id.get(paper_id)
        if row is None:
            failures.append(
                {
                    "stage": "paper_detail_sample",
                    "id": paper_id,
                    "reason": "not_found",
                }
            )
            continue
        if not _optional_text(_row_value(row, "title_clean", 1)):
            failures.append(
                {
                    "stage": "paper_detail_sample",
                    "id": paper_id,
                    "reason": "missing_title",
                }
            )
    return ApiSampleEvidence(
        sampled_ids=tuple(paper_id for paper_id in paper_ids if paper_id in by_id),
        failures=tuple(failures),
    )


def _select_changed_ids_for_refresh(
    _conn: Any,
    professor_ids: tuple[str, ...],
    paper_ids: tuple[str, ...],
    _run_id: str,
) -> IndexRefreshEvidence:
    if not professor_ids and not paper_ids:
        return IndexRefreshEvidence(
            professor_ids=(),
            paper_ids=(),
            skipped_reason="no_changed_ids",
        )
    return IndexRefreshEvidence(
        professor_ids=professor_ids,
        paper_ids=paper_ids,
    )


def _selected_residual_rows(
    buckets: DatasetClosureBuckets,
    *,
    lanes: Sequence[ClosureLaneName] | None,
) -> tuple[DatasetClosureBucketRow, ...]:
    if lanes is None:
        return tuple(buckets.rows)
    selected_lanes = {_normalize_lane(lane) for lane in lanes}
    return tuple(row for row in buckets.rows if row.remediation_lane in selected_lanes)


def _require_full_bucket_coverage(
    buckets: DatasetClosureBuckets,
    *,
    rows: Sequence[DatasetClosureBucketRow],
) -> None:
    selected_blockers = {row.blocker_type for row in rows}
    for blocker_type in sorted(selected_blockers):
        summary = buckets.summary.get(blocker_type) or {}
        total = int(summary.get("total") or 0)
        sampled = int(summary.get("sampled") or 0)
        truncated = bool(summary.get("truncated"))
        actual = sum(1 for row in rows if row.blocker_type == blocker_type)
        if truncated or sampled != total or actual != total:
            raise ValueError(
                "residual-risk issue filing requires full bucket coverage "
                f"for {blocker_type}: total={total}, sampled={sampled}, "
                f"actual={actual}, truncated={truncated}"
            )


def _upsert_residual_risk_issue(
    conn: Any,
    *,
    row: DatasetClosureBucketRow,
    run_id: str,
) -> Literal["inserted", "updated"]:
    stage = _stage_for_residual_row(row)
    professor_id = row.professor_id
    institution = _institution_for_residual_row(row)
    description = _residual_risk_description(row)
    severity = _residual_risk_severity(row)
    evidence = _residual_risk_evidence(row, run_id=run_id)
    existing = conn.execute(
        """
        SELECT issue_id
          FROM pipeline_issue
         WHERE professor_id IS NOT DISTINCT FROM %s
           AND institution IS NOT DISTINCT FROM %s
           AND stage = %s
           AND reported_by = %s
           AND description_hash = md5(%s)
           AND resolved = false
         LIMIT 1
        """,
        (
            professor_id,
            institution,
            stage,
            _RESIDUAL_RISK_REPORTED_BY,
            description,
        ),
    ).fetchone()
    evidence_snapshot = Jsonb(evidence)
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
            (evidence_snapshot, severity, issue_id),
        )
        return "updated"
    conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, institution, stage, severity,
            description, evidence_snapshot, reported_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            professor_id,
            institution,
            stage,
            severity,
            description,
            evidence_snapshot,
            _RESIDUAL_RISK_REPORTED_BY,
        ),
    )
    return "inserted"


def _open_residual_risk_issue_exists(
    conn: Any,
    row: DatasetClosureBucketRow,
) -> bool:
    result = conn.execute(
        """
        SELECT COUNT(*)::int AS count
          FROM pipeline_issue
         WHERE professor_id IS NOT DISTINCT FROM %s
           AND institution IS NOT DISTINCT FROM %s
           AND stage = %s
           AND reported_by = %s
           AND description_hash = md5(%s)
           AND resolved = false
           AND evidence_snapshot->>'issue_type' = %s
        """,
        (
            row.professor_id,
            _institution_for_residual_row(row),
            _stage_for_residual_row(row),
            _RESIDUAL_RISK_REPORTED_BY,
            _residual_risk_description(row),
            _RESIDUAL_RISK_ISSUE_TYPE,
        ),
    ).fetchone()
    return int(_row_value(result, "count", 0) or 0) > 0


def _residual_risk_description(row: DatasetClosureBucketRow) -> str:
    return (
        "professor dataset quality closure residual risk: "
        f"{row.blocker_type}: {_residual_target_key(row)}"
    )


def _residual_target_key(row: DatasetClosureBucketRow) -> str:
    if row.duplicate_group_id:
        return row.duplicate_group_id
    if row.paper_id:
        return row.paper_id
    if row.professor_id:
        return row.professor_id
    return f"{row.entity_type}:{row.blocker_type}"


def _residual_risk_evidence(
    row: DatasetClosureBucketRow,
    *,
    run_id: str,
) -> dict[str, Any]:
    reason = row.skip_reason or _pending_candidate_reason(row)
    recommended_action = _recommended_residual_action(row, reason)
    return {
        "issue_type": _RESIDUAL_RISK_ISSUE_TYPE,
        "domain": "professor",
        "run_id": run_id,
        "blocker_type": row.blocker_type,
        "entity_type": row.entity_type,
        "remediation_lane": row.remediation_lane,
        "professor_id": row.professor_id,
        "paper_id": row.paper_id,
        "duplicate_group_id": row.duplicate_group_id,
        "source_page_id": row.source_page_id,
        "source_url": row.source_url,
        "current_status": row.current_status,
        "reason": reason,
        "automatic_eligibility": row.automatic_eligibility,
        "confidence_impact": _confidence_impact(row),
        "recommended_action": recommended_action,
        "next_action": recommended_action,
        "bucket_evidence": row.evidence or {},
    }


def _pending_candidate_reason(row: DatasetClosureBucketRow) -> str:
    if row.remediation_lane == "profile_summary_repair":
        return "pending_profile_summary_candidate_generation"
    if row.remediation_lane == "research_overview_backfill":
        return "pending_research_overview_extraction_or_translation"
    if row.remediation_lane == "professor_paper_summary_generation":
        return "pending_professor_paper_summary_generation"
    if row.remediation_lane == "duplicate_paper_merge":
        return "pending_duplicate_paper_merge_candidate"
    return "pending_dataset_quality_closure"


def _recommended_residual_action(
    row: DatasetClosureBucketRow,
    reason: str,
) -> str:
    if reason == "missing_grounded_profile_inputs":
        return "Re-crawl the official profile page or mark the profile summary as manually blocked."
    if reason == "missing_official_source_text":
        return "Re-crawl the official profile page and extract a supported research overview source span."
    if reason == "duplicate_verified_paper_links":
        return "Resolve duplicate verified paper groups before generating the Professor paper summary."
    if reason == "ambiguous_fuzzy_match":
        return "Queue manual duplicate-paper review with DOI, arXiv, author, venue, or source-page evidence."
    if row.remediation_lane == "profile_summary_repair":
        return "Generate a 200-300 character Chinese summary from official Professor evidence and rerun write mode."
    if row.remediation_lane == "research_overview_backfill":
        return "Extract or translate the official research overview with source hash and rerun write mode."
    if row.remediation_lane == "professor_paper_summary_generation":
        return "Generate a grounded Professor paper summary from deduplicated verified paper links."
    if row.remediation_lane == "duplicate_paper_merge":
        return "Produce canonical paper merge evidence and rerun duplicate-paper merge write mode."
    return "Review the blocker and either repair the row or accept residual risk with evidence."


def _confidence_impact(row: DatasetClosureBucketRow) -> str:
    if row.blocker_type == "ready_summary_lt_200":
        return "Professor profile may look shallow in user-facing detail and retrieval snippets."
    if row.blocker_type == "missing_research_overview_zh":
        return "Chinese research overview cannot be displayed or cited from durable profile sections."
    if row.blocker_type == "missing_professor_paper_summary":
        return "Professor output narrative remains incomplete despite verified paper links."
    if row.blocker_type == "duplicate_verified_paper_title_year_groups":
        return "Paper list may show duplicate verified outputs until canonical merge evidence is applied."
    return "Dataset quality closure cannot be considered complete for this row."


def _residual_risk_severity(row: DatasetClosureBucketRow) -> str:
    if row.blocker_type == "duplicate_verified_paper_title_year_groups":
        return "high"
    if row.automatic_eligibility:
        return "medium"
    return "high"


def _stage_for_residual_row(row: DatasetClosureBucketRow) -> str:
    return _LANE_ISSUE_STAGE[_normalize_lane(row.remediation_lane)]


def _institution_for_residual_row(row: DatasetClosureBucketRow) -> str | None:
    if row.professor_id:
        return None
    return f"{row.entity_type}:{_residual_target_key(row)}"


def _count_rows_by_blocker(rows: Sequence[DatasetClosureBucketRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.blocker_type] = counts.get(row.blocker_type, 0) + 1
    return dict(sorted(counts.items()))


def _build_lane_summary(
    buckets: DatasetClosureBuckets,
    *,
    lane: ClosureLaneName,
) -> LaneDryRunSummary:
    blocker_type = _LANE_TO_BLOCKER[lane]
    rows = [row for row in buckets.rows if row.remediation_lane == lane]
    eligible_rows = [row for row in rows if row.automatic_eligibility]
    skipped_rows = [row for row in rows if not row.automatic_eligibility]
    validation_failure_rows = [
        row for row in eligible_rows if _has_validation_failure(row, lane=lane)
    ]
    validation_failure_ids = {id(row) for row in validation_failure_rows}
    proposed_rows = [
        row for row in eligible_rows if id(row) not in validation_failure_ids
    ]
    return LaneDryRunSummary(
        lane=lane,
        blocker_type=blocker_type,
        dataset_input_count=int(
            (buckets.summary.get(blocker_type) or {}).get("total") or 0
        ),
        input_count=len(rows),
        eligible_count=len(eligible_rows),
        proposed_write_count=len(proposed_rows),
        skipped_count=len(skipped_rows),
        validation_failure_count=len(validation_failure_rows),
        provider_failure_count=0,
        affected_professor_ids=_unique_sorted(
            row.professor_id for row in proposed_rows if row.professor_id
        ),
        affected_paper_ids=_affected_paper_ids(proposed_rows),
        skip_reason_counts=_skip_reason_counts(skipped_rows),
        validation_rules=_LANE_VALIDATION_RULES[lane],
    )


def _call_quality_re_evaluator(
    conn: Any,
    *,
    callbacks: PostWriteVerificationCallbacks,
    professor_ids: tuple[str, ...],
    issues: list[dict[str, Any]],
) -> QualityReevaluationEvidence | None:
    if not professor_ids:
        return QualityReevaluationEvidence(
            evaluated_professor_ids=(),
            before_distribution={},
            after_distribution={},
        )
    if callbacks.quality_re_evaluator is None:
        issues.append(
            {
                "stage": "professor_quality_re_evaluation",
                "reason": "missing_quality_re_evaluator",
            }
        )
        return None
    try:
        evidence = callbacks.quality_re_evaluator(conn, professor_ids)
    except Exception as exc:  # noqa: BLE001 - verification failure must surface
        issues.append(
            {
                "stage": "professor_quality_re_evaluation",
                "reason": str(exc),
            }
        )
        return None
    issues.extend(evidence.failures)
    return evidence


def _quality_distribution_for_ids(
    conn: Any,
    professor_ids: tuple[str, ...],
) -> dict[str, int]:
    if not professor_ids:
        return {}
    rows = conn.execute(
        """
        SELECT COALESCE(quality_status, 'missing') AS quality_status,
               COUNT(*)::int AS count
          FROM professor
         WHERE professor_id = ANY(%s)
         GROUP BY quality_status
         ORDER BY quality_status
        """,
        (list(professor_ids),),
    ).fetchall()
    return {
        str(_row_value(row, "quality_status", 0)): int(_row_value(row, "count", 1) or 0)
        for row in rows
    }


def _remaining_professor_blockers_for_ids(
    conn: Any,
    professor_ids: tuple[str, ...],
) -> dict[str, int]:
    if not professor_ids:
        return {}
    row = conn.execute(
        """
        SELECT COUNT(*) FILTER (
                 WHERE p.quality_status = 'ready'
                   AND char_length(COALESCE(p.profile_summary, '')) < 200
               )::int AS ready_summary_lt_200,
               COUNT(*) FILTER (
                 WHERE p.profile_raw_text ~* '(research|研究领域|研究方向|研究兴趣|研究概况|研究简介)'
                   AND NOT EXISTS (
                     SELECT 1
                       FROM professor_profile_section pps
                      WHERE pps.professor_id = p.professor_id
                        AND pps.section_type = 'research_overview'
                        AND pps.language = 'zh'
                        AND NULLIF(BTRIM(pps.content), '') IS NOT NULL
                   )
               )::int AS missing_research_overview_zh,
               COUNT(*) FILTER (
                 WHERE EXISTS (
                     SELECT 1
                       FROM professor_paper_link ppl
                      WHERE ppl.professor_id = p.professor_id
                        AND ppl.link_status = 'verified'
                   )
                   AND NULLIF(BTRIM(COALESCE(p.paper_summary, '')), '') IS NULL
               )::int AS missing_professor_paper_summary
          FROM professor p
         WHERE p.professor_id = ANY(%s)
        """,
        (list(professor_ids),),
    ).fetchone()
    if row is None:
        return {}
    return {
        "ready_summary_lt_200": int(_row_value(row, "ready_summary_lt_200", 0) or 0),
        "missing_research_overview_zh": int(
            _row_value(row, "missing_research_overview_zh", 1) or 0
        ),
        "missing_professor_paper_summary": int(
            _row_value(row, "missing_professor_paper_summary", 2) or 0
        ),
    }


def _remaining_duplicate_paper_groups_for_ids(
    conn: Any,
    *,
    professor_ids: tuple[str, ...],
    paper_ids: tuple[str, ...],
) -> int:
    if not professor_ids and not paper_ids:
        return 0
    rows = conn.execute(
        """
        WITH scope_links AS (
          SELECT ppl.professor_id,
                 COALESCE(pma.canonical_paper_id, ppl.paper_id) AS resolved_paper_id
            FROM professor_paper_link ppl
            LEFT JOIN paper_merge_alias pma ON pma.old_paper_id = ppl.paper_id
           WHERE ppl.link_status = 'verified'
             AND (
               ppl.professor_id = ANY(%s)
               OR ppl.paper_id = ANY(%s)
               OR pma.canonical_paper_id = ANY(%s)
             )
        ),
        groups AS (
          SELECT sl.professor_id,
                 lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g'))
                   AS title_key,
                 p.year,
                 COUNT(DISTINCT p.paper_id)::int AS paper_count
            FROM scope_links sl
            JOIN paper p ON p.paper_id = sl.resolved_paper_id
           WHERE NULLIF(BTRIM(COALESCE(p.title_clean, '')), '') IS NOT NULL
           GROUP BY sl.professor_id,
                    lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g')),
                    p.year
          HAVING COUNT(DISTINCT p.paper_id) > 1
        )
        SELECT COUNT(*)::int AS duplicate_verified_paper_title_year_groups
          FROM groups
        """,
        (list(professor_ids), list(paper_ids), list(paper_ids)),
    ).fetchone()
    if rows is None:
        return 0
    return int(_row_value(rows, "duplicate_verified_paper_title_year_groups", 0) or 0)


def _call_affected_audit_checker(
    conn: Any,
    *,
    callbacks: PostWriteVerificationCallbacks,
    professor_ids: tuple[str, ...],
    paper_ids: tuple[str, ...],
    issues: list[dict[str, Any]],
) -> AffectedAuditEvidence | None:
    if callbacks.affected_audit_checker is None:
        issues.append(
            {
                "stage": "affected_id_closure_audit",
                "reason": "missing_affected_audit_checker",
            }
        )
        return None
    try:
        evidence = callbacks.affected_audit_checker(conn, professor_ids, paper_ids)
    except Exception as exc:  # noqa: BLE001
        issues.append(
            {
                "stage": "affected_id_closure_audit",
                "reason": str(exc),
            }
        )
        return None
    issues.extend(evidence.failures)
    return evidence


def _call_api_sampler(
    conn: Any,
    *,
    sampler: Callable[[Any, tuple[str, ...]], ApiSampleEvidence] | None,
    ids: tuple[str, ...],
    stage: str,
    issues: list[dict[str, Any]],
    required: bool,
) -> ApiSampleEvidence | None:
    if not ids and not required:
        return ApiSampleEvidence(sampled_ids=())
    if sampler is None:
        issues.append({"stage": stage, "reason": f"missing_{stage}"})
        return None
    try:
        evidence = sampler(conn, ids)
    except Exception as exc:  # noqa: BLE001
        issues.append({"stage": stage, "reason": str(exc)})
        return None
    issues.extend(evidence.failures)
    return evidence


def _call_refresh_selector(
    conn: Any,
    *,
    callbacks: PostWriteVerificationCallbacks,
    professor_ids: tuple[str, ...],
    paper_ids: tuple[str, ...],
    run_id: str,
    issues: list[dict[str, Any]],
) -> IndexRefreshEvidence | None:
    if callbacks.refresh_selector is None:
        issues.append(
            {
                "stage": "index_refresh_selection",
                "reason": "missing_refresh_selector",
            }
        )
        return None
    try:
        evidence = callbacks.refresh_selector(conn, professor_ids, paper_ids, run_id)
    except Exception as exc:  # noqa: BLE001
        issues.append({"stage": "index_refresh_selection", "reason": str(exc)})
        return None
    issues.extend(evidence.failures)
    return evidence


def _write_profile_summary_from_candidate(
    conn: Any,
    row: DatasetClosureBucketRow,
    run_id: str,
) -> ClosureRowWriteResult:
    professor_id = _required_row_id(row.professor_id, "professor_id")
    evidence = row.evidence or {}
    candidate = str(evidence.get("candidate_profile_summary") or "").strip()
    if not candidate:
        return ClosureRowWriteResult(
            status="unresolved",
            unresolved_reason="missing_candidate_profile_summary",
        )
    if not _valid_candidate_profile_summary(candidate):
        return ClosureRowWriteResult(
            status="unresolved",
            unresolved_reason="invalid_candidate_profile_summary",
        )
    current = _fetch_professor_field(
        conn,
        professor_id=professor_id,
        field_name="profile_summary",
    )
    if current == candidate:
        return ClosureRowWriteResult(status="unchanged")
    conn.execute(
        """
        UPDATE professor
           SET profile_summary = %s,
               run_id = %s,
               updated_at = now()
         WHERE professor_id = %s
        """,
        (candidate, run_id, professor_id),
    )
    return ClosureRowWriteResult(
        status="written",
        changed_professor_ids=(professor_id,),
        rollback_evidence={
            "table": "professor",
            "field": "profile_summary",
            "professor_id": professor_id,
            "before": current,
            "after": candidate,
        },
    )


def _write_research_overview_from_candidate(
    conn: Any,
    row: DatasetClosureBucketRow,
    run_id: str,
) -> ClosureRowWriteResult:
    professor_id = _required_row_id(row.professor_id, "professor_id")
    evidence = row.evidence or {}
    content = str(
        evidence.get("research_overview_content")
        or evidence.get("candidate_research_overview_zh")
        or ""
    ).strip()
    if not content:
        return ClosureRowWriteResult(
            status="unresolved",
            unresolved_reason="missing_candidate_research_overview",
        )
    if not re.search(r"[\u4e00-\u9fff]", content):
        return ClosureRowWriteResult(
            status="unresolved",
            unresolved_reason="research_overview_not_chinese",
        )
    source_text = _optional_text(evidence.get("source_text"))
    source_text_hash = _optional_text(evidence.get("source_text_hash"))
    if not source_text and not source_text_hash:
        return ClosureRowWriteResult(
            status="unresolved",
            unresolved_reason="missing_research_overview_source_hash",
        )
    source_language = _optional_text(evidence.get("source_language"))
    generation_method = _optional_text(evidence.get("generation_method"))
    if not generation_method:
        generation_method = (
            "llm_translation" if source_language == "en" else "official_extract"
        )
    result = upsert_professor_profile_section(
        conn,
        ProfessorProfileSectionInput(
            professor_id=professor_id,
            section_type="research_overview",
            language="zh",
            content=content,
            source_page_id=row.source_page_id,
            source_language=source_language,
            source_text=source_text,
            source_text_hash=source_text_hash,
            source_span=_optional_text(evidence.get("source_span")),
            generation_method=generation_method,
            run_id=run_id,
        ),
    )
    return ClosureRowWriteResult(
        status="written",
        changed_professor_ids=(professor_id,),
        rollback_evidence={
            "table": "professor_profile_section",
            "field": "research_overview",
            "professor_id": professor_id,
            "section_id": str(result.section_id),
            "source_text_hash": source_text_hash,
        },
    )


def _write_paper_summary_from_candidate(
    conn: Any,
    row: DatasetClosureBucketRow,
    run_id: str,
) -> ClosureRowWriteResult:
    professor_id = _required_row_id(row.professor_id, "professor_id")
    evidence = row.evidence or {}
    candidate = str(
        evidence.get("candidate_paper_summary") or evidence.get("paper_summary") or ""
    ).strip()
    if not candidate:
        return ClosureRowWriteResult(
            status="unresolved",
            unresolved_reason="missing_candidate_paper_summary",
        )
    current = _fetch_professor_field(
        conn,
        professor_id=professor_id,
        field_name="paper_summary",
    )
    persistence = persist_professor_output_summaries(
        conn,
        professor_id=professor_id,
        paper_summary=candidate,
        patent_summary=None,
        run_id=run_id,
    )
    if "paper_summary" not in persistence.changed_fields:
        return ClosureRowWriteResult(status="unchanged")
    return ClosureRowWriteResult(
        status="written",
        changed_professor_ids=(professor_id,),
        rollback_evidence={
            "table": "professor",
            "field": "paper_summary",
            "professor_id": professor_id,
            "before": current,
            "after": candidate,
        },
    )


def _write_duplicate_merge_alias_from_candidate(
    conn: Any,
    row: DatasetClosureBucketRow,
    run_id: str,
) -> ClosureRowWriteResult:
    evidence = row.evidence or {}
    candidate_gate = evidence.get("candidate_generation")
    if isinstance(candidate_gate, dict):
        if (
            candidate_gate.get("candidate_status") != "ready"
            or candidate_gate.get("write_recommendation") != "auto_write_candidate"
        ):
            return ClosureRowWriteResult(
                status="unresolved",
                unresolved_reason="candidate_requires_review_before_write",
            )
    canonical_paper_id = _optional_text(evidence.get("canonical_paper_id"))
    if not canonical_paper_id:
        return ClosureRowWriteResult(
            status="unresolved",
            unresolved_reason="missing_canonical_paper_id",
        )
    old_paper_ids = tuple(
        item
        for item in _string_tuple(
            evidence.get("old_paper_ids") or evidence.get("paper_ids")
        )
        if item != canonical_paper_id
    )
    if not old_paper_ids:
        return ClosureRowWriteResult(
            status="unresolved",
            unresolved_reason="missing_old_paper_ids",
        )
    merge_reason = (
        _optional_text(evidence.get("merge_reason"))
        or "dataset_quality_closure:verified_duplicate_group"
    )
    evidence_source = row.source_url or row.source_page_id or row.duplicate_group_id
    for old_paper_id in old_paper_ids:
        upsert_paper_merge_alias(
            conn,
            PaperMergeAliasInput(
                old_paper_id=old_paper_id,
                canonical_paper_id=canonical_paper_id,
                merge_reason=merge_reason,
                evidence_source=str(evidence_source) if evidence_source else None,
                run_id=run_id,
            ),
        )
    return ClosureRowWriteResult(
        status="written",
        changed_professor_ids=(row.professor_id,) if row.professor_id else (),
        changed_paper_ids=_unique_sorted((canonical_paper_id, *old_paper_ids)),
        rollback_evidence={
            "table": "paper_merge_alias",
            "canonical_paper_id": canonical_paper_id,
            "old_paper_ids": old_paper_ids,
            "merge_reason": merge_reason,
        },
    )


def _run_lane_write_batch(
    *,
    conn: Any,
    buckets: DatasetClosureBuckets,
    lane: ClosureLaneName,
    run_id: str,
    batch_size: int,
    writer: ClosureRowWriter | None,
) -> LaneWriteBatchSummary:
    rows = [row for row in buckets.rows if row.remediation_lane == lane]
    review_required_rows = [
        row
        for row in rows
        if row.automatic_eligibility
        and not _has_validation_failure(row, lane=lane)
        and _candidate_requires_review_before_write(row)
    ]
    review_required_row_ids = {id(row) for row in review_required_rows}
    skipped_rows = [
        row
        for row in rows
        if not row.automatic_eligibility
        or _has_validation_failure(row, lane=lane)
        or id(row) in review_required_row_ids
    ]
    eligible_rows = [
        row
        for row in rows
        if row.automatic_eligibility
        and not _has_validation_failure(row, lane=lane)
        and id(row) not in review_required_row_ids
    ]
    attempted_rows = eligible_rows[:batch_size]
    skipped_by_batch_bound = eligible_rows[batch_size:]

    written = 0
    unchanged = 0
    failed = 0
    issues: list[dict[str, Any]] = []
    changed_professor_ids: list[str] = []
    changed_paper_ids: list[str] = []
    rollback_evidence: list[dict[str, Any]] = []

    for row in [*skipped_rows, *skipped_by_batch_bound]:
        if row in skipped_by_batch_bound:
            reason = row.skip_reason or "batch_size_bound"
        elif id(row) in review_required_row_ids:
            reason = "candidate_requires_review_before_write"
        else:
            reason = row.skip_reason
        issues.append(
            _issue_payload(
                row,
                lane=lane,
                reason=reason or "not_automatic_eligible",
                run_id=run_id,
            )
        )

    for row in attempted_rows:
        try:
            result = (
                writer(conn, row, run_id)
                if writer is not None
                else ClosureRowWriteResult(
                    status="unresolved",
                    unresolved_reason="writer_not_configured",
                )
            )
        except Exception as exc:  # noqa: BLE001 - row-level failure must be visible
            failed += 1
            issues.append(
                _issue_payload(row, lane=lane, reason=str(exc), run_id=run_id)
            )
            continue

        if result.status == "written":
            written += 1
        elif result.status == "unchanged":
            unchanged += 1
        elif result.status == "unresolved":
            issues.append(
                _issue_payload(
                    row,
                    lane=lane,
                    reason=result.unresolved_reason or "unresolved",
                    run_id=run_id,
                )
            )
        else:
            failed += 1
            issues.append(
                _issue_payload(
                    row,
                    lane=lane,
                    reason=f"unsupported_write_status:{result.status}",
                    run_id=run_id,
                )
            )
            continue

        changed_professor_ids.extend(result.changed_professor_ids)
        changed_paper_ids.extend(result.changed_paper_ids)
        if result.rollback_evidence:
            rollback_evidence.append(dict(result.rollback_evidence))

    return LaneWriteBatchSummary(
        lane=lane,
        blocker_type=_LANE_TO_BLOCKER[lane],
        input_count=len(rows),
        attempted_count=len(attempted_rows),
        written_count=written,
        unchanged_count=unchanged,
        skipped_count=len(skipped_rows) + len(skipped_by_batch_bound),
        failed_count=failed,
        unresolved_issue_count=len(issues),
        changed_professor_ids=_unique_sorted(changed_professor_ids),
        changed_paper_ids=_unique_sorted(changed_paper_ids),
        rollback_evidence=tuple(rollback_evidence),
        issues=tuple(issues),
    )


def _has_validation_failure(
    row: DatasetClosureBucketRow,
    *,
    lane: ClosureLaneName,
) -> bool:
    if lane != "profile_summary_repair":
        return False
    evidence = row.evidence or {}
    if isinstance(evidence.get("candidate_generation"), dict):
        return False
    if "candidate_profile_summary" not in evidence:
        return False
    return not _valid_candidate_profile_summary(
        str(evidence.get("candidate_profile_summary") or "")
    )


def _candidate_requires_review_before_write(row: DatasetClosureBucketRow) -> bool:
    candidate_gate = (row.evidence or {}).get("candidate_generation")
    if not isinstance(candidate_gate, dict):
        return False
    return (
        candidate_gate.get("candidate_status") != "ready"
        or candidate_gate.get("write_recommendation") != "auto_write_candidate"
    )


def _validate_dry_run_evidence(
    *,
    expected: DatasetClosureDryRunReport,
    actual: DatasetClosureDryRunReport,
    lanes: Sequence[ClosureLaneName],
) -> None:
    if actual.mode != "dry_run" or not actual.dry_run:
        raise DryRunEvidenceMismatch("write mode requires dry-run evidence")
    actual_lanes = tuple(lane.lane for lane in actual.lanes)
    expected_lanes = tuple(lanes)
    if actual_lanes != expected_lanes:
        raise DryRunEvidenceMismatch(
            f"dry-run evidence lanes {actual_lanes} do not match {expected_lanes}"
        )
    if actual.selection_hash != expected.selection_hash:
        raise DryRunEvidenceMismatch(
            "dry-run evidence selection_hash does not match current bucket selection"
        )


def _issue_payload(
    row: DatasetClosureBucketRow,
    *,
    lane: ClosureLaneName,
    reason: str,
    run_id: str,
) -> dict[str, Any]:
    return {
        "lane": lane,
        "stage": _LANE_ISSUE_STAGE[lane],
        "blocker_type": row.blocker_type,
        "professor_id": row.professor_id,
        "paper_id": row.paper_id,
        "duplicate_group_id": row.duplicate_group_id,
        "reason": reason,
        "run_id": run_id,
    }


def _lane_summary_from_payload(payload: Any) -> LaneDryRunSummary:
    if not isinstance(payload, dict):
        raise ValueError("dry-run lane evidence must be a JSON object")
    lane = _normalize_lane(str(payload.get("lane") or ""))
    return LaneDryRunSummary(
        lane=lane,
        blocker_type=str(payload.get("blocker_type") or _LANE_TO_BLOCKER[lane]),
        dataset_input_count=int(payload.get("dataset_input_count") or 0),
        input_count=int(payload.get("input_count") or 0),
        eligible_count=int(payload.get("eligible_count") or 0),
        proposed_write_count=int(payload.get("proposed_write_count") or 0),
        skipped_count=int(payload.get("skipped_count") or 0),
        validation_failure_count=int(payload.get("validation_failure_count") or 0),
        provider_failure_count=int(payload.get("provider_failure_count") or 0),
        affected_professor_ids=tuple(
            str(item) for item in payload.get("affected_professor_ids") or ()
        ),
        affected_paper_ids=tuple(
            str(item) for item in payload.get("affected_paper_ids") or ()
        ),
        skip_reason_counts=dict(payload.get("skip_reason_counts") or {}),
        validation_rules=tuple(
            str(item) for item in payload.get("validation_rules") or ()
        ),
    )


def _normalize_batch_size(value: int) -> int:
    if value <= 0:
        raise ValueError("batch_size must be positive")
    return min(int(value), 5000)


def _fetch_professor_field(
    conn: Any,
    *,
    professor_id: str,
    field_name: str,
) -> str | None:
    if field_name not in {"profile_summary", "paper_summary"}:
        raise ValueError(f"unsupported professor field: {field_name}")
    row = conn.execute(
        f"""
        SELECT {field_name}
          FROM professor
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    if row is None:
        return None
    return _optional_text(_row_value(row, field_name, 0))


def _required_row_id(value: str | None, name: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ()
    text = str(value).strip()
    return (text,) if text else ()


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError):
        return row[index]


def _valid_candidate_profile_summary(value: str) -> bool:
    return is_valid_profile_summary(value)


def _selection_hash(
    *,
    bucket_limit: int,
    lanes: Sequence[ClosureLaneName],
    summaries: Sequence[LaneDryRunSummary],
) -> str:
    payload = {
        "bucket_limit": bucket_limit,
        "lanes": list(lanes),
        "summaries": [asdict(summary) for summary in summaries],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _affected_paper_ids(rows: Sequence[DatasetClosureBucketRow]) -> tuple[str, ...]:
    paper_ids: list[str] = []
    for row in rows:
        if row.paper_id:
            paper_ids.append(row.paper_id)
        evidence = row.evidence or {}
        raw_ids = evidence.get("paper_ids")
        if isinstance(raw_ids, (list, tuple)):
            paper_ids.extend(str(item) for item in raw_ids if item)
    return _unique_sorted(paper_ids)


def _skip_reason_counts(rows: Sequence[DatasetClosureBucketRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = row.skip_reason or "unspecified_skip_reason"
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _unique_sorted(values: Sequence[str] | Any) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if value}))


def _normalize_lane(value: str) -> ClosureLaneName:
    if value not in ALL_CLOSURE_LANES:
        raise ValueError(f"unsupported closure lane: {value}")
    return value  # type: ignore[return-value]
