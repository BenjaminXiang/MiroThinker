from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Sequence


AuditReadiness = Literal["ready", "blocked"]
AuditCaseStatus = Literal["passing", "failing", "missing"]


@dataclass(frozen=True, slots=True)
class BaselineProfessorMetrics:
    total: int
    ready: int
    summary_lt_150: int
    summary_lt_200: int
    ready_summary_lt_200: int
    has_research_source_label: int
    research_overview_storage_available: bool
    missing_research_overview_zh: int
    professors_with_verified_papers: int
    professors_with_verified_missing_paper_summary: int

    @classmethod
    def empty(cls) -> BaselineProfessorMetrics:
        return cls(
            total=0,
            ready=0,
            summary_lt_150=0,
            summary_lt_200=0,
            ready_summary_lt_200=0,
            has_research_source_label=0,
            research_overview_storage_available=False,
            missing_research_overview_zh=0,
            professors_with_verified_papers=0,
            professors_with_verified_missing_paper_summary=0,
        )


@dataclass(frozen=True, slots=True)
class BaselinePaperMetrics:
    verified_links: int
    linked_papers: int
    linked_missing_abstract: int
    linked_missing_summary_zh: int
    linked_with_pdf: int
    duplicate_title_year_groups: int
    duplicate_affected_professors: int
    duplicate_groups_with_enriched_row: int
    canonical_source_distribution: dict[str, int]
    quality_status_distribution: dict[str, int]

    @classmethod
    def empty(cls) -> BaselinePaperMetrics:
        return cls(
            verified_links=0,
            linked_papers=0,
            linked_missing_abstract=0,
            linked_missing_summary_zh=0,
            linked_with_pdf=0,
            duplicate_title_year_groups=0,
            duplicate_affected_professors=0,
            duplicate_groups_with_enriched_row=0,
            canonical_source_distribution={},
            quality_status_distribution={},
        )


@dataclass(frozen=True, slots=True)
class AuditCaseResult:
    case_id: str
    entity_type: str
    status: AuditCaseStatus
    failures: list[str]
    evidence: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DatasetClosureBucketRow:
    blocker_type: str
    entity_type: str
    remediation_lane: str
    automatic_eligibility: bool
    professor_id: str | None = None
    paper_id: str | None = None
    duplicate_group_id: str | None = None
    source_page_id: str | None = None
    source_url: str | None = None
    current_status: str | None = None
    skip_reason: str | None = None
    evidence: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DatasetClosureBuckets:
    bucket_limit: int
    summary: dict[str, dict[str, Any]]
    rows: list[DatasetClosureBucketRow]


@dataclass(frozen=True, slots=True)
class CoreProfilePaperQualityAuditInputs:
    professor_metrics: BaselineProfessorMetrics
    paper_metrics: BaselinePaperMetrics
    cases: list[AuditCaseResult]


@dataclass(frozen=True, slots=True)
class CoreProfilePaperQualityAuditReport:
    blockers: list[str]
    cases: list[AuditCaseResult]
    paper_metrics: BaselinePaperMetrics
    professor_metrics: BaselineProfessorMetrics
    readiness: AuditReadiness


def build_core_profile_paper_quality_report(
    *,
    professor_metrics: BaselineProfessorMetrics,
    paper_metrics: BaselinePaperMetrics,
    cases: Sequence[AuditCaseResult],
) -> CoreProfilePaperQualityAuditReport:
    blockers = _collect_blockers(
        professor_metrics=professor_metrics,
        paper_metrics=paper_metrics,
        cases=cases,
    )
    return CoreProfilePaperQualityAuditReport(
        blockers=blockers,
        cases=list(cases),
        paper_metrics=paper_metrics,
        professor_metrics=professor_metrics,
        readiness="blocked" if blockers else "ready",
    )


def format_core_profile_paper_quality_report(
    report: CoreProfilePaperQualityAuditReport,
    *,
    closure_buckets: DatasetClosureBuckets | None = None,
) -> str:
    payload = asdict(report)
    if closure_buckets is not None:
        payload["closure_buckets"] = asdict(closure_buckets)
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_dataset_closure_bucket_report(
    *,
    professor_metrics: BaselineProfessorMetrics,
    paper_metrics: BaselinePaperMetrics,
    bucket_limit: int,
    rows: Sequence[DatasetClosureBucketRow],
) -> DatasetClosureBuckets:
    rows_by_type: dict[str, int] = {}
    for row in rows:
        rows_by_type[row.blocker_type] = rows_by_type.get(row.blocker_type, 0) + 1
    summary = {
        "ready_summary_lt_200": _bucket_summary(
            total=professor_metrics.ready_summary_lt_200,
            sampled=rows_by_type.get("ready_summary_lt_200", 0),
            bucket_limit=bucket_limit,
            remediation_lane="profile_summary_repair",
        ),
        "missing_research_overview_zh": _bucket_summary(
            total=professor_metrics.missing_research_overview_zh,
            sampled=rows_by_type.get("missing_research_overview_zh", 0),
            bucket_limit=bucket_limit,
            remediation_lane="research_overview_backfill",
        ),
        "missing_professor_paper_summary": _bucket_summary(
            total=professor_metrics.professors_with_verified_missing_paper_summary,
            sampled=rows_by_type.get("missing_professor_paper_summary", 0),
            bucket_limit=bucket_limit,
            remediation_lane="professor_paper_summary_generation",
        ),
        "duplicate_verified_paper_title_year_groups": _bucket_summary(
            total=paper_metrics.duplicate_title_year_groups,
            sampled=rows_by_type.get("duplicate_verified_paper_title_year_groups", 0),
            bucket_limit=bucket_limit,
            remediation_lane="duplicate_paper_merge",
        ),
    }
    return DatasetClosureBuckets(
        bucket_limit=bucket_limit,
        summary=summary,
        rows=list(rows),
    )


def load_dataset_closure_buckets(
    conn: Any,
    *,
    professor_metrics: BaselineProfessorMetrics,
    paper_metrics: BaselinePaperMetrics,
    bucket_limit: int = 20,
) -> DatasetClosureBuckets:
    if bucket_limit < 0:
        raise ValueError("bucket_limit must be non-negative")
    rows: list[DatasetClosureBucketRow] = []
    rows.extend(_load_ready_summary_lt_200_bucket_rows(conn, bucket_limit=bucket_limit))
    rows.extend(
        _load_missing_research_overview_bucket_rows(
            conn,
            bucket_limit=bucket_limit,
            storage_available=professor_metrics.research_overview_storage_available,
        )
    )
    rows.extend(
        _load_missing_professor_paper_summary_bucket_rows(
            conn,
            bucket_limit=bucket_limit,
        )
    )
    rows.extend(_load_duplicate_paper_bucket_rows(conn, bucket_limit=bucket_limit))
    return build_dataset_closure_bucket_report(
        professor_metrics=professor_metrics,
        paper_metrics=paper_metrics,
        bucket_limit=bucket_limit,
        rows=rows,
    )


def load_case_definitions(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("case definition file must contain a JSON list")
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each case definition must be a JSON object")
        if not item.get("case_id"):
            raise ValueError("each case definition must include case_id")
        if not item.get("entity_type"):
            raise ValueError(f"case {item.get('case_id')} missing entity_type")
    return payload


def load_baseline_professor_metrics(conn: Any) -> BaselineProfessorMetrics:
    row = conn.execute(
        """
        SELECT COUNT(*)::int AS total,
               COUNT(*) FILTER (WHERE quality_status = 'ready')::int AS ready,
               COUNT(*) FILTER (
                 WHERE COALESCE(char_length(profile_summary), 0) < 150
               )::int AS summary_lt_150,
               COUNT(*) FILTER (
                 WHERE COALESCE(char_length(profile_summary), 0) < 200
               )::int AS summary_lt_200,
               COUNT(*) FILTER (
                 WHERE quality_status = 'ready'
                   AND COALESCE(char_length(profile_summary), 0) < 200
               )::int AS ready_summary_lt_200,
               COUNT(*) FILTER (
                 WHERE profile_raw_text ~* '(research|研究领域|研究方向|研究兴趣|研究概况|研究简介)'
               )::int AS has_research_source_label
          FROM professor
        """
    ).fetchone()
    storage_available = _professor_profile_section_exists(conn)
    has_research_source_label = _int_value(row, "has_research_source_label", 5)
    return BaselineProfessorMetrics(
        total=_int_value(row, "total", 0),
        ready=_int_value(row, "ready", 1),
        summary_lt_150=_int_value(row, "summary_lt_150", 2),
        summary_lt_200=_int_value(row, "summary_lt_200", 3),
        ready_summary_lt_200=_int_value(row, "ready_summary_lt_200", 4),
        has_research_source_label=has_research_source_label,
        research_overview_storage_available=storage_available,
        missing_research_overview_zh=_missing_research_overview_count(
            conn,
            storage_available=storage_available,
            fallback_count=has_research_source_label,
        ),
        professors_with_verified_papers=_professors_with_verified_papers(conn),
        professors_with_verified_missing_paper_summary=(
            _professors_with_verified_missing_paper_summary(conn)
        ),
    )


def load_baseline_paper_metrics(conn: Any) -> BaselinePaperMetrics:
    paper_row = conn.execute(
        """
        WITH linked AS (
          SELECT DISTINCT p.paper_id,
                 p.abstract_clean,
                 p.summary_zh,
                 p.canonical_source,
                 p.quality_status
            FROM professor_paper_link ppl
            JOIN paper p ON p.paper_id = ppl.paper_id
           WHERE ppl.link_status = 'verified'
        )
        SELECT (SELECT COUNT(*) FROM professor_paper_link WHERE link_status = 'verified')::int
                 AS verified_links,
               COUNT(*)::int AS linked_papers,
               COUNT(*) FILTER (
                 WHERE NULLIF(BTRIM(COALESCE(abstract_clean, '')), '') IS NULL
               )::int AS linked_missing_abstract,
               COUNT(*) FILTER (
                 WHERE NULLIF(BTRIM(COALESCE(summary_zh, '')), '') IS NULL
               )::int AS linked_missing_summary_zh
          FROM linked
        """
    ).fetchone()
    duplicates = _load_duplicate_paper_metrics(conn)
    return BaselinePaperMetrics(
        verified_links=_int_value(paper_row, "verified_links", 0),
        linked_papers=_int_value(paper_row, "linked_papers", 1),
        linked_missing_abstract=_int_value(paper_row, "linked_missing_abstract", 2),
        linked_missing_summary_zh=_int_value(
            paper_row,
            "linked_missing_summary_zh",
            3,
        ),
        linked_with_pdf=_linked_papers_with_pdf(conn),
        duplicate_title_year_groups=duplicates["duplicate_title_year_groups"],
        duplicate_affected_professors=duplicates["duplicate_affected_professors"],
        duplicate_groups_with_enriched_row=duplicates[
            "duplicate_groups_with_enriched_row"
        ],
        canonical_source_distribution=_linked_distribution(conn, "canonical_source"),
        quality_status_distribution=_linked_distribution(conn, "quality_status"),
    )


def evaluate_case_definitions(
    conn: Any,
    case_definitions: Sequence[dict[str, Any]],
) -> list[AuditCaseResult]:
    results: list[AuditCaseResult] = []
    for case in case_definitions:
        case_id = str(case["case_id"])
        if case_id == "ahmed-elazab":
            results.append(_evaluate_ahmed_case(conn, case))
        elif case_id == "ding-wenbo":
            results.append(_evaluate_ding_case(conn, case))
        elif case_id == "pfedgpa":
            results.append(_evaluate_pfedgpa_case(conn, case))
        else:
            results.append(
                AuditCaseResult(
                    case_id=case_id,
                    entity_type=str(case.get("entity_type") or "unknown"),
                    status="missing",
                    failures=["unsupported_case_definition"],
                    evidence={},
                )
            )
    return results


def _bucket_summary(
    *,
    total: int,
    sampled: int,
    bucket_limit: int,
    remediation_lane: str,
) -> dict[str, Any]:
    return {
        "total": int(total),
        "sampled": int(sampled),
        "truncated": bool(total > sampled and (bucket_limit == 0 or sampled >= bucket_limit)),
        "remediation_lane": remediation_lane,
    }


def _load_ready_summary_lt_200_bucket_rows(
    conn: Any,
    *,
    bucket_limit: int,
) -> list[DatasetClosureBucketRow]:
    rows = conn.execute(
        """
        SELECT p.professor_id,
               p.canonical_name,
               p.quality_status,
               char_length(COALESCE(p.profile_summary, ''))::int
                 AS profile_summary_length,
               p.primary_official_profile_page_id AS source_page_id,
               sp.url AS source_url,
               EXISTS (
                 SELECT 1
                   FROM professor_fact pf
                  WHERE pf.professor_id = p.professor_id
                    AND pf.status = 'active'
                    AND pf.fact_type IN (
                      'research_topic',
                      'education',
                      'work_experience',
                      'academic_position',
                      'award',
                      'honor'
                    )
               ) AS has_grounded_facts,
               NULLIF(BTRIM(COALESCE(p.profile_raw_text, '')), '') IS NOT NULL
                 AS has_profile_raw_text,
               NULLIF(BTRIM(COALESCE(p.paper_summary, '')), '') IS NOT NULL
                 AS has_paper_summary
          FROM professor p
          LEFT JOIN source_page sp
            ON sp.page_id = p.primary_official_profile_page_id
         WHERE p.quality_status = 'ready'
           AND char_length(COALESCE(p.profile_summary, '')) < 200
         ORDER BY p.professor_id ASC
         LIMIT %s
        """,
        (bucket_limit,),
    ).fetchall()
    bucket_rows: list[DatasetClosureBucketRow] = []
    for row in rows:
        automatic_eligibility, skip_reason = _classify_profile_summary_bucket(
            has_grounded_facts=bool(_record_value(row, "has_grounded_facts", 6)),
            has_profile_raw_text=bool(_record_value(row, "has_profile_raw_text", 7)),
        )
        bucket_rows.append(
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id=str(_record_value(row, "professor_id", 0)),
                current_status=str(_record_value(row, "quality_status", 2) or ""),
                automatic_eligibility=automatic_eligibility,
                skip_reason=skip_reason,
                source_page_id=_optional_str(_record_value(row, "source_page_id", 4)),
                source_url=_optional_str(_record_value(row, "source_url", 5)),
                evidence={
                    "canonical_name": _record_value(row, "canonical_name", 1),
                    "profile_summary_length": _int_value(
                        row,
                        "profile_summary_length",
                        3,
                    ),
                    "has_grounded_facts": bool(
                        _record_value(row, "has_grounded_facts", 6)
                    ),
                    "has_profile_raw_text": bool(
                        _record_value(row, "has_profile_raw_text", 7)
                    ),
                    "has_paper_summary": bool(
                        _record_value(row, "has_paper_summary", 8)
                    ),
                },
            )
        )
    return bucket_rows


def _load_missing_research_overview_bucket_rows(
    conn: Any,
    *,
    bucket_limit: int,
    storage_available: bool,
) -> list[DatasetClosureBucketRow]:
    if storage_available:
        rows = conn.execute(
            """
            SELECT p.professor_id,
                   p.canonical_name,
                   p.quality_status,
                   p.primary_official_profile_page_id AS source_page_id,
                   sp.url AS source_url,
                   p.profile_raw_text
              FROM professor p
              LEFT JOIN source_page sp
                ON sp.page_id = p.primary_official_profile_page_id
             WHERE p.profile_raw_text ~* '(research|研究领域|研究方向|研究兴趣|研究概况|研究简介)'
               AND NOT EXISTS (
                 SELECT 1
                   FROM professor_profile_section section
                  WHERE section.professor_id = p.professor_id
                    AND section.section_type = 'research_overview'
                    AND section.language = 'zh'
                    AND NULLIF(BTRIM(section.content), '') IS NOT NULL
               )
             ORDER BY p.professor_id ASC
             LIMIT %s
            """,
            (bucket_limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT p.professor_id,
                   p.canonical_name,
                   p.quality_status,
                   p.primary_official_profile_page_id AS source_page_id,
                   sp.url AS source_url,
                   p.profile_raw_text
              FROM professor p
              LEFT JOIN source_page sp
                ON sp.page_id = p.primary_official_profile_page_id
             WHERE p.profile_raw_text ~* '(research|研究领域|研究方向|研究兴趣|研究概况|研究简介)'
             ORDER BY p.professor_id ASC
             LIMIT %s
            """,
            (bucket_limit,),
        ).fetchall()
    bucket_rows: list[DatasetClosureBucketRow] = []
    for row in rows:
        profile_raw_text = str(_record_value(row, "profile_raw_text", 5) or "")
        automatic_eligibility, skip_reason, source_language = (
            _classify_research_overview_bucket(profile_raw_text)
        )
        bucket_rows.append(
            DatasetClosureBucketRow(
                blocker_type="missing_research_overview_zh",
                entity_type="professor",
                remediation_lane="research_overview_backfill",
                professor_id=str(_record_value(row, "professor_id", 0)),
                current_status=str(_record_value(row, "quality_status", 2) or ""),
                automatic_eligibility=automatic_eligibility,
                skip_reason=skip_reason,
                source_page_id=_optional_str(_record_value(row, "source_page_id", 3)),
                source_url=_optional_str(_record_value(row, "source_url", 4)),
                evidence={
                    "canonical_name": _record_value(row, "canonical_name", 1),
                    "source_language": source_language,
                    "profile_raw_text_length": len(profile_raw_text),
                    "storage_available": storage_available,
                },
            )
        )
    return bucket_rows


def _load_missing_professor_paper_summary_bucket_rows(
    conn: Any,
    *,
    bucket_limit: int,
) -> list[DatasetClosureBucketRow]:
    rows = conn.execute(
        """
        WITH verified_links AS (
          SELECT ppl.professor_id,
                 COALESCE(pma.canonical_paper_id, ppl.paper_id) AS resolved_paper_id
            FROM professor_paper_link ppl
            LEFT JOIN paper_merge_alias pma ON pma.old_paper_id = ppl.paper_id
           WHERE ppl.link_status = 'verified'
        ),
        duplicate_groups AS (
          SELECT vl.professor_id,
                 lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g'))
                   AS title_key,
                 p.year,
                 COUNT(DISTINCT p.paper_id)::int AS paper_count
            FROM verified_links vl
            JOIN paper p ON p.paper_id = vl.resolved_paper_id
           WHERE NULLIF(BTRIM(COALESCE(p.title_clean, '')), '') IS NOT NULL
           GROUP BY vl.professor_id,
                    lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g')),
                    p.year
          HAVING COUNT(DISTINCT p.paper_id) > 1
        )
        SELECT p.professor_id,
               p.canonical_name,
               p.quality_status,
               COUNT(DISTINCT vl.resolved_paper_id)::int AS verified_paper_count,
               COUNT(DISTINCT dg.title_key)::int AS duplicate_group_count
          FROM professor p
          JOIN verified_links vl ON vl.professor_id = p.professor_id
          LEFT JOIN duplicate_groups dg ON dg.professor_id = p.professor_id
         WHERE NULLIF(BTRIM(COALESCE(p.paper_summary, '')), '') IS NULL
         GROUP BY p.professor_id, p.canonical_name, p.quality_status
         ORDER BY p.professor_id ASC
         LIMIT %s
        """,
        (bucket_limit,),
    ).fetchall()
    bucket_rows: list[DatasetClosureBucketRow] = []
    for row in rows:
        duplicate_group_count = _int_value(row, "duplicate_group_count", 4)
        automatic_eligibility, skip_reason = _classify_professor_paper_summary_bucket(
            duplicate_group_count=duplicate_group_count,
        )
        bucket_rows.append(
            DatasetClosureBucketRow(
                blocker_type="missing_professor_paper_summary",
                entity_type="professor",
                remediation_lane="professor_paper_summary_generation",
                professor_id=str(_record_value(row, "professor_id", 0)),
                current_status=str(_record_value(row, "quality_status", 2) or ""),
                automatic_eligibility=automatic_eligibility,
                skip_reason=skip_reason,
                evidence={
                    "canonical_name": _record_value(row, "canonical_name", 1),
                    "verified_paper_count": _int_value(
                        row,
                        "verified_paper_count",
                        3,
                    ),
                    "duplicate_group_count": duplicate_group_count,
                },
            )
        )
    return bucket_rows


def _load_duplicate_paper_bucket_rows(
    conn: Any,
    *,
    bucket_limit: int,
) -> list[DatasetClosureBucketRow]:
    rows = conn.execute(
        """
        WITH verified_links AS (
          SELECT ppl.professor_id,
                 COALESCE(pma.canonical_paper_id, ppl.paper_id) AS resolved_paper_id,
                 MIN(ppl.evidence_page_id::text)::uuid AS source_page_id
            FROM professor_paper_link ppl
            LEFT JOIN paper_merge_alias pma ON pma.old_paper_id = ppl.paper_id
           WHERE ppl.link_status = 'verified'
           GROUP BY ppl.professor_id,
                    COALESCE(pma.canonical_paper_id, ppl.paper_id)
        ),
        groups AS (
          SELECT vl.professor_id,
                 lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g'))
                   AS title_key,
                 p.year,
                 array_agg(DISTINCT vl.resolved_paper_id ORDER BY vl.resolved_paper_id)
                   AS paper_ids,
                 array_agg(DISTINCT COALESCE(p.canonical_source, 'missing')
                           ORDER BY COALESCE(p.canonical_source, 'missing'))
                   AS canonical_sources,
                 COUNT(DISTINCT vl.resolved_paper_id)::int AS paper_count,
                 COUNT(DISTINCT NULLIF(BTRIM(COALESCE(p.doi, '')), ''))::int
                   AS doi_count,
                 COUNT(DISTINCT NULLIF(BTRIM(COALESCE(p.arxiv_id, '')), ''))::int
                   AS arxiv_count,
                 BOOL_OR(COALESCE(p.canonical_source, '') != 'prof_page_only')
                   AS has_enriched_row,
                 MIN(vl.source_page_id::text)::uuid AS source_page_id
            FROM verified_links vl
            JOIN paper p ON p.paper_id = vl.resolved_paper_id
           WHERE NULLIF(BTRIM(COALESCE(p.title_clean, '')), '') IS NOT NULL
           GROUP BY vl.professor_id,
                    lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g')),
                    p.year
          HAVING COUNT(DISTINCT vl.resolved_paper_id) > 1
        )
        SELECT g.professor_id,
               prof.canonical_name,
               prof.quality_status,
               g.title_key,
               g.year,
               g.paper_ids,
               g.canonical_sources,
               g.paper_count,
               g.doi_count,
               g.arxiv_count,
               g.has_enriched_row,
               g.source_page_id,
               sp.url AS source_url
          FROM groups g
          JOIN professor prof ON prof.professor_id = g.professor_id
          LEFT JOIN source_page sp ON sp.page_id = g.source_page_id
         ORDER BY g.professor_id ASC, g.year DESC NULLS LAST, g.title_key ASC
         LIMIT %s
        """,
        (bucket_limit,),
    ).fetchall()
    bucket_rows: list[DatasetClosureBucketRow] = []
    for row in rows:
        paper_ids = _jsonable_sequence(_record_value(row, "paper_ids", 5))
        canonical_sources = _jsonable_sequence(
            _record_value(row, "canonical_sources", 6)
        )
        doi_count = _int_value(row, "doi_count", 8)
        arxiv_count = _int_value(row, "arxiv_count", 9)
        has_enriched_row = bool(_record_value(row, "has_enriched_row", 10))
        automatic_eligibility, skip_reason = _classify_duplicate_paper_bucket(
            has_enriched_row=has_enriched_row,
            doi_count=doi_count,
            arxiv_count=arxiv_count,
        )
        professor_id = str(_record_value(row, "professor_id", 0))
        year = _record_value(row, "year", 4)
        title_key = str(_record_value(row, "title_key", 3) or "")
        bucket_rows.append(
            DatasetClosureBucketRow(
                blocker_type="duplicate_verified_paper_title_year_groups",
                entity_type="paper_group",
                remediation_lane="duplicate_paper_merge",
                professor_id=professor_id,
                duplicate_group_id=(
                    f"{professor_id}:{year or 'unknown'}:{title_key[:48]}"
                ),
                source_page_id=_optional_str(_record_value(row, "source_page_id", 11)),
                source_url=_optional_str(_record_value(row, "source_url", 12)),
                current_status="verified_duplicate",
                automatic_eligibility=automatic_eligibility,
                skip_reason=skip_reason,
                evidence={
                    "canonical_name": _record_value(row, "canonical_name", 1),
                    "professor_quality_status": _record_value(
                        row,
                        "quality_status",
                        2,
                    ),
                    "year": year,
                    "paper_ids": paper_ids,
                    "canonical_sources": canonical_sources,
                    "paper_count": _int_value(row, "paper_count", 7),
                    "doi_count": doi_count,
                    "arxiv_count": arxiv_count,
                    "has_enriched_row": has_enriched_row,
                },
            )
        )
    return bucket_rows


def _classify_profile_summary_bucket(
    *,
    has_grounded_facts: bool,
    has_profile_raw_text: bool,
) -> tuple[bool, str | None]:
    automatic_eligibility = has_grounded_facts or has_profile_raw_text
    return (
        automatic_eligibility,
        None if automatic_eligibility else "missing_grounded_profile_inputs",
    )


def _classify_research_overview_bucket(
    profile_raw_text: str | None,
) -> tuple[bool, str | None, str | None]:
    source_language = _infer_source_language(profile_raw_text)
    automatic_eligibility = source_language is not None
    return (
        automatic_eligibility,
        None if automatic_eligibility else "missing_official_source_text",
        source_language,
    )


def _classify_professor_paper_summary_bucket(
    *,
    duplicate_group_count: int,
) -> tuple[bool, str | None]:
    automatic_eligibility = duplicate_group_count == 0
    return (
        automatic_eligibility,
        None if automatic_eligibility else "duplicate_verified_paper_links",
    )


def _classify_duplicate_paper_bucket(
    *,
    has_enriched_row: bool,
    doi_count: int,
    arxiv_count: int,
) -> tuple[bool, str | None]:
    automatic_eligibility = has_enriched_row and (doi_count > 0 or arxiv_count > 0)
    return (
        automatic_eligibility,
        None if automatic_eligibility else "ambiguous_fuzzy_match",
    )


def _collect_blockers(
    *,
    professor_metrics: BaselineProfessorMetrics,
    paper_metrics: BaselinePaperMetrics,
    cases: Sequence[AuditCaseResult],
) -> list[str]:
    blockers: list[str] = []
    if professor_metrics.ready_summary_lt_200:
        blockers.append(f"ready_summary_lt_200:{professor_metrics.ready_summary_lt_200}")
    if professor_metrics.missing_research_overview_zh:
        blockers.append(
            f"missing_research_overview_zh:{professor_metrics.missing_research_overview_zh}"
        )
    if professor_metrics.professors_with_verified_missing_paper_summary:
        blockers.append(
            "missing_professor_paper_summary:"
            f"{professor_metrics.professors_with_verified_missing_paper_summary}"
        )
    if paper_metrics.duplicate_title_year_groups:
        blockers.append(
            "duplicate_verified_paper_title_year_groups:"
            f"{paper_metrics.duplicate_title_year_groups}"
        )
    for case in cases:
        if case.status != "passing":
            blockers.append(f"case_failed:{case.case_id}")
    return blockers


def _professor_profile_section_exists(conn: Any) -> bool:
    row = conn.execute(
        "SELECT to_regclass('public.professor_profile_section') IS NOT NULL AS exists"
    ).fetchone()
    return bool(_record_value(row, "exists", 0))


def _missing_research_overview_count(
    conn: Any,
    *,
    storage_available: bool,
    fallback_count: int,
) -> int:
    if not storage_available:
        return int(fallback_count)
    row = conn.execute(
        """
        SELECT COUNT(*)::int AS count
          FROM professor p
         WHERE p.profile_raw_text ~* '(research|研究领域|研究方向|研究兴趣|研究概况|研究简介)'
           AND NOT EXISTS (
             SELECT 1
               FROM professor_profile_section section
              WHERE section.professor_id = p.professor_id
                AND section.section_type = 'research_overview'
                AND section.language = 'zh'
                AND NULLIF(BTRIM(section.content), '') IS NOT NULL
           )
        """
    ).fetchone()
    return _int_value(row, "count", 0)


def _professors_with_verified_papers(conn: Any) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT professor_id)::int AS count
          FROM professor_paper_link
         WHERE link_status = 'verified'
        """
    ).fetchone()
    return _int_value(row, "count", 0)


def _professors_with_verified_missing_paper_summary(conn: Any) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT p.professor_id)::int AS count
          FROM professor p
          JOIN professor_paper_link ppl ON ppl.professor_id = p.professor_id
         WHERE ppl.link_status = 'verified'
           AND NULLIF(BTRIM(COALESCE(p.paper_summary, '')), '') IS NULL
        """
    ).fetchone()
    return _int_value(row, "count", 0)


def _load_duplicate_paper_metrics(conn: Any) -> dict[str, int]:
    row = conn.execute(
        """
        WITH groups AS (
          SELECT ppl.professor_id,
                 lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g')) AS title_key,
                 p.year,
                 COUNT(DISTINCT p.paper_id)::int AS paper_count,
                 BOOL_OR(COALESCE(p.canonical_source, '') != 'prof_page_only')
                   AS has_enriched_row
            FROM professor_paper_link ppl
            JOIN paper p ON p.paper_id = ppl.paper_id
           WHERE ppl.link_status = 'verified'
             AND NULLIF(BTRIM(COALESCE(p.title_clean, '')), '') IS NOT NULL
           GROUP BY ppl.professor_id,
                    lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g')),
                    p.year
          HAVING COUNT(DISTINCT p.paper_id) > 1
        )
        SELECT COUNT(*)::int AS duplicate_title_year_groups,
               COUNT(DISTINCT professor_id)::int AS duplicate_affected_professors,
               COUNT(*) FILTER (WHERE has_enriched_row)::int
                 AS duplicate_groups_with_enriched_row
          FROM groups
        """
    ).fetchone()
    return {
        "duplicate_title_year_groups": _int_value(
            row,
            "duplicate_title_year_groups",
            0,
        ),
        "duplicate_affected_professors": _int_value(
            row,
            "duplicate_affected_professors",
            1,
        ),
        "duplicate_groups_with_enriched_row": _int_value(
            row,
            "duplicate_groups_with_enriched_row",
            2,
        ),
    }


def _linked_papers_with_pdf(conn: Any) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT p.paper_id)::int AS count
          FROM professor_paper_link ppl
          JOIN paper p ON p.paper_id = ppl.paper_id
          JOIN paper_full_text pft ON pft.paper_id = p.paper_id
         WHERE ppl.link_status = 'verified'
           AND NULLIF(BTRIM(COALESCE(pft.pdf_url, '')), '') IS NOT NULL
        """
    ).fetchone()
    return _int_value(row, "count", 0)


def _linked_distribution(conn: Any, column: str) -> dict[str, int]:
    if column not in {"canonical_source", "quality_status"}:
        raise ValueError(f"unsupported distribution column: {column}")
    rows = conn.execute(
        f"""
        WITH linked AS (
          SELECT DISTINCT p.paper_id, COALESCE(p.{column}, 'missing') AS key
            FROM professor_paper_link ppl
            JOIN paper p ON p.paper_id = ppl.paper_id
           WHERE ppl.link_status = 'verified'
        )
        SELECT key, COUNT(*)::int AS count
          FROM linked
         GROUP BY key
         ORDER BY count DESC, key ASC
        """
    ).fetchall()
    return {str(_record_value(row, "key", 0)): _int_value(row, "count", 1) for row in rows}


def _evaluate_ahmed_case(conn: Any, case: dict[str, Any]) -> AuditCaseResult:
    professor_id = str(case["professor_id"])
    failures: list[str] = []
    professor = _fetch_professor(conn, professor_id)
    if professor is None:
        return AuditCaseResult(
            case_id=str(case["case_id"]),
            entity_type=str(case["entity_type"]),
            status="missing",
            failures=["professor_missing"],
            evidence={"professor_id": professor_id},
        )
    if not _has_research_overview_zh(conn, professor_id):
        failures.append("missing_research_overview_zh")
    if not _has_nonempty_field(professor, "paper_summary", 9):
        failures.append("missing_paper_summary")
    duplicate_title = str(case.get("duplicate_paper_title") or "")
    duplicate_count = _active_verified_title_count(
        conn,
        professor_id=professor_id,
        title_prefix=duplicate_title[:45],
    )
    if duplicate_count > 1:
        failures.append("duplicate_verified_paper")
    return AuditCaseResult(
        case_id=str(case["case_id"]),
        entity_type=str(case["entity_type"]),
        status="failing" if failures else "passing",
        failures=failures,
        evidence={
            "professor_id": professor_id,
            "quality_status": _record_value(professor, "quality_status", 7),
            "paper_summary_present": _has_nonempty_field(professor, "paper_summary", 9),
            "duplicate_title_active_verified_count": duplicate_count,
        },
    )


def _evaluate_ding_case(conn: Any, case: dict[str, Any]) -> AuditCaseResult:
    professor_id = str(case["professor_id"])
    failures: list[str] = []
    professor = _fetch_professor(conn, professor_id)
    if professor is None:
        return AuditCaseResult(
            case_id=str(case["case_id"]),
            entity_type=str(case["entity_type"]),
            status="missing",
            failures=["professor_missing"],
            evidence={"professor_id": professor_id},
        )
    summary = str(_record_value(professor, "profile_summary", 8) or "")
    if len(summary) < 200:
        failures.append("profile_summary_too_short")
    fact_counts = _active_fact_counts(conn, professor_id)
    required_fact_types = {
        "education": "missing_education",
        "work_experience": "missing_work_experience",
        "research_topic": "missing_research_directions",
        "academic_position": "missing_academic_positions",
        "award": "missing_awards",
    }
    for fact_type, failure in required_fact_types.items():
        if fact_counts.get(fact_type, 0) <= 0:
            failures.append(failure)
    return AuditCaseResult(
        case_id=str(case["case_id"]),
        entity_type=str(case["entity_type"]),
        status="failing" if failures else "passing",
        failures=failures,
        evidence={
            "professor_id": professor_id,
            "quality_status": _record_value(professor, "quality_status", 7),
            "profile_summary_length": len(summary),
            "fact_counts": fact_counts,
            "professor_core_readiness_excludes": case.get(
                "professor_core_readiness_excludes",
                [],
            ),
        },
    )


def _evaluate_pfedgpa_case(conn: Any, case: dict[str, Any]) -> AuditCaseResult:
    expected_arxiv = str(case.get("expected_external_identifier") or "")
    expected_arxiv_id = expected_arxiv.removeprefix("arxiv:")
    row = conn.execute(
        """
        SELECT p.paper_id,
               p.title_clean,
               p.arxiv_id,
               p.quality_status,
               p.canonical_source,
               pft.pdf_url,
               requested_alias.canonical_paper_id AS alias_target
          FROM paper p
          LEFT JOIN paper_merge_alias requested_alias
                 ON requested_alias.old_paper_id = %s
          LEFT JOIN paper_full_text pft ON pft.paper_id = p.paper_id
         WHERE p.paper_id = COALESCE(requested_alias.canonical_paper_id, %s)
            OR p.title_clean = %s
         ORDER BY p.paper_id = COALESCE(requested_alias.canonical_paper_id, %s) DESC,
                  p.paper_id = %s DESC,
                  p.paper_id ASC
         LIMIT 1
        """,
        (
            case.get("paper_id"),
            case.get("paper_id"),
            case.get("title"),
            case.get("paper_id"),
            case.get("paper_id"),
        ),
    ).fetchone()
    if row is None:
        return AuditCaseResult(
            case_id=str(case["case_id"]),
            entity_type=str(case["entity_type"]),
            status="missing",
            failures=["paper_missing"],
            evidence={"paper_id": case.get("paper_id"), "title": case.get("title")},
        )
    failures: list[str] = []
    arxiv_id = str(_record_value(row, "arxiv_id", 2) or "")
    pdf_url = str(_record_value(row, "pdf_url", 5) or "")
    if expected_arxiv_id and expected_arxiv_id not in arxiv_id:
        failures.append("missing_arxiv_id")
    if not pdf_url:
        failures.append("missing_arxiv_pdf")
    return AuditCaseResult(
        case_id=str(case["case_id"]),
        entity_type=str(case["entity_type"]),
        status="failing" if failures else "passing",
        failures=failures,
        evidence={
            "paper_id": _record_value(row, "paper_id", 0),
            "arxiv_id": arxiv_id or None,
            "pdf_url": pdf_url or None,
            "quality_status": _record_value(row, "quality_status", 3),
            "canonical_source": _record_value(row, "canonical_source", 4),
            "expected_route": f"/paper/{_record_value(row, 'paper_id', 0)}",
            "merged_from_paper_id": (
                case.get("paper_id")
                if _record_value(row, "alias_target", 6)
                else None
            ),
        },
    )


def _fetch_professor(conn: Any, professor_id: str) -> Any | None:
    return conn.execute(
        """
        SELECT professor_id,
               canonical_name,
               canonical_name_en,
               identity_status,
               lifecycle_state,
               lifecycle_merged_into_id,
               primary_official_profile_page_id,
               quality_status,
               profile_summary,
               paper_summary
          FROM professor
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchone()


def _has_research_overview_zh(conn: Any, professor_id: str) -> bool:
    if not _professor_profile_section_exists(conn):
        return False
    row = conn.execute(
        """
        SELECT EXISTS (
          SELECT 1
            FROM professor_profile_section
           WHERE professor_id = %s
             AND section_type = 'research_overview'
             AND language = 'zh'
             AND NULLIF(BTRIM(content), '') IS NOT NULL
        ) AS exists
        """,
        (professor_id,),
    ).fetchone()
    return bool(_record_value(row, "exists", 0))


def _active_verified_title_count(
    conn: Any,
    *,
    professor_id: str,
    title_prefix: str,
) -> int:
    normalized_prefix = _normalize_title_prefix(title_prefix)
    if not normalized_prefix:
        return 0
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT p.paper_id)::int AS count
          FROM professor_paper_link ppl
          JOIN paper p ON p.paper_id = ppl.paper_id
         WHERE ppl.professor_id = %s
           AND ppl.link_status = 'verified'
           AND lower(
                 regexp_replace(
                   replace(replace(p.title_clean, '’', ''), '''', ''),
                   '\\s+',
                   ' ',
                   'g'
                 )
               ) LIKE %s
        """,
        (professor_id, f"{normalized_prefix}%"),
    ).fetchone()
    return _int_value(row, "count", 0)


def _normalize_title_prefix(value: str) -> str:
    normalized = value.replace("’", "").replace("'", "").lower()
    return re.sub(r"\s+", " ", normalized).strip()


def _active_fact_counts(conn: Any, professor_id: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT fact_type, COUNT(*)::int AS count
          FROM professor_fact
         WHERE professor_id = %s
           AND status = 'active'
         GROUP BY fact_type
         ORDER BY fact_type
        """,
        (professor_id,),
    ).fetchall()
    return {
        str(_record_value(row, "fact_type", 0)): _int_value(row, "count", 1)
        for row in rows
    }


def _has_nonempty_field(row: Any, key: str, index: int) -> bool:
    value = _record_value(row, key, index)
    return bool(str(value or "").strip())


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _jsonable_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _infer_source_language(value: str | None) -> str | None:
    text = value or ""
    if not text.strip():
        return None
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    return "en"


def _int_value(row: Any, key: str, index: int) -> int:
    return int(_record_value(row, key, index) or 0)


def _record_value(row: Any, key: str, index: int) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError):
        return row[index]
