from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal, Sequence


FullRunCoverageState = Literal["covered", "failed", "missing"]
FieldDefectStatus = Literal["resolved", "unresolved"]
P9Readiness = Literal["ready", "blocked"]


@dataclass(frozen=True, slots=True)
class FullRunEvidence:
    seed_id: int
    run_id: str
    status: str
    trigger_mode: str
    failure_class: str
    items_processed: int
    items_failed: int
    written_profile_count: int | None
    diagnostic_profile_count: int | None


@dataclass(frozen=True, slots=True)
class FullRunCoverage:
    seed_id: int
    run_id: str
    status: str
    trigger_mode: str
    failure_class: str
    items_processed: int
    items_failed: int
    written_profile_count: int | None
    diagnostic_profile_count: int | None
    coverage_state: FullRunCoverageState
    reason: str


@dataclass(frozen=True, slots=True)
class FieldDefectInput:
    defect_id: str
    professor_id: str
    canonical_name: str
    source_url: str
    field_name: str
    current_value: str | None
    expected_value: str


@dataclass(frozen=True, slots=True)
class FieldDefectResult:
    defect_id: str
    professor_id: str
    canonical_name: str
    source_url: str
    field_name: str
    expected_value: str
    current_value_preview: str
    contamination_markers: list[str]
    status: FieldDefectStatus


@dataclass(frozen=True, slots=True)
class PostFullQualityMetrics:
    canonical_total: int
    quality_status_distribution: dict[str, int]
    run_id_coverage: dict[str, int]
    official_source_page_coverage: dict[str, int]
    primary_affiliation_coverage: dict[str, int]
    fact_coverage: dict[str, int]
    duplicate_identity_risk_groups: list[dict[str, object]]
    open_pipeline_issue_counts: dict[str, int]

    @classmethod
    def empty(cls, *, canonical_total: int = 0) -> PostFullQualityMetrics:
        return cls(
            canonical_total=canonical_total,
            quality_status_distribution={},
            run_id_coverage={
                "with_run_id": canonical_total,
                "missing_run_id": 0,
            },
            official_source_page_coverage={
                "with_official_source_page": 0,
                "missing_official_source_page": canonical_total,
            },
            primary_affiliation_coverage={
                "with_primary_affiliation": 0,
                "missing_primary_affiliation": canonical_total,
            },
            fact_coverage={
                "with_fact": 0,
                "missing_fact": canonical_total,
            },
            duplicate_identity_risk_groups=[],
            open_pipeline_issue_counts={},
        )


@dataclass(frozen=True, slots=True)
class PostFullAuditReport:
    blocked_seed_carryover: list[int]
    canonical_total: int
    duplicate_identity_risk_groups: list[dict[str, object]]
    fact_coverage: dict[str, int]
    full_run_coverage: list[FullRunCoverage]
    known_field_defects: list[FieldDefectResult]
    official_source_page_coverage: dict[str, int]
    open_pipeline_issue_counts: dict[str, int]
    p9_blockers: list[str]
    p9_readiness: P9Readiness
    primary_affiliation_coverage: dict[str, int]
    quality_status_distribution: dict[str, int]
    run_id_coverage: dict[str, int]


_CONTAMINATION_MARKERS = (
    "URL Source",
    "Published Time",
    "Markdown Content",
    "搜索",
    "面包屑",
    "教育背景",
    "学术领域",
    "研究领域",
    "个人简介",
    "学术著作",
)


def build_post_full_audit_report(
    *,
    selected_seed_ids: Sequence[int],
    full_runs: Sequence[FullRunEvidence],
    metrics: PostFullQualityMetrics,
    blocked_seed_ids: Sequence[int],
    field_defects: Sequence[FieldDefectInput],
) -> PostFullAuditReport:
    full_run_coverage = _build_full_run_coverage(selected_seed_ids, full_runs)
    known_field_defects = [_classify_field_defect(defect) for defect in field_defects]
    p9_blockers = _collect_p9_blockers(full_run_coverage, known_field_defects)
    return PostFullAuditReport(
        blocked_seed_carryover=sorted({int(seed_id) for seed_id in blocked_seed_ids}),
        canonical_total=metrics.canonical_total,
        duplicate_identity_risk_groups=metrics.duplicate_identity_risk_groups,
        fact_coverage=metrics.fact_coverage,
        full_run_coverage=full_run_coverage,
        known_field_defects=known_field_defects,
        official_source_page_coverage=metrics.official_source_page_coverage,
        open_pipeline_issue_counts=metrics.open_pipeline_issue_counts,
        p9_blockers=p9_blockers,
        p9_readiness="blocked" if p9_blockers else "ready",
        primary_affiliation_coverage=metrics.primary_affiliation_coverage,
        quality_status_distribution=metrics.quality_status_distribution,
        run_id_coverage=metrics.run_id_coverage,
    )


def format_post_full_audit_report(report: PostFullAuditReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _build_full_run_coverage(
    selected_seed_ids: Sequence[int],
    full_runs: Sequence[FullRunEvidence],
) -> list[FullRunCoverage]:
    by_seed = {run.seed_id: run for run in full_runs}
    rows: list[FullRunCoverage] = []
    for seed_id in sorted({int(seed_id) for seed_id in selected_seed_ids}):
        run = by_seed.get(seed_id)
        if run is None:
            rows.append(
                FullRunCoverage(
                    seed_id=seed_id,
                    run_id="",
                    status="missing",
                    trigger_mode="",
                    failure_class="",
                    items_processed=0,
                    items_failed=0,
                    written_profile_count=None,
                    diagnostic_profile_count=None,
                    coverage_state="missing",
                    reason="missing_latest_full_run",
                )
            )
            continue

        is_covered = (
            run.status == "succeeded"
            and run.trigger_mode == "full"
            and run.failure_class == "success"
            and run.items_processed > 0
            and run.items_failed == 0
        )
        rows.append(
            FullRunCoverage(
                seed_id=seed_id,
                run_id=run.run_id,
                status=run.status,
                trigger_mode=run.trigger_mode,
                failure_class=run.failure_class,
                items_processed=run.items_processed,
                items_failed=run.items_failed,
                written_profile_count=run.written_profile_count,
                diagnostic_profile_count=run.diagnostic_profile_count,
                coverage_state="covered" if is_covered else "failed",
                reason="latest_full_run_success" if is_covered else "latest_full_run_not_success",
            )
        )
    return rows


def _classify_field_defect(defect: FieldDefectInput) -> FieldDefectResult:
    current = defect.current_value or ""
    markers = [marker for marker in _CONTAMINATION_MARKERS if marker in current]
    status: FieldDefectStatus = (
        "resolved" if current.strip() == defect.expected_value and not markers else "unresolved"
    )
    return FieldDefectResult(
        defect_id=defect.defect_id,
        professor_id=defect.professor_id,
        canonical_name=defect.canonical_name,
        source_url=defect.source_url,
        field_name=defect.field_name,
        expected_value=defect.expected_value,
        current_value_preview=current[:240],
        contamination_markers=markers,
        status=status,
    )


def _collect_p9_blockers(
    full_run_coverage: Sequence[FullRunCoverage],
    known_field_defects: Sequence[FieldDefectResult],
) -> list[str]:
    blockers: list[str] = []
    for row in full_run_coverage:
        if row.coverage_state != "covered":
            blockers.append(f"missing_full_run_seed:{row.seed_id}")
    for defect in known_field_defects:
        if defect.status != "resolved":
            blockers.append(f"field_defect:{defect.defect_id}")
    return blockers
