from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.deps import get_pg_conn
from src.data_agents.storage.postgres.pipeline_run import (
    close_pipeline_run,
    open_pipeline_run,
)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

QUALITY_STATUSES = {"ready", "needs_review", "low_confidence", "needs_enrichment"}
DERIVED_QUALITY_STATUSES = QUALITY_STATUSES | {"inactive", "merged"}


class DomainEnum(str, Enum):
    professor = "professor"
    company = "company"
    paper = "paper"
    patent = "patent"


class PaginatedResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


class UpdateRecordRequest(BaseModel):
    core_facts: dict[str, Any] | None = None
    summary_fields: dict[str, Any] | None = None
    quality_status: (
        Literal["ready", "needs_review", "low_confidence", "needs_enrichment"] | None
    ) = None


class RelatedResponse(BaseModel):
    papers: list[dict[str, Any]]
    patents: list[dict[str, Any]]
    companies: list[dict[str, Any]]


class FilterOptionsResponse(BaseModel):
    options: list[str]


LATEST_COMPANY_SNAPSHOT_LATERAL_SQL = """
LEFT JOIN LATERAL (
    SELECT
        cs.snapshot_id,
        cs.company_id,
        cs.import_batch_id,
        cs.source_row_number,
        cs.snapshot_kind,
        cs.project_name,
        cs.industry,
        cs.sub_industry,
        cs.business,
        cs.region,
        cs.description,
        cs.logo_url,
        cs.star_rating,
        cs.status_raw,
        cs.remarks,
        cs.is_high_tech,
        cs.company_name_xlsx,
        cs.country_xlsx,
        cs.established_date,
        cs.years_established,
        cs.website_xlsx,
        cs.legal_representative,
        cs.registered_address,
        cs.registered_capital,
        cs.contact_phone,
        cs.contact_email,
        cs.reported_insured_count,
        cs.reported_shareholder_count,
        cs.reported_investment_count,
        cs.reported_patent_count,
        cs.reported_trademark_count,
        cs.reported_copyright_count,
        cs.reported_recruitment_count,
        cs.reported_news_count,
        cs.reported_institution_count,
        cs.reported_funding_round_count,
        cs.reported_total_funding_raw,
        cs.reported_valuation_raw,
        cs.latest_funding_round,
        cs.latest_funding_time_raw,
        cs.latest_funding_time,
        cs.latest_funding_amount_raw,
        cs.latest_funding_cny_wan,
        cs.latest_funding_ratio,
        cs.latest_investors_raw,
        cs.latest_fa_info,
        cs.team_raw,
        cs.snapshot_created_at,
        cs.raw_row_jsonb
    FROM company_snapshot cs
    WHERE cs.company_id = c.company_id
    ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC
    LIMIT 1
) latest_snapshot ON TRUE
"""

PROFESSOR_SELECT_SQL = """
SELECT
    p.professor_id,
    p.canonical_name,
    p.canonical_name_en,
    p.canonical_name_zh,
    p.aliases,
    p.discipline_family,
    p.identity_status,
    p.merged_into_id,
    p.profile_summary,
    p.h_index,
    p.citation_count,
    p.paper_count,
    p.metrics_computed_at,
    p.metrics_source,
    p.last_refreshed_at,
    p.updated_at,
    p.run_id,
    primary_affiliation.institution AS primary_affiliation_institution,
    primary_affiliation.department AS primary_affiliation_department,
    primary_affiliation.title AS primary_affiliation_title,
    COALESCE(research_topic_counts.research_topic_count, 0) AS research_topic_count,
    sp.url AS primary_profile_url,
    sp.fetched_at AS primary_profile_fetched_at,
    count(*) OVER() AS total_count
FROM professor p
LEFT JOIN LATERAL (
    SELECT pa.institution, pa.department, pa.title
    FROM professor_affiliation pa
    WHERE pa.professor_id = p.professor_id
    ORDER BY
        pa.is_primary DESC,
        pa.is_current DESC,
        pa.start_year DESC NULLS LAST,
        pa.created_at DESC NULLS LAST,
        pa.affiliation_id DESC
    LIMIT 1
) primary_affiliation ON TRUE
LEFT JOIN LATERAL (
    SELECT count(*)::int AS research_topic_count
    FROM professor_fact pf
    WHERE pf.professor_id = p.professor_id
      AND pf.fact_type = 'research_topic'
      AND pf.status = 'active'
) research_topic_counts ON TRUE
LEFT JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id
"""

COMPANY_SELECT_SQL = f"""
SELECT
    c.company_id,
    c.unified_credit_code,
    c.canonical_name,
    c.registered_name,
    c.aliases,
    c.website,
    c.hq_province,
    c.hq_city,
    c.hq_district,
    c.is_shenzhen,
    c.country,
    c.identity_status,
    c.merged_into_id,
    c.last_refreshed_at,
    c.created_at,
    c.updated_at,
    latest_snapshot.project_name,
    latest_snapshot.industry,
    latest_snapshot.sub_industry,
    latest_snapshot.business,
    latest_snapshot.region,
    latest_snapshot.description,
    latest_snapshot.logo_url,
    latest_snapshot.star_rating,
    latest_snapshot.status_raw,
    latest_snapshot.remarks,
    latest_snapshot.is_high_tech,
    latest_snapshot.company_name_xlsx,
    latest_snapshot.established_date,
    latest_snapshot.years_established,
    latest_snapshot.website_xlsx,
    latest_snapshot.registered_address,
    latest_snapshot.registered_capital,
    latest_snapshot.reported_patent_count,
    latest_snapshot.reported_news_count,
    latest_snapshot.reported_funding_round_count,
    latest_snapshot.reported_total_funding_raw,
    latest_snapshot.reported_valuation_raw,
    latest_snapshot.latest_funding_round,
    latest_snapshot.latest_funding_time,
    latest_snapshot.latest_funding_amount_raw,
    latest_snapshot.latest_funding_cny_wan,
    latest_snapshot.latest_investors_raw,
    latest_snapshot.team_raw,
    latest_snapshot.snapshot_created_at,
    count(*) OVER() AS total_count
FROM company c
{LATEST_COMPANY_SNAPSHOT_LATERAL_SQL}
"""

PAPER_SELECT_SQL = """
SELECT
    p.paper_id,
    p.title_clean,
    p.title_raw,
    p.doi,
    p.arxiv_id,
    p.openalex_id,
    p.semantic_scholar_id,
    p.year,
    p.venue,
    p.abstract_clean,
    p.authors_display,
    p.authors_raw,
    p.citation_count,
    p.canonical_source,
    p.first_seen_at,
    p.updated_at,
    p.run_id,
    admin_run.run_scope->>'action' AS admin_action,
    COALESCE(link_counts.linked_professor_count, 0) AS linked_professor_count,
    COALESCE(verified_link_counts.verified_professor_count, 0) AS verified_professor_count,
    count(*) OVER() AS total_count
FROM paper p
LEFT JOIN pipeline_run admin_run
       ON admin_run.run_id = p.run_id
      AND admin_run.triggered_by = 'admin-console'
LEFT JOIN LATERAL (
    SELECT count(*)::int AS linked_professor_count
    FROM professor_paper_link ppl
    WHERE ppl.paper_id = p.paper_id
      AND ppl.link_status IN ('verified', 'candidate')
) link_counts ON TRUE
LEFT JOIN LATERAL (
    SELECT count(*)::int AS verified_professor_count
    FROM professor_paper_link ppl
    WHERE ppl.paper_id = p.paper_id
      AND ppl.link_status = 'verified'
) verified_link_counts ON TRUE
"""

PATENT_SELECT_SQL = """
SELECT
    patent.patent_id,
    patent.patent_number,
    patent.title_clean,
    patent.title_raw,
    patent.title_en,
    patent.applicants_raw,
    patent.applicants_parsed,
    patent.inventors_raw,
    patent.inventors_parsed,
    patent.filing_date,
    patent.publication_date,
    patent.grant_date,
    patent.patent_type,
    patent.status,
    patent.abstract_clean,
    patent.technology_effect,
    patent.ipc_codes,
    patent.first_seen_at,
    patent.updated_at,
    patent.run_id,
    count(*) OVER() AS total_count
FROM patent
"""

DOMAIN_SELECT_SQL: dict[str, str] = {
    "professor": PROFESSOR_SELECT_SQL,
    "company": COMPANY_SELECT_SQL,
    "paper": PAPER_SELECT_SQL,
    "patent": PATENT_SELECT_SQL,
}

DOMAIN_ID_COLUMNS = {
    "professor": "p.professor_id",
    "company": "c.company_id",
    "paper": "p.paper_id",
    "patent": "patent.patent_id",
}

DOMAIN_SORT_COLUMNS = {
    "professor": {
        "id": "p.professor_id",
        "display_name": "p.canonical_name",
        "last_updated": "COALESCE(p.last_refreshed_at, p.updated_at)",
    },
    "company": {
        "id": "c.company_id",
        "display_name": "c.canonical_name",
        "last_updated": "COALESCE(c.last_refreshed_at, c.updated_at)",
    },
    "paper": {
        "id": "p.paper_id",
        "display_name": "p.title_clean",
        "last_updated": "p.updated_at",
        "year": "p.year",
    },
    "patent": {
        "id": "patent.patent_id",
        "display_name": "patent.title_clean",
        "last_updated": "patent.updated_at",
        "filing_date": "patent.filing_date",
    },
}

DOMAIN_DEFAULT_ORDER = {
    "professor": "COALESCE(p.last_refreshed_at, p.updated_at) DESC NULLS LAST, p.canonical_name ASC",
    "company": "COALESCE(c.last_refreshed_at, c.updated_at) DESC NULLS LAST, c.canonical_name ASC",
    "paper": "p.year DESC NULLS LAST, p.citation_count DESC NULLS LAST, p.title_clean ASC",
    "patent": "patent.filing_date DESC NULLS LAST, patent.publication_date DESC NULLS LAST, patent.title_clean ASC",
}

DOMAIN_SUPPORTED_FILTERS = {
    "professor": {"quality_status", "institution", "department", "title", "discipline_family"},
    "company": {"quality_status", "industry", "hq_city", "is_shenzhen"},
    "paper": {"quality_status", "year", "venue"},
    "patent": {"quality_status", "patent_type"},
}

DOMAIN_FILTER_OPTIONS_SQL = {
    ("professor", "institution"): """
        SELECT DISTINCT primary_affiliation.institution AS value
        FROM professor p
        JOIN LATERAL (
            SELECT pa.institution
            FROM professor_affiliation pa
            WHERE pa.professor_id = p.professor_id
              AND pa.institution IS NOT NULL
              AND pa.institution != ''
            ORDER BY pa.is_primary DESC, pa.is_current DESC, pa.start_year DESC NULLS LAST,
                     pa.created_at DESC NULLS LAST, pa.affiliation_id DESC
            LIMIT 1
        ) primary_affiliation ON TRUE
        WHERE p.identity_status = 'resolved'
        ORDER BY value ASC
        LIMIT 1000
    """,
    ("professor", "department"): """
        SELECT DISTINCT primary_affiliation.department AS value
        FROM professor p
        JOIN LATERAL (
            SELECT pa.department
            FROM professor_affiliation pa
            WHERE pa.professor_id = p.professor_id
              AND pa.department IS NOT NULL
              AND pa.department != ''
            ORDER BY pa.is_primary DESC, pa.is_current DESC, pa.start_year DESC NULLS LAST,
                     pa.created_at DESC NULLS LAST, pa.affiliation_id DESC
            LIMIT 1
        ) primary_affiliation ON TRUE
        WHERE p.identity_status = 'resolved'
        ORDER BY value ASC
        LIMIT 1000
    """,
    ("professor", "title"): """
        SELECT DISTINCT primary_affiliation.title AS value
        FROM professor p
        JOIN LATERAL (
            SELECT pa.title
            FROM professor_affiliation pa
            WHERE pa.professor_id = p.professor_id
              AND pa.title IS NOT NULL
              AND pa.title != ''
            ORDER BY pa.is_primary DESC, pa.is_current DESC, pa.start_year DESC NULLS LAST,
                     pa.created_at DESC NULLS LAST, pa.affiliation_id DESC
            LIMIT 1
        ) primary_affiliation ON TRUE
        WHERE p.identity_status = 'resolved'
        ORDER BY value ASC
        LIMIT 1000
    """,
    ("professor", "quality_status"): """
        SELECT DISTINCT
            CASE
                WHEN p.identity_status = 'inactive' THEN 'inactive'
                WHEN p.identity_status IN ('merged', 'merged_into') THEN 'merged'
                WHEN p.identity_status = 'needs_review' THEN 'needs_review'
                ELSE 'ready'
            END AS value
        FROM professor p
        ORDER BY value ASC
        LIMIT 1000
    """,
    ("company", "industry"): """
        SELECT DISTINCT latest_snapshot.industry AS value
        FROM company c
        JOIN LATERAL (
            SELECT cs.industry
            FROM company_snapshot cs
            WHERE cs.company_id = c.company_id
              AND cs.industry IS NOT NULL
              AND cs.industry != ''
            ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC
            LIMIT 1
        ) latest_snapshot ON TRUE
        WHERE c.identity_status != 'inactive'
        ORDER BY value ASC
        LIMIT 1000
    """,
    ("company", "quality_status"): """
        SELECT DISTINCT
            CASE
                WHEN c.identity_status = 'inactive' THEN 'inactive'
                WHEN c.identity_status IN ('merged', 'merged_into') THEN 'merged'
                WHEN c.identity_status = 'needs_review' THEN 'needs_review'
                ELSE 'ready'
            END AS value
        FROM company c
        ORDER BY value ASC
        LIMIT 1000
    """,
    ("paper", "year"): """
        SELECT DISTINCT p.year::text AS value
        FROM paper p
        LEFT JOIN pipeline_run admin_run
               ON admin_run.run_id = p.run_id
              AND admin_run.triggered_by = 'admin-console'
        WHERE p.year IS NOT NULL
          AND COALESCE(admin_run.run_scope->>'action', '') != 'delete'
        ORDER BY value DESC
        LIMIT 1000
    """,
    ("paper", "venue"): """
        SELECT DISTINCT p.venue AS value
        FROM paper p
        LEFT JOIN pipeline_run admin_run
               ON admin_run.run_id = p.run_id
              AND admin_run.triggered_by = 'admin-console'
        WHERE p.venue IS NOT NULL
          AND p.venue != ''
          AND COALESCE(admin_run.run_scope->>'action', '') != 'delete'
        ORDER BY value ASC
        LIMIT 1000
    """,
    ("paper", "quality_status"): """
        SELECT DISTINCT
            CASE
                WHEN admin_run.run_scope->>'action' = 'delete' THEN 'inactive'
                ELSE 'needs_review'
            END AS value
        FROM paper p
        LEFT JOIN pipeline_run admin_run
               ON admin_run.run_id = p.run_id
              AND admin_run.triggered_by = 'admin-console'
        ORDER BY value ASC
        LIMIT 1000
    """,
    ("patent", "patent_type"): """
        SELECT DISTINCT patent.patent_type AS value
        FROM patent
        WHERE patent.patent_type IS NOT NULL
          AND patent.patent_type != ''
          AND COALESCE(patent.status, '') != 'inactive'
        ORDER BY value ASC
        LIMIT 1000
    """,
    ("patent", "quality_status"): """
        SELECT DISTINCT
            CASE
                WHEN patent.status = 'inactive' THEN 'inactive'
                WHEN patent.status IN ('ready', 'needs_review', 'low_confidence', 'needs_enrichment')
                    THEN patent.status
                ELSE 'ready'
            END AS value
        FROM patent
        ORDER BY value ASC
        LIMIT 1000
    """,
}


def _row_dict(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _fetchone(
    conn: Any,
    query: str,
    params: dict[str, Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any] | None:
    return _row_dict(conn.execute(query, params or {}).fetchone())


def _fetchall(
    conn: Any,
    query: str,
    params: dict[str, Any] | tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params or {}).fetchall()]


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _last_updated(row: dict[str, Any], *field_names: str) -> str:
    for field_name in field_names:
        value = row.get(field_name)
        if value is not None:
            return str(_json_value(value))
    return datetime.now(timezone.utc).isoformat()


def _derive_identity_quality(row: dict[str, Any]) -> str:
    identity_status = row.get("identity_status")
    if identity_status == "inactive":
        return "inactive"
    if identity_status in {"merged", "merged_into"}:
        return "merged"
    if identity_status == "needs_review":
        return "needs_review"
    return "ready"


def _derive_paper_quality(row: dict[str, Any]) -> str:
    if row.get("admin_action") == "delete":
        return "inactive"
    return "needs_review"


def _derive_patent_quality(row: dict[str, Any]) -> str:
    status = row.get("status")
    if status == "inactive":
        return "inactive"
    if status in QUALITY_STATUSES:
        return status
    return "ready"


def _quality_to_identity_status(quality_status: str) -> str:
    if quality_status == "ready":
        return "resolved"
    return "needs_review"


def _professor_evidence(row: dict[str, Any]) -> list[dict[str, Any]]:
    url = row.get("primary_profile_url")
    if not url:
        return []
    return [
        {
            "source_type": "official_site",
            "source_url": url,
            "source_file": None,
            "fetched_at": _json_value(
                row.get("primary_profile_fetched_at") or row.get("last_refreshed_at")
            ),
            "snippet": "Primary official profile page.",
            "confidence": None,
        }
    ]


def _row_to_released_object(
    domain: str,
    row: dict[str, Any],
    *,
    include_evidence: bool = False,
) -> dict[str, Any]:
    if domain == "professor":
        core_facts = {
            "name": row["canonical_name"],
            "name_en": row.get("canonical_name_en"),
            "name_zh": row.get("canonical_name_zh"),
            "institution": row.get("primary_affiliation_institution"),
            "department": row.get("primary_affiliation_department"),
            "title": row.get("primary_affiliation_title"),
            "discipline_family": row.get("discipline_family"),
            "h_index": row.get("h_index"),
            "citation_count": row.get("citation_count"),
            "paper_count": row.get("paper_count"),
            "research_topic_count": row.get("research_topic_count"),
            "verified_paper_count": row.get("paper_count"),
            "aliases": row.get("aliases") or [],
        }
        return {
            "id": row["professor_id"],
            "object_type": "professor",
            "display_name": row["canonical_name"],
            "core_facts": _json_value(core_facts),
            "summary_fields": {"profile_summary": row.get("profile_summary")},
            "evidence": _professor_evidence(row) if include_evidence else [],
            "last_updated": _last_updated(row, "last_refreshed_at", "updated_at"),
            "quality_status": _derive_identity_quality(row),
        }

    if domain == "company":
        display_name = row["canonical_name"]
        core_facts = {
            "name": display_name,
            "normalized_name": display_name,
            "registered_name": row.get("registered_name"),
            "unified_credit_code": row.get("unified_credit_code"),
            "industry": row.get("industry"),
            "sub_industry": row.get("sub_industry"),
            "business": row.get("business"),
            "region": row.get("region"),
            "website": row.get("website") or row.get("website_xlsx"),
            "hq_province": row.get("hq_province"),
            "hq_city": row.get("hq_city"),
            "hq_district": row.get("hq_district"),
            "is_shenzhen": row.get("is_shenzhen"),
            "country": row.get("country"),
            "project_name": row.get("project_name"),
            "latest_funding_round": row.get("latest_funding_round"),
            "latest_funding_time": row.get("latest_funding_time"),
            "latest_funding_amount_raw": row.get("latest_funding_amount_raw"),
            "reported_patent_count": row.get("reported_patent_count"),
            "team_raw": row.get("team_raw"),
            "aliases": row.get("aliases") or [],
        }
        return {
            "id": row["company_id"],
            "object_type": "company",
            "display_name": display_name,
            "core_facts": _json_value(core_facts),
            "summary_fields": {
                "profile_summary": row.get("description"),
                "evaluation_summary": row.get("remarks"),
                "technology_route_summary": row.get("business"),
            },
            "evidence": [],
            "last_updated": _last_updated(
                row, "last_refreshed_at", "updated_at", "snapshot_created_at"
            ),
            "quality_status": _derive_identity_quality(row),
        }

    if domain == "paper":
        display_name = row.get("title_clean") or row.get("title_raw") or row["paper_id"]
        core_facts = {
            "title": row.get("title_clean"),
            "title_raw": row.get("title_raw"),
            "authors": row.get("authors_display"),
            "year": row.get("year"),
            "venue": row.get("venue"),
            "doi": row.get("doi"),
            "arxiv_id": row.get("arxiv_id"),
            "openalex_id": row.get("openalex_id"),
            "semantic_scholar_id": row.get("semantic_scholar_id"),
            "citation_count": row.get("citation_count"),
            "canonical_source": row.get("canonical_source"),
            "linked_professor_count": row.get("linked_professor_count"),
            "verified_professor_count": row.get("verified_professor_count"),
        }
        return {
            "id": row["paper_id"],
            "object_type": "paper",
            "display_name": display_name,
            "core_facts": _json_value(core_facts),
            "summary_fields": {
                "summary_text": row.get("abstract_clean"),
                "summary_zh": row.get("abstract_clean"),
            },
            "evidence": [],
            "last_updated": _last_updated(row, "updated_at", "first_seen_at"),
            "quality_status": _derive_paper_quality(row),
        }

    if domain == "patent":
        display_name = row.get("title_clean") or row["patent_id"]
        core_facts = {
            "title": row.get("title_clean"),
            "title_raw": row.get("title_raw"),
            "title_en": row.get("title_en"),
            "patent_number": row.get("patent_number"),
            "patent_type": row.get("patent_type"),
            "applicants": row.get("applicants_raw"),
            "applicants_parsed": row.get("applicants_parsed"),
            "inventors": row.get("inventors_raw"),
            "inventors_parsed": row.get("inventors_parsed"),
            "filing_date": row.get("filing_date"),
            "publication_date": row.get("publication_date"),
            "grant_date": row.get("grant_date"),
            "status": row.get("status"),
            "technology_effect": row.get("technology_effect"),
            "ipc_codes": row.get("ipc_codes") or [],
        }
        return {
            "id": row["patent_id"],
            "object_type": "patent",
            "display_name": display_name,
            "core_facts": _json_value(core_facts),
            "summary_fields": {"summary_text": row.get("abstract_clean")},
            "evidence": [],
            "last_updated": _last_updated(row, "updated_at", "first_seen_at"),
            "quality_status": _derive_patent_quality(row),
        }

    raise HTTPException(status_code=422, detail=f"Unsupported domain: {domain}")


def _parse_filters(filters: str) -> dict[str, Any]:
    if not filters:
        return {}
    try:
        parsed = json.loads(filters)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Invalid filters JSON")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="Invalid filters JSON")
    return parsed


def _add_quality_condition(
    domain: str,
    value: Any,
    conditions: list[str],
    params: dict[str, Any],
) -> None:
    if value not in DERIVED_QUALITY_STATUSES:
        conditions.append("1 = 0")
        return

    if domain == "professor":
        if value == "ready":
            conditions.append("p.identity_status = 'resolved'")
        elif value == "needs_review":
            conditions.append("p.identity_status = 'needs_review'")
        elif value == "inactive":
            conditions.append("p.identity_status = 'inactive'")
        elif value == "merged":
            conditions.append("p.identity_status IN ('merged', 'merged_into')")
        else:
            conditions.append("1 = 0")
    elif domain == "company":
        if value == "ready":
            conditions.append("c.identity_status = 'resolved'")
        elif value == "needs_review":
            conditions.append("c.identity_status = 'needs_review'")
        elif value == "inactive":
            conditions.append("c.identity_status = 'inactive'")
        elif value == "merged":
            conditions.append("c.identity_status IN ('merged', 'merged_into')")
        else:
            conditions.append("1 = 0")
    elif domain == "paper":
        if value == "needs_review":
            conditions.append("COALESCE(admin_run.run_scope->>'action', '') != 'delete'")
        elif value == "inactive":
            conditions.append("admin_run.run_scope->>'action' = 'delete'")
        else:
            conditions.append("1 = 0")
    elif domain == "patent":
        if value == "ready":
            conditions.append(
                "COALESCE(patent.status, '') NOT IN "
                "('inactive', 'needs_review', 'low_confidence', 'needs_enrichment')"
            )
        elif value in QUALITY_STATUSES - {"ready"}:
            params["quality_status"] = value
            conditions.append("patent.status = %(quality_status)s")
        elif value == "inactive":
            conditions.append("patent.status = 'inactive'")
        else:
            conditions.append("1 = 0")


def _add_filter_conditions(
    domain: str,
    parsed_filters: dict[str, Any],
    conditions: list[str],
    params: dict[str, Any],
) -> None:
    supported = DOMAIN_SUPPORTED_FILTERS[domain]
    invalid = sorted(set(parsed_filters) - supported)
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported filters for {domain}: {', '.join(invalid)}. "
                f"Supported: {', '.join(sorted(supported))}"
            ),
        )

    for field, value in parsed_filters.items():
        if value in {None, ""}:
            continue
        param_name = f"filter_{field}"
        if field == "quality_status":
            _add_quality_condition(domain, value, conditions, params)
        elif domain == "professor" and field == "institution":
            params[param_name] = value
            conditions.append(
                "primary_affiliation.institution = %(filter_institution)s"
            )
        elif domain == "professor" and field == "department":
            params[param_name] = value
            conditions.append("primary_affiliation.department = %(filter_department)s")
        elif domain == "professor" and field == "title":
            params[param_name] = value
            conditions.append("primary_affiliation.title = %(filter_title)s")
        elif domain == "professor" and field == "discipline_family":
            params[param_name] = value
            conditions.append("p.discipline_family = %(filter_discipline_family)s")
        elif domain == "company" and field == "industry":
            params[param_name] = value
            conditions.append("latest_snapshot.industry = %(filter_industry)s")
        elif domain == "company" and field == "hq_city":
            params[param_name] = value
            conditions.append("c.hq_city = %(filter_hq_city)s")
        elif domain == "company" and field == "is_shenzhen":
            params[param_name] = value
            conditions.append("c.is_shenzhen = %(filter_is_shenzhen)s")
        elif domain == "paper" and field == "year":
            try:
                params[param_name] = int(value)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="Invalid year filter")
            conditions.append("p.year = %(filter_year)s")
        elif domain == "paper" and field == "venue":
            params[param_name] = value
            conditions.append("p.venue = %(filter_venue)s")
        elif domain == "patent" and field == "patent_type":
            params[param_name] = value
            conditions.append("patent.patent_type = %(filter_patent_type)s")


def _add_query_condition(
    domain: str,
    q: str,
    conditions: list[str],
    params: dict[str, Any],
) -> None:
    if not q:
        return
    params["like_pattern"] = f"%{q}%"
    if domain == "professor":
        conditions.append(
            """
            (
                p.canonical_name ILIKE %(like_pattern)s
                OR p.canonical_name_en ILIKE %(like_pattern)s
                OR p.canonical_name_zh ILIKE %(like_pattern)s
                OR EXISTS (
                    SELECT 1
                    FROM unnest(p.aliases) AS alias
                    WHERE alias ILIKE %(like_pattern)s
                )
            )
            """
        )
    elif domain == "company":
        conditions.append(
            """
            (
                c.canonical_name ILIKE %(like_pattern)s
                OR c.registered_name ILIKE %(like_pattern)s
                OR EXISTS (
                    SELECT 1
                    FROM unnest(c.aliases) AS alias
                    WHERE alias ILIKE %(like_pattern)s
                )
            )
            """
        )
    elif domain == "paper":
        conditions.append(
            """
            (
                p.title_clean ILIKE %(like_pattern)s
                OR p.title_raw ILIKE %(like_pattern)s
                OR COALESCE(p.authors_display, '') ILIKE %(like_pattern)s
            )
            """
        )
    elif domain == "patent":
        conditions.append(
            """
            (
                patent.title_clean ILIKE %(like_pattern)s
                OR patent.title_raw ILIKE %(like_pattern)s
                OR patent.patent_number ILIKE %(like_pattern)s
                OR COALESCE(patent.applicants_raw, '') ILIKE %(like_pattern)s
            )
            """
        )


def _base_conditions(domain: str) -> list[str]:
    if domain == "professor":
        return ["p.identity_status = 'resolved'"]
    if domain == "company":
        return ["c.identity_status != 'inactive'"]
    if domain == "paper":
        return ["COALESCE(admin_run.run_scope->>'action', '') != 'delete'"]
    if domain == "patent":
        return ["COALESCE(patent.status, '') != 'inactive'"]
    return []


def _where_sql(conditions: list[str]) -> str:
    if not conditions:
        return ""
    return "WHERE " + " AND ".join(f"({condition})" for condition in conditions)


def _query_domain_rows(
    conn: Any,
    *,
    domain: str,
    q: str = "",
    parsed_filters: dict[str, Any] | None = None,
    object_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "display_name",
    sort_order: str = "asc",
) -> tuple[list[dict[str, Any]], int]:
    params: dict[str, Any] = {
        "offset": (page - 1) * page_size,
        "page_size": page_size,
    }
    parsed_filters = parsed_filters or {}
    has_quality_filter = "quality_status" in parsed_filters
    conditions = [] if object_id is None and has_quality_filter else _base_conditions(domain)

    if object_id is not None:
        params["object_id"] = object_id
        conditions.append(f"{DOMAIN_ID_COLUMNS[domain]} = %(object_id)s")
    else:
        _add_query_condition(domain, q, conditions, params)
        _add_filter_conditions(domain, parsed_filters, conditions, params)

    sort_columns = DOMAIN_SORT_COLUMNS[domain]
    if sort_by not in sort_columns:
        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid sort_by. Allowed: "
                + ", ".join(sorted(sort_columns))
            ),
        )

    order_sql = f"{sort_columns[sort_by]} {sort_order.upper()} NULLS LAST"
    if sort_by != "display_name":
        order_sql += f", {sort_columns['display_name']} ASC"

    limit_sql = "" if object_id is not None else "OFFSET %(offset)s LIMIT %(page_size)s"
    query = (
        DOMAIN_SELECT_SQL[domain]
        + "\n"
        + _where_sql(conditions)
        + "\nORDER BY "
        + order_sql
        + "\n"
        + limit_sql
    )
    rows = _fetchall(conn, query, params)
    total = int(rows[0]["total_count"]) if rows else 0
    return rows, total


def _get_released_object(
    conn: Any,
    domain: str,
    object_id: str,
    *,
    include_evidence: bool = False,
) -> dict[str, Any] | None:
    rows, _ = _query_domain_rows(
        conn,
        domain=domain,
        object_id=object_id,
        sort_by="id",
        sort_order="asc",
    )
    if not rows:
        return None
    return _row_to_released_object(domain, rows[0], include_evidence=include_evidence)


def _open_admin_run(conn: Any, *, domain: str, object_id: str, action: str) -> Any:
    return open_pipeline_run(
        conn,
        run_kind="backfill_real",
        run_scope={
            "source": "admin-console",
            "domain": domain,
            "object_id": object_id,
            "action": action,
        },
        triggered_by="admin-console",
    )


def _finish_admin_run(
    conn: Any,
    run_id: Any,
    *,
    status: str,
    error_summary: dict[str, Any] | None = None,
) -> None:
    close_pipeline_run(
        conn,
        run_id,
        status=status,
        items_processed=1 if status == "succeeded" else 0,
        items_failed=1 if status != "succeeded" else 0,
        error_summary=error_summary,
    )


def _set_clause(
    clauses: list[str],
    params: dict[str, Any],
    column: str,
    param_name: str,
    value: Any,
) -> None:
    params[param_name] = value
    clauses.append(f"{column} = %({param_name})s")


def _int_or_none(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _apply_professor_update(
    conn: Any,
    object_id: str,
    body: UpdateRecordRequest,
    run_id: Any,
) -> None:
    core = body.core_facts or {}
    summary = body.summary_fields or {}
    params: dict[str, Any] = {"id": object_id, "run_id": run_id}
    clauses: list[str] = []

    field_map = {
        "name": "canonical_name",
        "canonical_name": "canonical_name",
        "name_en": "canonical_name_en",
        "canonical_name_en": "canonical_name_en",
        "name_zh": "canonical_name_zh",
        "canonical_name_zh": "canonical_name_zh",
        "discipline_family": "discipline_family",
        "profile_summary": "profile_summary",
    }
    for field, column in field_map.items():
        if field in core:
            _set_clause(clauses, params, column, f"core_{field}", _str_or_none(core[field]))

    if "profile_summary" in summary:
        _set_clause(
            clauses,
            params,
            "profile_summary",
            "summary_profile_summary",
            _str_or_none(summary["profile_summary"]),
        )
    for metric in ("h_index", "citation_count", "paper_count"):
        if metric in core:
            _set_clause(clauses, params, metric, f"core_{metric}", _int_or_none(core[metric]))
    if body.quality_status is not None:
        _set_clause(
            clauses,
            params,
            "identity_status",
            "identity_status",
            _quality_to_identity_status(body.quality_status),
        )

    clauses.extend(["updated_at = now()", "run_id = %(run_id)s"])
    conn.execute(
        "UPDATE professor SET " + ", ".join(clauses) + " WHERE professor_id = %(id)s",
        params,
    )

    affiliation_clauses: list[str] = []
    affiliation_params: dict[str, Any] = {"id": object_id, "run_id": run_id}
    for field in ("institution", "department", "title"):
        if field in core:
            _set_clause(
                affiliation_clauses,
                affiliation_params,
                field,
                f"aff_{field}",
                _str_or_none(core[field]),
            )
    if affiliation_clauses:
        affiliation_clauses.extend(["updated_at = now()", "run_id = %(run_id)s"])
        conn.execute(
            """
            UPDATE professor_affiliation
               SET """ + ", ".join(affiliation_clauses) + """
             WHERE affiliation_id = (
                SELECT pa.affiliation_id
                FROM professor_affiliation pa
                WHERE pa.professor_id = %(id)s
                ORDER BY
                    pa.is_primary DESC,
                    pa.is_current DESC,
                    pa.start_year DESC NULLS LAST,
                    pa.created_at DESC NULLS LAST,
                    pa.affiliation_id DESC
                LIMIT 1
             )
            """,
            affiliation_params,
        )


def _apply_company_update(
    conn: Any,
    object_id: str,
    body: UpdateRecordRequest,
    run_id: Any,
) -> None:
    del run_id  # company has no run_id column in the canonical schema.
    core = body.core_facts or {}
    summary = body.summary_fields or {}
    params: dict[str, Any] = {"id": object_id}
    clauses: list[str] = []

    field_map = {
        "name": "canonical_name",
        "normalized_name": "canonical_name",
        "canonical_name": "canonical_name",
        "registered_name": "registered_name",
        "website": "website",
        "hq_city": "hq_city",
        "hq_district": "hq_district",
        "is_shenzhen": "is_shenzhen",
    }
    for field, column in field_map.items():
        if field in core:
            _set_clause(clauses, params, column, f"core_{field}", core[field])
    if body.quality_status is not None:
        _set_clause(
            clauses,
            params,
            "identity_status",
            "identity_status",
            _quality_to_identity_status(body.quality_status),
        )

    clauses.append("updated_at = now()")
    conn.execute(
        "UPDATE company SET " + ", ".join(clauses) + " WHERE company_id = %(id)s",
        params,
    )

    snapshot_clauses: list[str] = []
    snapshot_params: dict[str, Any] = {"id": object_id}
    for field, column in {
        "industry": "industry",
        "business": "business",
        "profile_summary": "description",
    }.items():
        if field in core:
            _set_clause(snapshot_clauses, snapshot_params, column, f"snap_{field}", core[field])
    if "profile_summary" in summary:
        _set_clause(
            snapshot_clauses,
            snapshot_params,
            "description",
            "summary_profile_summary",
            summary["profile_summary"],
        )
    if "evaluation_summary" in summary:
        _set_clause(
            snapshot_clauses,
            snapshot_params,
            "remarks",
            "summary_evaluation_summary",
            summary["evaluation_summary"],
        )
    if snapshot_clauses:
        conn.execute(
            """
            UPDATE company_snapshot
               SET """ + ", ".join(snapshot_clauses) + """
             WHERE snapshot_id = (
                SELECT cs.snapshot_id
                FROM company_snapshot cs
                WHERE cs.company_id = %(id)s
                ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC
                LIMIT 1
             )
            """,
            snapshot_params,
        )


def _apply_paper_update(
    conn: Any,
    object_id: str,
    body: UpdateRecordRequest,
    run_id: Any,
) -> None:
    core = body.core_facts or {}
    summary = body.summary_fields or {}
    params: dict[str, Any] = {"id": object_id, "run_id": run_id}
    clauses: list[str] = []

    field_map = {
        "title": "title_clean",
        "title_clean": "title_clean",
        "title_raw": "title_raw",
        "venue": "venue",
        "doi": "doi",
        "arxiv_id": "arxiv_id",
        "openalex_id": "openalex_id",
        "semantic_scholar_id": "semantic_scholar_id",
        "abstract": "abstract_clean",
    }
    for field, column in field_map.items():
        if field in core:
            _set_clause(clauses, params, column, f"core_{field}", _str_or_none(core[field]))
    if "authors" in core:
        authors = core["authors"]
        if isinstance(authors, list):
            authors = ", ".join(str(author) for author in authors)
        _set_clause(clauses, params, "authors_display", "core_authors", _str_or_none(authors))
    if "year" in core:
        _set_clause(clauses, params, "year", "core_year", _int_or_none(core["year"]))
    if "summary_text" in summary:
        _set_clause(
            clauses,
            params,
            "abstract_clean",
            "summary_text",
            _str_or_none(summary["summary_text"]),
        )
    if "summary_zh" in summary:
        _set_clause(
            clauses,
            params,
            "abstract_clean",
            "summary_zh",
            _str_or_none(summary["summary_zh"]),
        )

    clauses.extend(["updated_at = now()", "run_id = %(run_id)s"])
    conn.execute(
        "UPDATE paper SET " + ", ".join(clauses) + " WHERE paper_id = %(id)s",
        params,
    )


def _apply_patent_update(
    conn: Any,
    object_id: str,
    body: UpdateRecordRequest,
    run_id: Any,
) -> None:
    core = body.core_facts or {}
    summary = body.summary_fields or {}
    params: dict[str, Any] = {"id": object_id, "run_id": run_id}
    clauses: list[str] = []

    field_map = {
        "title": "title_clean",
        "title_clean": "title_clean",
        "title_raw": "title_raw",
        "title_en": "title_en",
        "patent_number": "patent_number",
        "patent_type": "patent_type",
        "applicants": "applicants_raw",
        "inventors": "inventors_raw",
        "technology_effect": "technology_effect",
    }
    for field, column in field_map.items():
        if field in core:
            _set_clause(clauses, params, column, f"core_{field}", _str_or_none(core[field]))
    for field in ("filing_date", "publication_date", "grant_date"):
        if field in core:
            _set_clause(clauses, params, field, f"core_{field}", core[field] or None)
    if "ipc_codes" in core:
        ipc_codes = core["ipc_codes"]
        if isinstance(ipc_codes, str):
            ipc_codes = [part.strip() for part in ipc_codes.split(",") if part.strip()]
        _set_clause(clauses, params, "ipc_codes", "core_ipc_codes", ipc_codes)
    if "summary_text" in summary:
        _set_clause(
            clauses,
            params,
            "abstract_clean",
            "summary_text",
            _str_or_none(summary["summary_text"]),
        )
    if body.quality_status is not None:
        _set_clause(clauses, params, "status", "status", body.quality_status)

    clauses.extend(["updated_at = now()", "run_id = %(run_id)s"])
    conn.execute(
        "UPDATE patent SET " + ", ".join(clauses) + " WHERE patent_id = %(id)s",
        params,
    )


def _apply_update(
    conn: Any,
    domain: str,
    object_id: str,
    body: UpdateRecordRequest,
    run_id: Any,
) -> None:
    if domain == "professor":
        _apply_professor_update(conn, object_id, body, run_id)
    elif domain == "company":
        _apply_company_update(conn, object_id, body, run_id)
    elif domain == "paper":
        _apply_paper_update(conn, object_id, body, run_id)
    elif domain == "patent":
        _apply_patent_update(conn, object_id, body, run_id)


def _soft_delete(conn: Any, domain: str, object_id: str, run_id: Any) -> None:
    if domain == "professor":
        conn.execute(
            """
            UPDATE professor
               SET identity_status = 'inactive',
                   updated_at = now(),
                   run_id = %(run_id)s
             WHERE professor_id = %(id)s
            """,
            {"id": object_id, "run_id": run_id},
        )
    elif domain == "company":
        conn.execute(
            """
            UPDATE company
               SET identity_status = 'inactive',
                   updated_at = now()
             WHERE company_id = %(id)s
            """,
            {"id": object_id},
        )
    elif domain == "paper":
        conn.execute(
            """
            UPDATE paper
               SET updated_at = now(),
                   run_id = %(run_id)s
             WHERE paper_id = %(id)s
            """,
            {"id": object_id, "run_id": run_id},
        )
    elif domain == "patent":
        conn.execute(
            """
            UPDATE patent
               SET status = 'inactive',
                   updated_at = now(),
                   run_id = %(run_id)s
             WHERE patent_id = %(id)s
            """,
            {"id": object_id, "run_id": run_id},
        )


@router.get("/{domain}", response_model=PaginatedResponse)
def list_domain(
    domain: DomainEnum,
    q: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = "display_name",
    sort_order: Literal["asc", "desc"] = "asc",
    filters: str = "",
    conn: Any = Depends(get_pg_conn),
) -> PaginatedResponse:
    parsed_filters = _parse_filters(filters)
    rows, total = _query_domain_rows(
        conn,
        domain=domain.value,
        q=q,
        parsed_filters=parsed_filters,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse(
        items=[
            _row_to_released_object(domain.value, row, include_evidence=False)
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{domain}/filters/{field}", response_model=FilterOptionsResponse)
def get_filter_options(
    domain: DomainEnum,
    field: str,
    conn: Any = Depends(get_pg_conn),
) -> FilterOptionsResponse:
    query = DOMAIN_FILTER_OPTIONS_SQL.get((domain.value, field))
    if query is None:
        supported = ", ".join(sorted(DOMAIN_SUPPORTED_FILTERS[domain.value]))
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported filter field for {domain.value}: {field}. Supported: {supported}",
        )
    rows = _fetchall(conn, query)
    return FilterOptionsResponse(
        options=[str(row["value"]) for row in rows if row.get("value") not in {None, ""}]
    )


@router.get("/{domain}/{object_id}")
def get_domain_object(
    domain: DomainEnum,
    object_id: str,
    conn: Any = Depends(get_pg_conn),
) -> dict[str, Any]:
    obj = _get_released_object(conn, domain.value, object_id, include_evidence=True)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return obj


@router.patch("/{domain}/{object_id}")
def update_domain_object(
    domain: DomainEnum,
    object_id: str,
    body: UpdateRecordRequest,
    conn: Any = Depends(get_pg_conn),
) -> dict[str, Any]:
    obj = _get_released_object(conn, domain.value, object_id, include_evidence=True)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")

    if body.core_facts is None and body.summary_fields is None and body.quality_status is None:
        return obj

    run_id = _open_admin_run(
        conn,
        domain=domain.value,
        object_id=object_id,
        action="patch",
    )
    try:
        _apply_update(conn, domain.value, object_id, body, run_id)
        _finish_admin_run(conn, run_id, status="succeeded")
    except Exception as exc:
        logger.exception("Failed to update %s %s", domain.value, object_id)
        _finish_admin_run(
            conn,
            run_id,
            status="failed",
            error_summary={"message": str(exc)},
        )
        raise

    updated = _get_released_object(conn, domain.value, object_id, include_evidence=True)
    if updated is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return updated


@router.delete("/{domain}/{object_id}", status_code=204)
def delete_domain_object(
    domain: DomainEnum,
    object_id: str,
    conn: Any = Depends(get_pg_conn),
) -> None:
    obj = _get_released_object(conn, domain.value, object_id, include_evidence=False)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")

    run_id = _open_admin_run(
        conn,
        domain=domain.value,
        object_id=object_id,
        action="delete",
    )
    try:
        _soft_delete(conn, domain.value, object_id, run_id)
        _finish_admin_run(conn, run_id, status="succeeded")
    except Exception as exc:
        logger.exception("Failed to delete %s %s", domain.value, object_id)
        _finish_admin_run(
            conn,
            run_id,
            status="failed",
            error_summary={"message": str(exc)},
        )
        raise


def _related_papers_for_professor(conn: Any, professor_id: str) -> list[dict[str, Any]]:
    rows = _fetchall(
        conn,
        PAPER_SELECT_SQL
        + """
        JOIN professor_paper_link ppl ON ppl.paper_id = p.paper_id
        WHERE ppl.professor_id = %(id)s
          AND ppl.link_status IN ('verified', 'candidate')
          AND COALESCE(admin_run.run_scope->>'action', '') != 'delete'
        ORDER BY
            ppl.topic_consistency_score DESC NULLS LAST,
            p.citation_count DESC NULLS LAST,
            p.year DESC NULLS LAST,
            p.title_clean ASC
        LIMIT 20
        """,
        {"id": professor_id},
    )
    return [_row_to_released_object("paper", row) for row in rows]


def _related_patents_for_professor(conn: Any, professor_id: str) -> list[dict[str, Any]]:
    rows = _fetchall(
        conn,
        PATENT_SELECT_SQL
        + """
        JOIN professor_patent_link ppl ON ppl.patent_id = patent.patent_id
        WHERE ppl.professor_id = %(id)s
          AND ppl.link_status IN ('verified', 'candidate')
          AND COALESCE(patent.status, '') != 'inactive'
        ORDER BY patent.filing_date DESC NULLS LAST, patent.title_clean ASC
        LIMIT 20
        """,
        {"id": professor_id},
    )
    return [_row_to_released_object("patent", row) for row in rows]


def _related_companies_for_professor(conn: Any, professor_id: str) -> list[dict[str, Any]]:
    rows = _fetchall(
        conn,
        COMPANY_SELECT_SQL
        + """
        JOIN professor_company_role pcr ON pcr.company_id = c.company_id
        WHERE pcr.professor_id = %(id)s
          AND pcr.link_status IN ('verified', 'candidate')
          AND c.identity_status != 'inactive'
        ORDER BY c.canonical_name ASC
        LIMIT 20
        """,
        {"id": professor_id},
    )
    return [_row_to_released_object("company", row) for row in rows]


def _related_patents_for_company(conn: Any, company_id: str) -> list[dict[str, Any]]:
    rows = _fetchall(
        conn,
        PATENT_SELECT_SQL
        + """
        JOIN company_patent_link cpl ON cpl.patent_id = patent.patent_id
        WHERE cpl.company_id = %(id)s
          AND cpl.link_status IN ('verified', 'candidate')
          AND COALESCE(patent.status, '') != 'inactive'
        ORDER BY patent.filing_date DESC NULLS LAST, patent.title_clean ASC
        LIMIT 20
        """,
        {"id": company_id},
    )
    return [_row_to_released_object("patent", row) for row in rows]


def _related_professors_for_paper(conn: Any, paper_id: str) -> list[dict[str, Any]]:
    rows = _fetchall(
        conn,
        PROFESSOR_SELECT_SQL
        + """
        JOIN professor_paper_link ppl ON ppl.professor_id = p.professor_id
        WHERE ppl.paper_id = %(id)s
          AND ppl.link_status IN ('verified', 'candidate')
          AND p.identity_status = 'resolved'
        ORDER BY
            CASE ppl.link_status WHEN 'verified' THEN 0 ELSE 1 END,
            ppl.topic_consistency_score DESC NULLS LAST,
            p.canonical_name ASC
        LIMIT 20
        """,
        {"id": paper_id},
    )
    return [_row_to_released_object("professor", row) for row in rows]


def _related_companies_for_patent(conn: Any, patent_id: str) -> list[dict[str, Any]]:
    rows = _fetchall(
        conn,
        COMPANY_SELECT_SQL
        + """
        JOIN company_patent_link cpl ON cpl.company_id = c.company_id
        WHERE cpl.patent_id = %(id)s
          AND cpl.link_status IN ('verified', 'candidate')
          AND c.identity_status != 'inactive'
        ORDER BY c.canonical_name ASC
        LIMIT 20
        """,
        {"id": patent_id},
    )
    return [_row_to_released_object("company", row) for row in rows]


def _related_professors_for_patent(conn: Any, patent_id: str) -> list[dict[str, Any]]:
    rows = _fetchall(
        conn,
        PROFESSOR_SELECT_SQL
        + """
        JOIN professor_patent_link ppl ON ppl.professor_id = p.professor_id
        WHERE ppl.patent_id = %(id)s
          AND ppl.link_status IN ('verified', 'candidate')
          AND p.identity_status = 'resolved'
        ORDER BY p.canonical_name ASC
        LIMIT 20
        """,
        {"id": patent_id},
    )
    return [_row_to_released_object("professor", row) for row in rows]


@router.get("/{domain}/{object_id}/related", response_model=RelatedResponse)
def get_related_objects(
    domain: DomainEnum,
    object_id: str,
    conn: Any = Depends(get_pg_conn),
) -> RelatedResponse:
    obj = _get_released_object(conn, domain.value, object_id, include_evidence=False)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")

    papers: list[dict[str, Any]] = []
    patents: list[dict[str, Any]] = []
    companies: list[dict[str, Any]] = []

    if domain.value == "professor":
        papers = _related_papers_for_professor(conn, object_id)
        patents = _related_patents_for_professor(conn, object_id)
        companies = _related_companies_for_professor(conn, object_id)
    elif domain.value == "company":
        patents = _related_patents_for_company(conn, object_id)
    elif domain.value == "paper":
        # RelatedResponse has no "professors" bucket; preserve the existing
        # frontend contract by returning professor objects in the papers list.
        papers = _related_professors_for_paper(conn, object_id)
    elif domain.value == "patent":
        companies = _related_companies_for_patent(conn, object_id)
        papers = _related_professors_for_patent(conn, object_id)

    return RelatedResponse(papers=papers, patents=patents, companies=companies)
