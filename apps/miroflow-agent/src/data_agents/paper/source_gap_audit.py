from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Sequence

from src.data_agents.paper.source_text_quality import is_usable_paper_source_text


class PaperSourceGapLane(str, Enum):
    EXISTING_SOURCE_SUMMARY_FAST_PATH = "existing_source_summary_fast_path"
    IDENTIFIER_METADATA_ENRICHMENT = "identifier_metadata_enrichment"
    PROFESSOR_PAGE_FULL_TEXT_ACQUISITION = "professor_page_full_text_acquisition"
    PROF_PAGE_ONLY_TITLE_PARSER_CLEANUP = "prof_page_only_title_parser_cleanup"
    REVIEW_ONLY_RESIDUAL = "review_only_residual"
    UNSAFE_ROW = "unsafe_row"


_LANE_ORDER = tuple(PaperSourceGapLane)
@dataclass(frozen=True, slots=True)
class PaperSourceGapClassification:
    paper_id: str
    primary_lane: str
    secondary_lanes: tuple[str, ...]
    eligible_for_summary: bool
    skip_reason: str | None
    source_text_field: str | None
    evidence: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PaperSourceGapLaneReport:
    lane: str
    total: int
    sample_paper_ids: tuple[str, ...]
    selection_hash: str
    skip_reason_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class PaperSourceGapAuditReport:
    total_rows: int
    lane_counts: dict[str, int]
    source_buckets: dict[str, int]
    lanes: dict[str, PaperSourceGapLaneReport]
    rows: tuple[PaperSourceGapClassification, ...]


def classify_source_gap_row(row: dict[str, Any]) -> PaperSourceGapClassification:
    paper_id = _text(row.get("paper_id")) or ""
    source_text_field = _usable_source_text_field(row)
    secondary_lanes = _secondary_lanes(row, source_text_field=source_text_field)
    evidence = _classification_evidence(row)

    identity_status = _text(row.get("identity_status")) or "unverified"
    quality_status = _text(row.get("quality_status")) or "needs_enrichment"
    if identity_status in {"rejected", "merged"}:
        return PaperSourceGapClassification(
            paper_id=paper_id,
            primary_lane=PaperSourceGapLane.UNSAFE_ROW.value,
            secondary_lanes=(),
            eligible_for_summary=False,
            skip_reason="terminal_identity_status",
            source_text_field=source_text_field,
            evidence=evidence,
        )
    if quality_status == "rejected":
        return PaperSourceGapClassification(
            paper_id=paper_id,
            primary_lane=PaperSourceGapLane.UNSAFE_ROW.value,
            secondary_lanes=(),
            eligible_for_summary=False,
            skip_reason="rejected_quality_status",
            source_text_field=source_text_field,
            evidence=evidence,
        )
    if source_text_field is not None:
        eligible_for_summary = not bool(_text(row.get("summary_zh")))
        return PaperSourceGapClassification(
            paper_id=paper_id,
            primary_lane=PaperSourceGapLane.EXISTING_SOURCE_SUMMARY_FAST_PATH.value,
            secondary_lanes=secondary_lanes,
            eligible_for_summary=eligible_for_summary,
            skip_reason=None,
            source_text_field=source_text_field,
            evidence=evidence,
        )
    if _has_identifier(row):
        return PaperSourceGapClassification(
            paper_id=paper_id,
            primary_lane=PaperSourceGapLane.IDENTIFIER_METADATA_ENRICHMENT.value,
            secondary_lanes=secondary_lanes,
            eligible_for_summary=False,
            skip_reason="missing_usable_source_text",
            source_text_field=None,
            evidence=evidence,
        )
    if _text(row.get("pdf_url")):
        return PaperSourceGapClassification(
            paper_id=paper_id,
            primary_lane=PaperSourceGapLane.PROFESSOR_PAGE_FULL_TEXT_ACQUISITION.value,
            secondary_lanes=_without_lane(
                secondary_lanes,
                PaperSourceGapLane.PROFESSOR_PAGE_FULL_TEXT_ACQUISITION,
            ),
            eligible_for_summary=False,
            skip_reason="pdf_available_but_no_usable_text",
            source_text_field=None,
            evidence=evidence,
        )
    if _canonical_source(row) == "prof_page_only":
        return PaperSourceGapClassification(
            paper_id=paper_id,
            primary_lane=PaperSourceGapLane.PROF_PAGE_ONLY_TITLE_PARSER_CLEANUP.value,
            secondary_lanes=secondary_lanes,
            eligible_for_summary=False,
            skip_reason="prof_page_only_missing_identifier_or_source",
            source_text_field=None,
            evidence=evidence,
        )
    return PaperSourceGapClassification(
        paper_id=paper_id,
        primary_lane=PaperSourceGapLane.REVIEW_ONLY_RESIDUAL.value,
        secondary_lanes=secondary_lanes,
        eligible_for_summary=False,
        skip_reason="no_supported_source_action",
        source_text_field=None,
        evidence=evidence,
    )


def build_source_gap_audit_report(
    rows: Sequence[dict[str, Any]],
    *,
    sample_limit: int = 20,
) -> PaperSourceGapAuditReport:
    if sample_limit < 0:
        raise ValueError("sample_limit must be non-negative")
    classifications = tuple(classify_source_gap_row(dict(row)) for row in rows)
    lane_to_ids: dict[str, list[str]] = defaultdict(list)
    lane_skip_reasons: dict[str, Counter[str]] = defaultdict(Counter)
    source_buckets: Counter[str] = Counter()
    for row, classification in zip(rows, classifications, strict=True):
        lane_to_ids[classification.primary_lane].append(classification.paper_id)
        if classification.skip_reason:
            lane_skip_reasons[classification.primary_lane][classification.skip_reason] += 1
        source_buckets[_canonical_source(row)] += 1

    lanes: dict[str, PaperSourceGapLaneReport] = {}
    for lane in _LANE_ORDER:
        ids = sorted(lane_to_ids.get(lane.value, []))
        if not ids:
            continue
        lanes[lane.value] = PaperSourceGapLaneReport(
            lane=lane.value,
            total=len(ids),
            sample_paper_ids=tuple(ids[:sample_limit]),
            selection_hash=selection_hash_for_lane(lane, ids),
            skip_reason_counts=dict(sorted(lane_skip_reasons[lane.value].items())),
        )
    lane_counts = {lane: report.total for lane, report in lanes.items()}
    return PaperSourceGapAuditReport(
        total_rows=len(classifications),
        lane_counts=lane_counts,
        source_buckets=dict(sorted(source_buckets.items())),
        lanes=lanes,
        rows=classifications,
    )


def selection_hash_for_lane(
    lane: PaperSourceGapLane | str,
    paper_ids: Sequence[str],
) -> str:
    lane_value = lane.value if isinstance(lane, PaperSourceGapLane) else str(lane)
    payload = {
        "lane": lane_value,
        "paper_ids": sorted(str(paper_id) for paper_id in paper_ids),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def format_source_gap_audit_report(report: PaperSourceGapAuditReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_source_gap_rows(conn: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT %s"
        params.append(int(limit))
    cursor = conn.execute(
        f"""
        SELECT p.paper_id,
               p.title_clean,
               p.canonical_source,
               p.identity_status,
               p.quality_status,
               p.summary_zh,
               p.abstract_clean,
               p.doi,
               p.arxiv_id,
               p.openalex_id,
               pft.abstract AS full_text_abstract,
               pft.intro AS full_text_intro,
               pft.pdf_url,
               pft.fetch_error
          FROM paper p
          LEFT JOIN paper_full_text pft ON pft.paper_id = p.paper_id
          LEFT JOIN paper_merge_alias pma ON pma.old_paper_id = p.paper_id
         WHERE pma.old_paper_id IS NULL
           AND COALESCE(p.identity_status, 'unverified') NOT IN ('rejected', 'merged')
           AND COALESCE(p.quality_status, 'needs_enrichment') != 'rejected'
           AND (
                NULLIF(BTRIM(COALESCE(p.summary_zh, '')), '') IS NULL
             OR NULLIF(BTRIM(COALESCE(p.abstract_clean, '')), '') IS NULL
           )
         ORDER BY p.paper_id
        {limit_sql}
        """,
        tuple(params),
    )
    return [dict(row) for row in cursor.fetchall()]


def _secondary_lanes(
    row: dict[str, Any],
    *,
    source_text_field: str | None,
) -> tuple[str, ...]:
    lanes: list[PaperSourceGapLane] = []
    if source_text_field is not None and _has_identifier(row):
        lanes.append(PaperSourceGapLane.IDENTIFIER_METADATA_ENRICHMENT)
    if _text(row.get("pdf_url")):
        lanes.append(PaperSourceGapLane.PROFESSOR_PAGE_FULL_TEXT_ACQUISITION)
    if _canonical_source(row) == "prof_page_only":
        lanes.append(PaperSourceGapLane.PROF_PAGE_ONLY_TITLE_PARSER_CLEANUP)
    return tuple(lane.value for lane in lanes if lane.value)


def _without_lane(
    lanes: tuple[str, ...],
    lane: PaperSourceGapLane,
) -> tuple[str, ...]:
    return tuple(item for item in lanes if item != lane.value)


def _classification_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_source": _canonical_source(row),
        "has_summary_zh": bool(_text(row.get("summary_zh"))),
        "has_abstract_clean": bool(_text(row.get("abstract_clean"))),
        "has_full_text_abstract": bool(_text(row.get("full_text_abstract"))),
        "has_full_text_intro": bool(_text(row.get("full_text_intro"))),
        "has_pdf_url": bool(_text(row.get("pdf_url"))),
        "has_doi": bool(_text(row.get("doi"))),
        "has_arxiv_id": bool(_text(row.get("arxiv_id"))),
        "has_openalex_id": bool(_text(row.get("openalex_id"))),
    }


def _usable_source_text_field(row: dict[str, Any]) -> str | None:
    if _is_usable_source_text(row.get("abstract_clean")):
        return "abstract_clean"
    if _is_usable_source_text(row.get("full_text_abstract")):
        return "full_text_abstract"
    if not _text(row.get("summary_zh")) and _is_usable_source_text(
        row.get("full_text_intro")
    ):
        return "full_text_intro"
    return None


def _is_usable_source_text(value: object) -> bool:
    return is_usable_paper_source_text(value)


def _has_identifier(row: dict[str, Any]) -> bool:
    return any(_text(row.get(field)) for field in ("doi", "arxiv_id", "openalex_id"))


def _canonical_source(row: dict[str, Any]) -> str:
    return _text(row.get("canonical_source")) or "unknown"


def _text(value: object) -> str:
    return str(value or "").strip()
