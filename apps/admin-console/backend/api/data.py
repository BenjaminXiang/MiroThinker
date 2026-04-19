from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.deps import get_pg_conn
from src.data_agents.canonical.company import (
    Company,
    CompanySignalEvent,
    CompanySnapshot,
    CompanyTeamMember,
)
from src.data_agents.canonical.paper import Paper, Patent
from src.data_agents.canonical.professor import (
    Professor as CanonicalProfessor,
    ProfessorAffiliation as CanonicalProfessorAffiliation,
)

router = APIRouter(prefix="/api/data")

# Resolve the "current" company snapshot inline in the list query so one page of
# results still executes as a single SQL statement instead of per-row lookups.
LATEST_SNAPSHOT_LATERAL_SQL = """
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

COMPANY_LIST_SELECT_SQL = f"""
SELECT
    c.company_id,
    c.canonical_name,
    latest_snapshot.industry,
    latest_snapshot.latest_funding_round,
    c.last_refreshed_at,
    c.is_shenzhen,
    c.aliases,
    count(*) OVER() AS total_count
FROM company c
{LATEST_SNAPSHOT_LATERAL_SQL}
"""

COMPANY_ORDER_BY_SQL = """
ORDER BY
    c.last_refreshed_at DESC NULLS LAST,
    c.canonical_name ASC
"""

LATEST_COMPANY_SNAPSHOT_SQL = """
SELECT
    cs.*
FROM company_snapshot cs
WHERE cs.company_id = %s
ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC
LIMIT 1
"""

ALL_COMPANY_SNAPSHOTS_SQL = """
SELECT
    cs.snapshot_id,
    cs.import_batch_id,
    cs.source_row_number,
    cs.snapshot_kind,
    cs.snapshot_created_at
FROM company_snapshot cs
WHERE cs.company_id = %s
ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC
"""

TEAM_MEMBERS_SQL = """
SELECT
    tm.*
FROM company_team_member tm
JOIN company_snapshot cs ON cs.snapshot_id = tm.snapshot_id
WHERE tm.company_id = %s
ORDER BY
    cs.snapshot_created_at DESC NULLS LAST,
    tm.member_order ASC,
    tm.member_id ASC
"""

FUNDING_EVENTS_SQL = """
SELECT
    cse.*
FROM company_signal_event cse
WHERE cse.company_id = %s
  AND cse.event_type = 'funding'
ORDER BY cse.event_date DESC, cse.created_at DESC NULLS LAST, cse.event_id DESC
"""

INDUSTRY_FACETS_SQL = """
SELECT
    latest_snapshot.industry,
    count(*)::int AS count
FROM company c
LEFT JOIN LATERAL (
    SELECT cs.industry
    FROM company_snapshot cs
    WHERE cs.company_id = c.company_id
      AND cs.industry IS NOT NULL
      AND cs.industry != ''
    ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC
    LIMIT 1
) latest_snapshot ON TRUE
WHERE latest_snapshot.industry IS NOT NULL
GROUP BY latest_snapshot.industry
ORDER BY count DESC, latest_snapshot.industry ASC
LIMIT 50
"""


class CompanyListItem(BaseModel):
    company_id: str
    canonical_name: str
    industry: str | None = None
    latest_funding_round: str | None = None
    last_refreshed_at: datetime | None = None
    is_shenzhen: bool
    aliases: list[str] = Field(default_factory=list)


class CompanyListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CompanyListItem]


class CompanySnapshotSummary(BaseModel):
    snapshot_id: UUID
    import_batch_id: UUID
    source_row_number: int | None = None
    snapshot_kind: str
    snapshot_created_at: datetime | None = None


class CompanyDetailResponse(BaseModel):
    company: Company
    latest_snapshot: CompanySnapshot | None = None
    all_snapshots: list[CompanySnapshotSummary]
    team_members: list[CompanyTeamMember]
    funding_events: list[CompanySignalEvent]


class IndustryFacet(BaseModel):
    industry: str
    count: int


def _row_to_model(row: Any | None, model_cls: type[BaseModel]) -> BaseModel | None:
    if row is None:
        return None
    return model_cls.model_validate(dict(row))


def _rows_to_models(rows: list[Any], model_cls: type[BaseModel]) -> list[BaseModel]:
    return [model_cls.model_validate(dict(row)) for row in rows]


def _list_companies(
    conn: Any,
    *,
    q: str | None,
    industry: str | None,
    hq_city: str | None,
    is_shenzhen: bool | None,
    page: int,
    page_size: int,
) -> CompanyListResponse:
    conditions: list[str] = []
    params: dict[str, Any] = {
        "offset": (page - 1) * page_size,
        "page_size": page_size,
    }

    if q:
        params["like_pattern"] = f"%{q}%"
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

    if industry:
        params["industry"] = industry
        conditions.append("latest_snapshot.industry = %(industry)s")

    if hq_city:
        params["hq_city"] = hq_city
        conditions.append("c.hq_city = %(hq_city)s")

    if is_shenzhen is not None:
        params["is_shenzhen"] = is_shenzhen
        conditions.append("c.is_shenzhen = %(is_shenzhen)s")

    where_sql = ""
    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    query = (
        COMPANY_LIST_SELECT_SQL
        + where_sql
        + "\n"
        + COMPANY_ORDER_BY_SQL
        + "\nOFFSET %(offset)s LIMIT %(page_size)s"
    )
    rows = conn.execute(query, params).fetchall()

    total = int(rows[0]["total_count"]) if rows else 0
    items = [
        CompanyListItem(
            company_id=row["company_id"],
            canonical_name=row["canonical_name"],
            industry=row["industry"],
            latest_funding_round=row["latest_funding_round"],
            last_refreshed_at=row["last_refreshed_at"],
            is_shenzhen=row["is_shenzhen"],
            aliases=row["aliases"] or [],
        )
        for row in rows
    ]
    return CompanyListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


@router.get("/companies", response_model=CompanyListResponse)
def list_companies(
    q: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    hq_city: str | None = Query(default=None),
    is_shenzhen: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    conn: Any = Depends(get_pg_conn),
) -> CompanyListResponse:
    return _list_companies(
        conn,
        q=q,
        industry=industry,
        hq_city=hq_city,
        is_shenzhen=is_shenzhen,
        page=page,
        page_size=page_size,
    )


@router.get("/companies/{company_id}", response_model=CompanyDetailResponse)
def get_company_detail(
    company_id: str,
    conn: Any = Depends(get_pg_conn),
) -> CompanyDetailResponse:
    company_row = conn.execute(
        """
        SELECT *
        FROM company
        WHERE company_id = %s
        """,
        (company_id,),
    ).fetchone()
    company = _row_to_model(company_row, Company)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    latest_snapshot = _row_to_model(
        conn.execute(LATEST_COMPANY_SNAPSHOT_SQL, (company_id,)).fetchone(),
        CompanySnapshot,
    )
    all_snapshots = _rows_to_models(
        conn.execute(ALL_COMPANY_SNAPSHOTS_SQL, (company_id,)).fetchall(),
        CompanySnapshotSummary,
    )
    team_members = _rows_to_models(
        conn.execute(TEAM_MEMBERS_SQL, (company_id,)).fetchall(),
        CompanyTeamMember,
    )
    funding_events = _rows_to_models(
        conn.execute(FUNDING_EVENTS_SQL, (company_id,)).fetchall(),
        CompanySignalEvent,
    )

    return CompanyDetailResponse(
        company=company,
        latest_snapshot=latest_snapshot,
        all_snapshots=all_snapshots,
        team_members=team_members,
        funding_events=funding_events,
    )


@router.get("/facets/industries", response_model=list[IndustryFacet])
def list_industry_facets(
    conn: Any = Depends(get_pg_conn),
) -> list[IndustryFacet]:
    rows = conn.execute(INDUSTRY_FACETS_SQL).fetchall()
    return [IndustryFacet.model_validate(dict(row)) for row in rows]


PROFESSOR_FACT_TYPES = (
    "research_topic",
    "education",
    "work_experience",
    "award",
    "academic_position",
    "contact",
    "homepage",
    "external_profile",
    "publication_count_reported",
)

PROFESSOR_LIST_SELECT_SQL = """
SELECT
    p.professor_id,
    p.canonical_name,
    p.canonical_name_en,
    primary_affiliation.institution,
    primary_affiliation.title,
    p.discipline_family,
    p.aliases,
    COALESCE(research_topic_counts.research_topic_count, 0) AS research_topic_count,
    COALESCE(verified_link_counts.verified_paper_count, 0) AS verified_paper_count,
    p.last_refreshed_at,
    count(*) OVER() AS total_count
FROM professor p
LEFT JOIN LATERAL (
    SELECT pa.institution, pa.title
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
LEFT JOIN LATERAL (
    SELECT count(*)::int AS verified_paper_count
    FROM professor_paper_link ppl
    WHERE ppl.professor_id = p.professor_id
      AND ppl.link_status = 'verified'
) verified_link_counts ON TRUE
"""

PROFESSOR_ORDER_BY_SQL = """
ORDER BY
    p.last_refreshed_at DESC NULLS LAST,
    p.canonical_name ASC
"""

PROFESSOR_DETAIL_SQL = """
SELECT
    p.*,
    sp.url AS primary_profile_url,
    NULL::text AS research_directions_source,
    COALESCE(rejected_link_counts.rejected_papers_total, 0) AS rejected_papers_total
FROM professor p
LEFT JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id
LEFT JOIN LATERAL (
    SELECT count(*)::int AS rejected_papers_total
    FROM professor_paper_link ppl
    WHERE ppl.professor_id = p.professor_id
      AND ppl.link_status = 'rejected'
) rejected_link_counts ON TRUE
WHERE p.professor_id = %s
"""

PROFESSOR_AFFILIATIONS_SQL = """
SELECT
    pa.*,
    sp.url AS source_page_url,
    sp.page_role AS source_page_role
FROM professor_affiliation pa
LEFT JOIN source_page sp ON sp.page_id = pa.source_page_id
WHERE pa.professor_id = %s
ORDER BY
    pa.is_primary DESC,
    pa.is_current DESC,
    pa.start_year DESC NULLS LAST,
    pa.created_at DESC NULLS LAST,
    pa.affiliation_id ASC
"""

PROFESSOR_FACTS_SQL = """
SELECT
    pf.fact_type,
    pf.value_raw,
    pf.value_normalized,
    pf.value_code,
    pf.source_page_id,
    pf.confidence,
    pf.evidence_span,
    sp.url AS source_page_url,
    sp.page_role AS source_page_role,
    sp.fetched_at AS source_page_fetched_at
FROM professor_fact pf
LEFT JOIN source_page sp ON sp.page_id = pf.source_page_id
WHERE pf.professor_id = %s
  AND pf.status = 'active'
ORDER BY
    pf.fact_type ASC,
    pf.confidence DESC NULLS LAST,
    pf.fact_id ASC
"""

PROFESSOR_TOP_PAPERS_SQL = """
SELECT
    p.paper_id,
    p.title_clean,
    p.year,
    p.venue,
    p.citation_count,
    p.authors_display,
    p.canonical_source,
    ppl.topic_consistency_score,
    ppl.link_status,
    ppl.match_reason,
    ppl.rejected_reason,
    ppl.verified_by,
    ppl.verified_at,
    ppl.evidence_api_source,
    ep.url AS evidence_page_url,
    ppl.is_officially_listed
FROM professor_paper_link ppl
JOIN paper p ON p.paper_id = ppl.paper_id
LEFT JOIN source_page ep ON ep.page_id = ppl.evidence_page_id
WHERE ppl.professor_id = %s
  AND ppl.link_status = %s
ORDER BY
    ppl.topic_consistency_score DESC NULLS LAST,
    p.citation_count DESC NULLS LAST,
    p.year DESC NULLS LAST,
    p.title_clean ASC
LIMIT 20
"""

PROFESSOR_REJECTED_PAPERS_SQL = """
SELECT
    p.paper_id,
    p.title_clean,
    p.year,
    p.venue,
    p.citation_count,
    p.authors_display,
    p.canonical_source,
    ppl.topic_consistency_score,
    ppl.link_status,
    ppl.match_reason,
    ppl.rejected_reason,
    ppl.verified_by,
    ppl.verified_at,
    ppl.evidence_api_source,
    ep.url AS evidence_page_url,
    ppl.is_officially_listed
FROM professor_paper_link ppl
JOIN paper p ON p.paper_id = ppl.paper_id
LEFT JOIN source_page ep ON ep.page_id = ppl.evidence_page_id
WHERE ppl.professor_id = %s
  AND ppl.link_status = 'rejected'
ORDER BY
    ppl.rejected_at DESC NULLS LAST,
    p.citation_count DESC NULLS LAST,
    p.year DESC NULLS LAST,
    p.title_clean ASC
LIMIT 50
"""

PROFESSOR_SOURCE_PAGES_USED_SQL = """
SELECT
    count(DISTINCT source_page_id)::int AS source_pages_used
FROM (
    SELECT pa.source_page_id
    FROM professor_affiliation pa
    WHERE pa.professor_id = %s
    UNION
    SELECT pf.source_page_id
    FROM professor_fact pf
    WHERE pf.professor_id = %s
      AND pf.status = 'active'
) source_pages
"""

PROFESSOR_INSTITUTION_FACETS_SQL = """
SELECT
    primary_affiliation.institution,
    count(*)::int AS count
FROM professor p
JOIN LATERAL (
    SELECT pa.institution
    FROM professor_affiliation pa
    WHERE pa.professor_id = p.professor_id
      AND pa.institution IS NOT NULL
      AND pa.institution != ''
    ORDER BY
        pa.is_primary DESC,
        pa.is_current DESC,
        pa.start_year DESC NULLS LAST,
        pa.created_at DESC NULLS LAST,
        pa.affiliation_id DESC
    LIMIT 1
) primary_affiliation ON TRUE
WHERE p.identity_status = 'resolved'
GROUP BY primary_affiliation.institution
ORDER BY count DESC, primary_affiliation.institution ASC
LIMIT 50
"""

RESEARCH_TOPIC_FACETS_SQL = """
SELECT
    pf.value_raw AS value,
    count(*)::int AS count
FROM professor_fact pf
JOIN professor p ON p.professor_id = pf.professor_id
WHERE pf.fact_type = 'research_topic'
  AND pf.status = 'active'
  AND pf.value_raw IS NOT NULL
  AND pf.value_raw != ''
  AND p.identity_status = 'resolved'
GROUP BY pf.value_raw
ORDER BY count DESC, pf.value_raw ASC
LIMIT 50
"""

PAPER_LIST_SELECT_SQL = """
SELECT
    p.paper_id,
    p.title_clean,
    p.year,
    p.venue,
    p.citation_count,
    p.authors_display,
    p.canonical_source,
    COALESCE(link_counts.linked_professor_count, 0) AS linked_professor_count,
    COALESCE(verified_link_counts.verified_professor_count, 0) AS verified_professor_count,
    count(*) OVER() AS total_count
FROM paper p
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

PAPER_ORDER_BY_SQL = """
ORDER BY
    p.year DESC NULLS LAST,
    p.citation_count DESC NULLS LAST,
    p.title_clean ASC
"""

PAPER_LINKED_PROFESSORS_SQL = """
SELECT
    ppl.link_status,
    prof.professor_id,
    prof.canonical_name,
    primary_affiliation.institution,
    ppl.topic_consistency_score,
    ppl.match_reason,
    ppl.rejected_reason,
    ppl.verified_by,
    ppl.verified_at,
    ppl.evidence_api_source,
    ep.url AS evidence_page_url,
    ppl.is_officially_listed
FROM professor_paper_link ppl
JOIN professor prof ON prof.professor_id = ppl.professor_id
LEFT JOIN LATERAL (
    SELECT pa.institution
    FROM professor_affiliation pa
    WHERE pa.professor_id = prof.professor_id
    ORDER BY
        pa.is_primary DESC,
        pa.is_current DESC,
        pa.start_year DESC NULLS LAST,
        pa.created_at DESC NULLS LAST,
        pa.affiliation_id DESC
    LIMIT 1
) primary_affiliation ON TRUE
LEFT JOIN source_page ep ON ep.page_id = ppl.evidence_page_id
WHERE ppl.paper_id = %s
  AND ppl.link_status IN ('verified', 'candidate', 'rejected')
ORDER BY
    CASE ppl.link_status
        WHEN 'verified' THEN 0
        WHEN 'candidate' THEN 1
        WHEN 'rejected' THEN 2
        ELSE 3
    END,
    CASE WHEN ppl.link_status = 'rejected' THEN ppl.rejected_at END DESC NULLS LAST,
    CASE
        WHEN ppl.link_status IN ('verified', 'candidate')
        THEN ppl.topic_consistency_score
        ELSE NULL
    END DESC NULLS LAST,
    prof.canonical_name ASC
"""

PATENT_LIST_SELECT_SQL = """
SELECT
    patent.patent_id,
    patent.patent_number,
    patent.title_clean,
    patent.filing_date,
    patent.publication_date,
    patent.patent_type,
    patent.applicants_raw,
    count(*) OVER() AS total_count
FROM patent
"""

PATENT_ORDER_BY_SQL = """
ORDER BY
    patent.filing_date DESC NULLS LAST,
    patent.publication_date DESC NULLS LAST,
    patent.title_clean ASC
"""

PATENT_LINKED_COMPANIES_SQL = """
SELECT
    cpl.company_id,
    c.canonical_name,
    cpl.link_role,
    cpl.link_status
FROM company_patent_link cpl
JOIN company c ON c.company_id = cpl.company_id
WHERE cpl.patent_id = %s
ORDER BY c.canonical_name ASC, cpl.link_role ASC
"""

PATENT_LINKED_PROFESSORS_SQL = """
SELECT
    ppl.professor_id,
    p.canonical_name,
    primary_affiliation.institution,
    ppl.link_role,
    ppl.link_status
FROM professor_patent_link ppl
JOIN professor p ON p.professor_id = ppl.professor_id
LEFT JOIN LATERAL (
    SELECT pa.institution
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
WHERE ppl.patent_id = %s
ORDER BY p.canonical_name ASC, ppl.link_role ASC
"""


class ProfessorListItem(BaseModel):
    professor_id: str
    canonical_name: str
    canonical_name_en: str | None = None
    institution: str | None = None
    title: str | None = None
    discipline_family: str
    aliases: list[str] = Field(default_factory=list)
    research_topic_count: int
    verified_paper_count: int
    last_refreshed_at: datetime | None = None


class ProfessorListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ProfessorListItem]


class ProfessorFactValue(BaseModel):
    value_raw: str
    value_normalized: str | None = None
    value_code: str | None = None
    source_page_id: UUID | None = None
    confidence: float | None = None
    evidence_span: str | None = None
    source_page_url: str | None = None
    source_page_role: str | None = None
    source_page_fetched_at: datetime | None = None


class ProfessorAffiliationWithProvenance(CanonicalProfessorAffiliation):
    source_page_url: str | None = None
    source_page_role: str | None = None


class PaperSummary(BaseModel):
    paper_id: str
    title_clean: str
    year: int | None = None
    venue: str | None = None
    citation_count: int | None = None
    authors_display: str | None = None
    canonical_source: str | None = None
    topic_consistency_score: float | None = None


class PaperSummaryWithProvenance(PaperSummary):
    link_status: str
    match_reason: str | None = None
    rejected_reason: str | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    evidence_api_source: str | None = None
    evidence_page_url: str | None = None
    is_officially_listed: bool = False


class ProfessorWithProvenance(CanonicalProfessor):
    primary_profile_url: str | None = None
    research_directions_source: str | None = None


class ProfessorDetailResponse(BaseModel):
    professor: ProfessorWithProvenance
    affiliations: list[ProfessorAffiliationWithProvenance]
    facts_by_type: dict[str, list[ProfessorFactValue]]
    verified_papers: list[PaperSummaryWithProvenance]
    candidate_papers: list[PaperSummaryWithProvenance]
    rejected_papers: list[PaperSummaryWithProvenance]
    rejected_papers_total: int
    source_pages_used: int


class ProfessorInstitutionFacet(BaseModel):
    institution: str
    count: int


class ResearchTopicFacet(BaseModel):
    value: str
    count: int


class PaperListItem(BaseModel):
    paper_id: str
    title_clean: str
    year: int | None = None
    venue: str | None = None
    citation_count: int | None = None
    authors_display: str | None = None
    canonical_source: str
    linked_professor_count: int


class PaperListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[PaperListItem]


class LinkedProfessorSummary(BaseModel):
    professor_id: str
    canonical_name: str
    institution: str | None = None
    link_status: str
    topic_consistency_score: float | None = None
    match_reason: str | None = None
    rejected_reason: str | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    evidence_api_source: str | None = None
    evidence_page_url: str | None = None
    is_officially_listed: bool = False


class LinkedProfessorsByStatus(BaseModel):
    verified: list[LinkedProfessorSummary] = Field(default_factory=list)
    candidate: list[LinkedProfessorSummary] = Field(default_factory=list)
    rejected: list[LinkedProfessorSummary] = Field(default_factory=list)


class PaperDetailResponse(BaseModel):
    paper: Paper
    linked_professors: LinkedProfessorsByStatus


class PatentListItem(BaseModel):
    patent_id: str
    patent_number: str
    title_clean: str
    filing_date: date | None = None
    publication_date: date | None = None
    patent_type: str | None = None
    applicants_raw: str | None = None


class PatentListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[PatentListItem]


class PatentLinkedCompany(BaseModel):
    company_id: str
    canonical_name: str
    link_role: str
    link_status: str


class PatentLinkedProfessor(BaseModel):
    professor_id: str
    canonical_name: str
    institution: str | None = None
    link_role: str
    link_status: str


class PatentDetailResponse(BaseModel):
    patent: Patent
    linked_companies: list[PatentLinkedCompany]
    linked_professors: list[PatentLinkedProfessor]


def _list_professors(
    conn: Any,
    *,
    q: str | None,
    institution: str | None,
    discipline_family: str | None,
    has_verified_papers: bool | None,
    page: int,
    page_size: int,
) -> ProfessorListResponse:
    conditions: list[str] = ["p.identity_status = 'resolved'"]
    params: dict[str, Any] = {
        "offset": (page - 1) * page_size,
        "page_size": page_size,
    }

    if q:
        params["like_pattern"] = f"%{q}%"
        conditions.append(
            """
            (
                p.canonical_name ILIKE %(like_pattern)s
                OR p.canonical_name_en ILIKE %(like_pattern)s
                OR EXISTS (
                    SELECT 1
                    FROM unnest(p.aliases) AS alias
                    WHERE alias ILIKE %(like_pattern)s
                )
            )
            """
        )

    if institution:
        params["institution"] = institution
        conditions.append("primary_affiliation.institution = %(institution)s")

    if discipline_family:
        params["discipline_family"] = discipline_family
        conditions.append("p.discipline_family = %(discipline_family)s")

    if has_verified_papers is not None:
        if has_verified_papers:
            conditions.append("COALESCE(verified_link_counts.verified_paper_count, 0) > 0")
        else:
            conditions.append("COALESCE(verified_link_counts.verified_paper_count, 0) = 0")

    where_sql = ""
    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    query = (
        PROFESSOR_LIST_SELECT_SQL
        + where_sql
        + "\n"
        + PROFESSOR_ORDER_BY_SQL
        + "\nOFFSET %(offset)s LIMIT %(page_size)s"
    )
    rows = conn.execute(query, params).fetchall()

    total = int(rows[0]["total_count"]) if rows else 0
    items = [
        ProfessorListItem(
            professor_id=row["professor_id"],
            canonical_name=row["canonical_name"],
            canonical_name_en=row["canonical_name_en"],
            institution=row["institution"],
            title=row["title"],
            discipline_family=row["discipline_family"],
            aliases=row["aliases"] or [],
            research_topic_count=row["research_topic_count"],
            verified_paper_count=row["verified_paper_count"],
            last_refreshed_at=row["last_refreshed_at"],
        )
        for row in rows
    ]
    return ProfessorListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


def _paper_summary_rows(
    conn: Any,
    *,
    professor_id: str,
    link_status: str,
) -> list[PaperSummaryWithProvenance]:
    if link_status == "rejected":
        rows = conn.execute(PROFESSOR_REJECTED_PAPERS_SQL, (professor_id,)).fetchall()
    else:
        rows = conn.execute(PROFESSOR_TOP_PAPERS_SQL, (professor_id, link_status)).fetchall()
    return _rows_to_models(
        rows,
        PaperSummaryWithProvenance,
    )


def _list_papers(
    conn: Any,
    *,
    q: str | None,
    year_min: int | None,
    year_max: int | None,
    has_verified_professor: bool | None,
    min_citations: int | None,
    page: int,
    page_size: int,
) -> PaperListResponse:
    conditions: list[str] = []
    params: dict[str, Any] = {
        "offset": (page - 1) * page_size,
        "page_size": page_size,
    }

    if q:
        params["like_pattern"] = f"%{q}%"
        conditions.append(
            """
            (
                p.title_clean ILIKE %(like_pattern)s
                OR COALESCE(p.authors_display, '') ILIKE %(like_pattern)s
            )
            """
        )

    if year_min is not None:
        params["year_min"] = year_min
        conditions.append("p.year >= %(year_min)s")

    if year_max is not None:
        params["year_max"] = year_max
        conditions.append("p.year <= %(year_max)s")

    if has_verified_professor is not None:
        if has_verified_professor:
            conditions.append(
                "COALESCE(verified_link_counts.verified_professor_count, 0) > 0"
            )
        else:
            conditions.append(
                "COALESCE(verified_link_counts.verified_professor_count, 0) = 0"
            )

    if min_citations is not None:
        params["min_citations"] = min_citations
        conditions.append("COALESCE(p.citation_count, 0) >= %(min_citations)s")

    where_sql = ""
    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    query = (
        PAPER_LIST_SELECT_SQL
        + where_sql
        + "\n"
        + PAPER_ORDER_BY_SQL
        + "\nOFFSET %(offset)s LIMIT %(page_size)s"
    )
    rows = conn.execute(query, params).fetchall()

    total = int(rows[0]["total_count"]) if rows else 0
    items = [
        PaperListItem(
            paper_id=row["paper_id"],
            title_clean=row["title_clean"],
            year=row["year"],
            venue=row["venue"],
            citation_count=row["citation_count"],
            authors_display=row["authors_display"],
            canonical_source=row["canonical_source"],
            linked_professor_count=row["linked_professor_count"],
        )
        for row in rows
    ]
    return PaperListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


def _list_patents(
    conn: Any,
    *,
    q: str | None,
    year_min: int | None,
    year_max: int | None,
    applicant: str | None,
    page: int,
    page_size: int,
) -> PatentListResponse:
    conditions: list[str] = []
    params: dict[str, Any] = {
        "offset": (page - 1) * page_size,
        "page_size": page_size,
    }

    if q:
        params["like_pattern"] = f"%{q}%"
        conditions.append(
            """
            (
                patent.title_clean ILIKE %(like_pattern)s
                OR patent.patent_number ILIKE %(like_pattern)s
                OR COALESCE(patent.applicants_raw, '') ILIKE %(like_pattern)s
            )
            """
        )

    if year_min is not None:
        params["year_min"] = year_min
        conditions.append(
            "EXTRACT(YEAR FROM COALESCE(patent.filing_date, patent.publication_date, patent.grant_date)) >= %(year_min)s"
        )

    if year_max is not None:
        params["year_max"] = year_max
        conditions.append(
            "EXTRACT(YEAR FROM COALESCE(patent.filing_date, patent.publication_date, patent.grant_date)) <= %(year_max)s"
        )

    if applicant:
        params["applicant_pattern"] = f"%{applicant}%"
        conditions.append("COALESCE(patent.applicants_raw, '') ILIKE %(applicant_pattern)s")

    where_sql = ""
    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    query = (
        PATENT_LIST_SELECT_SQL
        + where_sql
        + "\n"
        + PATENT_ORDER_BY_SQL
        + "\nOFFSET %(offset)s LIMIT %(page_size)s"
    )
    rows = conn.execute(query, params).fetchall()

    total = int(rows[0]["total_count"]) if rows else 0
    items = [
        PatentListItem(
            patent_id=row["patent_id"],
            patent_number=row["patent_number"],
            title_clean=row["title_clean"],
            filing_date=row["filing_date"],
            publication_date=row["publication_date"],
            patent_type=row["patent_type"],
            applicants_raw=row["applicants_raw"],
        )
        for row in rows
    ]
    return PatentListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


@router.get("/professors", response_model=ProfessorListResponse)
def list_professors(
    q: str | None = Query(default=None),
    institution: str | None = Query(default=None),
    discipline_family: str | None = Query(default=None),
    has_verified_papers: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    conn: Any = Depends(get_pg_conn),
) -> ProfessorListResponse:
    return _list_professors(
        conn,
        q=q,
        institution=institution,
        discipline_family=discipline_family,
        has_verified_papers=has_verified_papers,
        page=page,
        page_size=page_size,
    )


@router.get("/professors/{professor_id}", response_model=ProfessorDetailResponse)
def get_professor_detail(
    professor_id: str,
    conn: Any = Depends(get_pg_conn),
) -> ProfessorDetailResponse:
    professor_row = conn.execute(PROFESSOR_DETAIL_SQL, (professor_id,)).fetchone()
    if professor_row is None:
        raise HTTPException(status_code=404, detail="Professor not found")
    professor_payload = dict(professor_row)
    rejected_papers_total = int(professor_payload.pop("rejected_papers_total") or 0)
    professor = ProfessorWithProvenance.model_validate(professor_payload)

    affiliations = _rows_to_models(
        conn.execute(PROFESSOR_AFFILIATIONS_SQL, (professor_id,)).fetchall(),
        ProfessorAffiliationWithProvenance,
    )

    grouped_facts: dict[str, list[ProfessorFactValue]] = {
        fact_type: [] for fact_type in PROFESSOR_FACT_TYPES
    }
    for row in conn.execute(PROFESSOR_FACTS_SQL, (professor_id,)).fetchall():
        grouped_facts[row["fact_type"]].append(
            ProfessorFactValue.model_validate(dict(row))
        )

    verified_papers = _paper_summary_rows(
        conn,
        professor_id=professor_id,
        link_status="verified",
    )
    candidate_papers = _paper_summary_rows(
        conn,
        professor_id=professor_id,
        link_status="candidate",
    )
    rejected_papers = _paper_summary_rows(
        conn,
        professor_id=professor_id,
        link_status="rejected",
    )

    source_pages_row = conn.execute(
        PROFESSOR_SOURCE_PAGES_USED_SQL,
        (professor_id, professor_id),
    ).fetchone()

    return ProfessorDetailResponse(
        professor=professor,
        affiliations=affiliations,
        facts_by_type=grouped_facts,
        verified_papers=verified_papers,
        candidate_papers=candidate_papers,
        rejected_papers=rejected_papers,
        rejected_papers_total=rejected_papers_total,
        source_pages_used=(
            int(source_pages_row["source_pages_used"]) if source_pages_row else 0
        ),
    )


@router.get(
    "/facets/professor-institutions",
    response_model=list[ProfessorInstitutionFacet],
)
def list_professor_institution_facets(
    conn: Any = Depends(get_pg_conn),
) -> list[ProfessorInstitutionFacet]:
    return _rows_to_models(
        conn.execute(PROFESSOR_INSTITUTION_FACETS_SQL).fetchall(),
        ProfessorInstitutionFacet,
    )


@router.get("/facets/research-topics", response_model=list[ResearchTopicFacet])
def list_research_topic_facets(
    conn: Any = Depends(get_pg_conn),
) -> list[ResearchTopicFacet]:
    return _rows_to_models(
        conn.execute(RESEARCH_TOPIC_FACETS_SQL).fetchall(),
        ResearchTopicFacet,
    )


@router.get("/papers", response_model=PaperListResponse)
def list_papers(
    q: str | None = Query(default=None),
    year_min: int | None = Query(default=None),
    year_max: int | None = Query(default=None),
    has_verified_professor: bool | None = Query(default=None),
    min_citations: int | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    conn: Any = Depends(get_pg_conn),
) -> PaperListResponse:
    return _list_papers(
        conn,
        q=q,
        year_min=year_min,
        year_max=year_max,
        has_verified_professor=has_verified_professor,
        min_citations=min_citations,
        page=page,
        page_size=page_size,
    )


@router.get("/papers/{paper_id}", response_model=PaperDetailResponse)
def get_paper_detail(
    paper_id: str,
    conn: Any = Depends(get_pg_conn),
) -> PaperDetailResponse:
    paper_row = conn.execute(
        """
        SELECT *
        FROM paper
        WHERE paper_id = %s
        """,
        (paper_id,),
    ).fetchone()
    paper = _row_to_model(paper_row, Paper)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    linked_professors = LinkedProfessorsByStatus()
    for row in conn.execute(PAPER_LINKED_PROFESSORS_SQL, (paper_id,)).fetchall():
        summary = LinkedProfessorSummary.model_validate(dict(row))
        if row["link_status"] == "verified":
            linked_professors.verified.append(summary)
        elif row["link_status"] == "candidate":
            linked_professors.candidate.append(summary)
        elif row["link_status"] == "rejected":
            linked_professors.rejected.append(summary)

    return PaperDetailResponse(
        paper=paper,
        linked_professors=linked_professors,
    )


@router.get("/patents", response_model=PatentListResponse)
def list_patents(
    q: str | None = Query(default=None),
    year_min: int | None = Query(default=None),
    year_max: int | None = Query(default=None),
    applicant: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    conn: Any = Depends(get_pg_conn),
) -> PatentListResponse:
    return _list_patents(
        conn,
        q=q,
        year_min=year_min,
        year_max=year_max,
        applicant=applicant,
        page=page,
        page_size=page_size,
    )


@router.get("/patents/{patent_id}", response_model=PatentDetailResponse)
def get_patent_detail(
    patent_id: str,
    conn: Any = Depends(get_pg_conn),
) -> PatentDetailResponse:
    patent_row = conn.execute(
        """
        SELECT *
        FROM patent
        WHERE patent_id = %s
        """,
        (patent_id,),
    ).fetchone()
    patent = _row_to_model(patent_row, Patent)
    if patent is None:
        raise HTTPException(status_code=404, detail="Patent not found")

    linked_companies = _rows_to_models(
        conn.execute(PATENT_LINKED_COMPANIES_SQL, (patent_id,)).fetchall(),
        PatentLinkedCompany,
    )
    linked_professors = _rows_to_models(
        conn.execute(PATENT_LINKED_PROFESSORS_SQL, (patent_id,)).fetchall(),
        PatentLinkedProfessor,
    )

    return PatentDetailResponse(
        patent=patent,
        linked_companies=linked_companies,
        linked_professors=linked_professors,
    )
