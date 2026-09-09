from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Literal
from urllib.parse import urlparse
from uuid import UUID

from psycopg import Connection

from src.data_agents.paper.canonical_writer import upsert_paper
from src.data_agents.paper.title_cleaner import clean_paper_title
from src.data_agents.quality.threshold_config import (
    PROFESSOR_PAPER_LINK_PROMOTION,
)
from src.data_agents.storage.postgres.pipeline_run import require_real_run_id

from .name_identity_gate import NameIdentityCandidate, NameIdentityDecision
from .fact_dedup_key import completeness_score, facts_are_duplicates
from .homepage_source_filter import is_homepage_publication_ingest_url
from .name_selection import is_obvious_non_person_name, is_same_person_name_variant
from .publish_helpers import build_professor_id, is_official_url
from .quality_gate import evaluate_and_persist_professor_quality
from .topic_quality import split_compound_research_topic

if TYPE_CHECKING:
    from src.data_agents.professor.cross_domain import PaperStagingRecord
    from src.data_agents.professor.models import EnrichedProfessorProfile


logger = logging.getLogger(__name__)

OFFICIAL_FACT_CONFIDENCE = Decimal("0.85")
NON_OFFICIAL_FACT_CONFIDENCE = Decimal("0.70")
_METRICS_SOURCES = {"openalex", "verified_link_only", "mixed"}
_SOURCE_PAGE_ROLE_PROVENANCE_PREFIX = "source_page_role:"
_OWNED_HOMEPAGE_SOURCE_PAGE_ROLES = frozenset(
    {"official_publication_page", "personal_homepage", "lab_homepage"}
)
_GENERIC_CONTACT_EMAILS = frozenset(
    {
        "cpoe@szu.edu.cn",
        "jcdlxy@mail.sysu.edu.cn",
        "sai@cuhk.edu.cn",
        "sds@cuhk.edu.cn",
        "sofe@mail.sysu.edu",
        "synbiofaculty@suat-sz.edu.cn",
        "szsky@szu.edu.cn",
        "yzb@uestc.edu.cn",
    }
)
_GENERIC_CONTACT_FOOTER_MARKERS = (
    "admissionscopyright",
    "followussztuwechat",
    "copyright",
)
_EXTERNAL_ACADEMIC_PROFILE_HOST_SUFFIXES = (
    "researchgate.net",
    "orcid.org",
    "dblp.org",
    "inspirehep.net",
    "semanticscholar.org",
)
_EXTERNAL_ACADEMIC_PROFILE_HOST_CONTAINS = (
    "scholar.google.",
)
_SOURCE_PAGE_ROLE_CONFLICT_EXPR = (
    "CASE "
    "WHEN source_page.page_role IN ('official_profile', 'official_publication_page') "
    "AND EXCLUDED.page_role IN ('personal_homepage', 'lab_homepage') "
    "THEN source_page.page_role "
    "ELSE EXCLUDED.page_role "
    "END"
)
_STALE_PROFESSOR_NAME_JUNK_TITLES = frozenset({"友情链接", "教师学习"})

_DISCIPLINE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "computer_science",
        (
            "computer",
            "software",
            "artificial intelligence",
            "machine learning",
            "deep learning",
            "data science",
            "ai",
            "算法",
            "计算机",
            "软件",
            "人工智能",
            "机器学习",
            "深度学习",
            "网络空间",
            "信息安全",
        ),
    ),
    (
        "electrical_engineering",
        (
            "electrical",
            "electronics",
            "microelectronics",
            "signal",
            "communication",
            "information engineering",
            "电子",
            "电气",
            "微电子",
            "通信",
            "信号",
            "信息工程",
            "集成电路",
        ),
    ),
    (
        "mechanical_engineering",
        (
            "mechanical",
            "robot",
            "manufacturing",
            "automation",
            "机电",
            "机械",
            "机器人",
            "制造",
            "自动化",
        ),
    ),
    (
        "materials",
        (
            "materials",
            "material science",
            "metallurgy",
            "材料",
            "材料科学",
            "冶金",
        ),
    ),
    (
        "biomedical",
        (
            "biomedical",
            "bioengineering",
            "biology",
            "medicine",
            "medical",
            "生物",
            "医学",
            "医工",
            "生物医学",
        ),
    ),
    (
        "mathematics",
        (
            "mathematics",
            "math",
            "statistics",
            "applied math",
            "数学",
            "统计",
            "应用数学",
        ),
    ),
    (
        "physics",
        (
            "physics",
            "quantum",
            "optics",
            "photonics",
            "物理",
            "量子",
            "光学",
            "光子",
        ),
    ),
    (
        "chemistry",
        (
            "chemistry",
            "chemical",
            "molecular",
            "化学",
            "分子",
            "化工",
        ),
    ),
    (
        "interdisciplinary",
        (
            "interdisciplinary",
            "跨学科",
            "交叉",
        ),
    ),
)


@dataclass(frozen=True)
class ProfessorCanonicalReport:
    professor_id: str
    is_new_professor: bool
    affiliations_written: int
    facts_written: int
    papers_written: int
    professor_paper_links_written: int
    professor_paper_links_verified: int


ProfessorLifecycleState = Literal["active", "archived", "merged_to_other_school"]
_PROFESSOR_LIFECYCLE_STATES = {"active", "archived", "merged_to_other_school"}


@dataclass(frozen=True)
class ProfessorLifecycleUpdateReport:
    professor_id: str
    previous_lifecycle_state: str
    lifecycle_state: str
    previous_lifecycle_merged_into_id: str | None
    lifecycle_merged_into_id: str | None


def write_professor_bundle(
    conn: Connection,
    *,
    enriched: EnrichedProfessorProfile,
    paper_staging: list[PaperStagingRecord] | None = None,
    official_profile_page_id: UUID | None = None,
    name_identity_gate: Callable[
        [NameIdentityCandidate], NameIdentityDecision
    ]
    | None = None,
    run_id: UUID | str,
) -> ProfessorCanonicalReport:
    """Upsert a professor bundle into canonical Postgres tables."""
    run_id = require_real_run_id(run_id, writer_name="write_professor_bundle")

    professor_name = _clean_text(getattr(enriched, "name", None))
    if not professor_name:
        raise ValueError("enriched.name must be non-empty")

    professor_id = _resolve_professor_id_for_write(
        conn,
        enriched=enriched,
        fallback_professor_id=build_professor_id(enriched),
    )
    primary_page_id = official_profile_page_id or _resolve_primary_profile_page_id(
        conn,
        enriched=enriched,
        professor_id=professor_id,
        run_id=run_id,
    )
    if primary_page_id is None:
        raise ValueError(
            "write_professor_bundle requires an official_profile_page_id or at least one evidence URL"
        )
    _claim_source_page_for_professor(
        conn,
        page_id=primary_page_id,
        professor_id=professor_id,
        run_id=run_id,
    )

    is_new_professor = _upsert_professor_row(
        conn,
        professor_id=professor_id,
        enriched=enriched,
        primary_page_id=primary_page_id,
        name_identity_gate=name_identity_gate,
        run_id=run_id,
    )

    affiliation_count = 0
    primary_affiliation = _build_primary_affiliation(enriched)
    if primary_affiliation is not None:
        _upsert_affiliation(
            conn,
            professor_id=professor_id,
            institution=primary_affiliation["institution"],
            department=primary_affiliation["department"],
            title=primary_affiliation["title"],
            is_primary=True,
            is_current=True,
            start_year=None,
            end_year=None,
            source_page_id=primary_page_id,
            run_id=run_id,
        )
        affiliation_count += 1

    for work_entry in _iter_list(getattr(enriched, "work_experience", None)):
        organization = _clean_text(_get_attr(work_entry, "organization"))
        if not organization:
            continue
        _upsert_affiliation(
            conn,
            professor_id=professor_id,
            institution=organization,
            department=None,
            title=_clean_text(_get_attr(work_entry, "role")),
            is_primary=False,
            is_current=False,
            start_year=_get_attr(work_entry, "start_year"),
            end_year=_get_attr(work_entry, "end_year"),
            source_page_id=primary_page_id,
            run_id=run_id,
        )
        affiliation_count += 1

    facts_written = 0
    atomic_directions: list[str] = []
    for raw_direction in _iter_list(getattr(enriched, "research_directions", None)):
        atomic_directions.extend(split_compound_research_topic(raw_direction))
    for direction in _dedupe_strings(atomic_directions):
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="research_topic",
            value_raw=direction,
            source_page_id=primary_page_id,
            evidence_span=_fact_evidence_span(enriched, direction),
            confidence=_fact_confidence_for_url(_primary_evidence_url(enriched)),
            run_id=run_id,
        )
        facts_written += 1

    for education_entry in _iter_list(getattr(enriched, "education_structured", None)):
        value_raw = _format_education_entry(education_entry)
        if not value_raw:
            continue
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="education",
            value_raw=value_raw,
            source_page_id=primary_page_id,
            evidence_span=_fact_evidence_span(enriched, value_raw),
            confidence=_fact_confidence_for_url(_primary_evidence_url(enriched)),
            run_id=run_id,
        )
        facts_written += 1

    for work_entry in _iter_list(getattr(enriched, "work_experience", None)):
        value_raw = _format_work_entry(work_entry)
        if not value_raw:
            continue
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="work_experience",
            value_raw=value_raw,
            source_page_id=primary_page_id,
            evidence_span=_fact_evidence_span(enriched, value_raw),
            confidence=_fact_confidence_for_url(_primary_evidence_url(enriched)),
            run_id=run_id,
        )
        facts_written += 1

    for award in _dedupe_strings(_iter_list(getattr(enriched, "awards", None))):
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="award",
            value_raw=award,
            source_page_id=primary_page_id,
            evidence_span=_fact_evidence_span(enriched, award),
            confidence=_fact_confidence_for_url(_primary_evidence_url(enriched)),
            run_id=run_id,
        )
        facts_written += 1

    for position in _dedupe_strings(_iter_list(getattr(enriched, "academic_positions", None))):
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="academic_position",
            value_raw=position,
            value_normalized=position,
            source_page_id=primary_page_id,
            evidence_span=_fact_evidence_span(enriched, position),
            confidence=_fact_confidence_for_url(_primary_evidence_url(enriched)),
            run_id=run_id,
        )
        facts_written += 1

    email = _clean_text(getattr(enriched, "email", None))
    if email and not _is_generic_contact_email(email):
        _retire_conflicting_contact_email_facts(
            conn,
            professor_id=professor_id,
            source_page_id=primary_page_id,
            accepted_email=email,
            run_id=run_id,
        )
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="contact",
            value_raw=email,
            source_page_id=primary_page_id,
            evidence_span=_fact_evidence_span(enriched, email),
            confidence=_fact_confidence_for_url(_primary_evidence_url(enriched)),
            run_id=run_id,
        )
        facts_written += 1
    elif email:
        logger.info(
            "Skipping generic contact email %s for professor %s",
            email,
            professor_id,
        )

    homepage_url = _clean_text(getattr(enriched, "homepage", None))
    homepage_role = _classify_homepage_source_page_role(homepage_url)
    external_profile_urls: list[str] = []
    if homepage_url and homepage_role == "official_external_profile":
        external_profile_urls.append(homepage_url)
    elif homepage_url and homepage_role:
        homepage_page_id = upsert_source_page_for_url(
            conn,
            url=homepage_url,
            page_role=homepage_role,
            owner_scope_kind="professor",
            owner_scope_ref=professor_id,
            is_official_source=homepage_role == "official_profile"
            or is_official_url(homepage_url),
            run_id=run_id,
        )
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="homepage",
            value_raw=homepage_url,
            source_page_id=homepage_page_id,
            evidence_span=_fact_evidence_span(enriched, homepage_url),
            confidence=_fact_confidence_for_url(homepage_url),
            run_id=run_id,
        )
        facts_written += 1

    external_profile_urls.extend(
        _iter_list(getattr(enriched, "scholarly_profile_urls", None))
    )
    for external_url in _dedupe_strings(external_profile_urls):
        external_page_id = upsert_source_page_for_url(
            conn,
            url=external_url,
            page_role="official_external_profile",
            owner_scope_kind="professor",
            owner_scope_ref=professor_id,
            is_official_source=True,
            run_id=run_id,
        )
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="external_profile",
            value_raw=external_url,
            source_page_id=external_page_id,
            evidence_span=_fact_evidence_span(enriched, external_url),
            confidence=_fact_confidence_for_url(external_url),
            run_id=run_id,
        )
        facts_written += 1

    _upsert_owned_homepage_source_pages(
        conn,
        enriched=enriched,
        professor_id=professor_id,
        run_id=run_id,
    )

    written_paper_ids: set[str] = set()
    written_link_keys: set[tuple[str, str]] = set()
    verified_link_keys: set[tuple[str, str]] = set()
    for staging_record in paper_staging or []:
        paper_title = _clean_text(_get_attr(staging_record, "title"))
        if not paper_title:
            continue
        title_clean = clean_paper_title(paper_title)
        if not title_clean:
            continue
        evidence_source_type = _map_paper_evidence_source(staging_record)
        paper_report = upsert_paper(
            conn,
            title_clean=title_clean,
            title_raw=_clean_text(_get_attr(staging_record, "title_raw"))
            or paper_title,
            doi=_clean_text(_get_attr(staging_record, "doi")),
            arxiv_id=_clean_text(_get_attr(staging_record, "arxiv_id")),
            openalex_id=_clean_text(_get_attr(staging_record, "openalex_id")),
            semantic_scholar_id=_clean_text(
                _get_attr(staging_record, "semantic_scholar_id")
            ),
            year=_get_attr(staging_record, "year"),
            venue=_clean_text(_get_attr(staging_record, "venue")),
            abstract_clean=_clean_text(_get_attr(staging_record, "abstract")),
            authors_display=_authors_display(staging_record),
            citation_count=_get_attr(staging_record, "citation_count"),
            canonical_source=_paper_canonical_source(staging_record),
            run_id=run_id,
        )
        written_paper_ids.add(paper_report.paper_id)

        link_status = _promote_link_status(staging_record, evidence_source_type)
        evidence_page_id = _paper_evidence_page_id(
            conn,
            professor_id=professor_id,
            staging_record=staging_record,
            evidence_source_type=evidence_source_type,
            run_id=run_id,
        )
        _upsert_professor_paper_link(
            conn,
            professor_id=professor_id,
            paper_id=paper_report.paper_id,
            link_status=link_status,
            evidence_source_type=evidence_source_type,
            evidence_page_id=evidence_page_id,
            evidence_api_source=(
                evidence_source_type
                if evidence_source_type == "academic_api_with_affiliation_match"
                else None
            ),
            match_reason=_link_match_reason(
                evidence_source_type=evidence_source_type,
                link_status=link_status,
            ),
            author_name_match_score=_decimal_score(
                _get_attr(staging_record, "disambiguation_confidence", 0.85),
                default=Decimal("0.85"),
            ),
            topic_consistency_score=_decimal_score(
                _get_attr(staging_record, "topic_consistency_score"),
            ),
            institution_consistency_score=_decimal_score(
                _get_attr(staging_record, "institution_consistency_score"),
            ),
            is_officially_listed=evidence_source_type
            != "academic_api_with_affiliation_match",
            run_id=run_id,
        )
        link_key = (professor_id, paper_report.paper_id)
        written_link_keys.add(link_key)
        if link_status == "verified":
            verified_link_keys.add(link_key)

    evaluate_and_persist_professor_quality(conn, professor_id)

    return ProfessorCanonicalReport(
        professor_id=professor_id,
        is_new_professor=is_new_professor,
        affiliations_written=affiliation_count,
        facts_written=facts_written,
        papers_written=len(written_paper_ids),
        professor_paper_links_written=len(written_link_keys),
        professor_paper_links_verified=len(verified_link_keys),
    )


def set_professor_lifecycle_state(
    conn: Connection,
    *,
    professor_id: str,
    lifecycle_state: ProfessorLifecycleState,
    actor: str,
    note: str | None = None,
    lifecycle_merged_into_id: str | None = None,
) -> ProfessorLifecycleUpdateReport:
    """Explicitly update professor lifecycle without coupling it to quality."""
    if lifecycle_state not in _PROFESSOR_LIFECYCLE_STATES:
        raise ValueError(f"invalid professor lifecycle_state: {lifecycle_state}")

    normalized_actor = _clean_text(actor)
    if not normalized_actor:
        raise ValueError("actor must be non-empty")

    merged_target = _clean_text(lifecycle_merged_into_id)
    if lifecycle_state != "merged_to_other_school":
        merged_target = None

    row = conn.execute(
        """
        SELECT lifecycle_state,
               lifecycle_merged_into_id,
               updated_at
          FROM professor
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"professor not found: {professor_id}")

    previous_state = str(_row_value(row, "lifecycle_state", 0) or "active")
    previous_target = _clean_text(_row_value(row, "lifecycle_merged_into_id", 1))
    observed_updated_at = _row_value(row, "updated_at", 2) or datetime.now(timezone.utc)

    conn.execute(
        """
        UPDATE professor
           SET lifecycle_state = %s,
               lifecycle_merged_into_id = %s,
               updated_at = now()
         WHERE professor_id = %s
        """,
        (lifecycle_state, merged_target, professor_id),
    )
    audit_note = _lifecycle_audit_note(
        previous_state=previous_state,
        next_state=lifecycle_state,
        previous_target=previous_target,
        next_target=merged_target,
        note=note,
    )
    conn.execute(
        """
        INSERT INTO professor_admin_action (
            professor_id,
            action,
            actor,
            note,
            observed_data_updated_at
        )
        VALUES (%s, 'set_lifecycle_state', %s, %s, %s)
        """,
        (professor_id, normalized_actor, audit_note, observed_updated_at),
    )

    return ProfessorLifecycleUpdateReport(
        professor_id=professor_id,
        previous_lifecycle_state=previous_state,
        lifecycle_state=lifecycle_state,
        previous_lifecycle_merged_into_id=previous_target,
        lifecycle_merged_into_id=merged_target,
    )


def upsert_professor_metrics(
    conn: Connection,
    *,
    professor_id: str,
    h_index: int | None,
    citation_count: int | None,
    metrics_source: str | None,
    run_id: UUID | str,
) -> None:
    """Compute verified paper_count and write professor academic metrics."""
    run_id = require_real_run_id(run_id, writer_name="upsert_professor_metrics")

    if metrics_source is None:
        if h_index is not None or citation_count is not None:
            raise ValueError("metrics_source is required when OpenAlex metrics exist")
        metrics_source = "verified_link_only"
    if metrics_source not in _METRICS_SOURCES:
        raise ValueError(f"invalid metrics_source: {metrics_source}")

    paper_count_row = conn.execute(
        """
        SELECT count(*)::int AS n
        FROM professor_paper_link
        WHERE professor_id = %s AND link_status = 'verified'
        """,
        (professor_id,),
    ).fetchone()
    paper_count = int(_row_value(paper_count_row, "n")) if paper_count_row else 0

    conn.execute(
        """
        UPDATE professor
        SET h_index = %s,
            citation_count = %s,
            paper_count = %s,
            metrics_computed_at = LEAST(now(), COALESCE(last_refreshed_at, now())),
            metrics_source = %s,
            run_id = %s,
            updated_at = now()
        WHERE professor_id = %s
          AND identity_status <> 'merged_into'
        """,
        (h_index, citation_count, paper_count, metrics_source, run_id, professor_id),
    )


def upsert_source_page_for_url(
    conn: Connection,
    *,
    url: str,
    page_role: str,
    owner_scope_kind: str | None = None,
    owner_scope_ref: str | None = None,
    fetched_at: datetime | None = None,
    is_official_source: bool = False,
    run_id: UUID | str,
) -> UUID:
    """Upsert a source_page row keyed by URL and return its page id."""
    run_id = require_real_run_id(run_id, writer_name="upsert_source_page_for_url")

    normalized_url = _clean_text(url)
    if not normalized_url:
        raise ValueError("url must be non-empty")
    normalized_page_role = _strip_postgres_nul(page_role)
    if not normalized_page_role:
        raise ValueError("page_role must be non-empty")
    normalized_owner_scope_kind = _strip_postgres_nul(owner_scope_kind)
    normalized_owner_scope_ref = _strip_postgres_nul(owner_scope_ref)
    effective_fetched_at = fetched_at or datetime.now(timezone.utc)
    row = conn.execute(
        f"""
        INSERT INTO source_page (
            url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            fetched_at,
            is_official_source,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url) DO UPDATE
           SET page_role          = {_SOURCE_PAGE_ROLE_CONFLICT_EXPR},
               owner_scope_kind   = COALESCE(EXCLUDED.owner_scope_kind, source_page.owner_scope_kind),
               owner_scope_ref    = COALESCE(EXCLUDED.owner_scope_ref, source_page.owner_scope_ref),
               fetched_at         = GREATEST(source_page.fetched_at, EXCLUDED.fetched_at),
               is_official_source = source_page.is_official_source OR EXCLUDED.is_official_source,
               run_id             = COALESCE(EXCLUDED.run_id, source_page.run_id)
        RETURNING page_id
        """,
        (
            normalized_url,
            normalized_page_role,
            normalized_owner_scope_kind,
            normalized_owner_scope_ref,
            effective_fetched_at,
            is_official_source,
            run_id,
        ),
    ).fetchone()
    assert row is not None
    return _row_value(row, "page_id")


def _resolve_primary_profile_page_id(
    conn: Connection,
    *,
    enriched: EnrichedProfessorProfile,
    professor_id: str,
    run_id: UUID | str,
) -> UUID | None:
    url = _primary_evidence_url(enriched)
    if not url:
        return None
    return upsert_source_page_for_url(
        conn,
        url=url,
        page_role="official_profile",
        owner_scope_kind="professor",
        owner_scope_ref=professor_id,
        is_official_source=is_official_url(url),
        run_id=run_id,
    )


def _resolve_professor_id_for_write(
    conn: Connection,
    *,
    enriched: EnrichedProfessorProfile,
    fallback_professor_id: str,
) -> str:
    profile_url = _primary_evidence_url(enriched)
    if not profile_url:
        return fallback_professor_id
    canonical_name = _clean_text(getattr(enriched, "name", None))
    row = conn.execute(
        """
        SELECT p.professor_id, p.canonical_name
          FROM professor p
          JOIN source_page sp
            ON sp.page_id = p.primary_official_profile_page_id
         WHERE sp.url = %s
           AND p.identity_status <> 'merged_into'
         ORDER BY (p.canonical_name = %s) DESC,
                  p.updated_at DESC
         LIMIT 1
        """,
        (profile_url, canonical_name),
    ).fetchone()
    if row is not None:
        resolved = _professor_id_if_existing_name_matches(row, canonical_name)
        if resolved is not None:
            return resolved

    row = conn.execute(
        """
        SELECT sp.owner_scope_ref AS professor_id, p.canonical_name
          FROM source_page sp
          JOIN professor p
            ON p.professor_id = sp.owner_scope_ref
         WHERE sp.url = %s
           AND sp.owner_scope_kind = 'professor'
           AND sp.owner_scope_ref IS NOT NULL
           AND p.identity_status <> 'merged_into'
         ORDER BY (p.canonical_name = %s) DESC,
                  p.updated_at DESC
         LIMIT 1
        """,
        (profile_url, canonical_name),
    ).fetchone()
    if row is not None:
        resolved = _professor_id_if_existing_name_matches(row, canonical_name)
        if resolved is not None:
            return resolved
    return fallback_professor_id


def _professor_id_if_existing_name_matches(
    row: object,
    canonical_name: str | None,
) -> str | None:
    professor_id = _row_value(row, "professor_id", 0)
    existing_name = _clean_text(_row_value(row, "canonical_name", 1))
    if _existing_professor_name_matches(
        existing_name=existing_name,
        canonical_name=canonical_name,
    ):
        return professor_id
    logger.warning(
        "Skipping professor_id reuse for source_page owner %s: existing name %r "
        "does not match candidate %r",
        professor_id,
        existing_name,
        canonical_name,
    )
    return None


def _existing_professor_name_matches(
    *,
    existing_name: str | None,
    canonical_name: str | None,
) -> bool:
    if not existing_name or not canonical_name:
        return True
    if existing_name == canonical_name:
        return True
    if is_same_person_name_variant(existing_name, canonical_name):
        return True
    return _can_reclaim_stale_junk_professor_name(
        existing_name=existing_name,
        canonical_name=canonical_name,
    )


def _can_reclaim_stale_junk_professor_name(
    *,
    existing_name: str,
    canonical_name: str,
) -> bool:
    return (
        _is_obvious_professor_name_junk(existing_name)
        and not _is_obvious_professor_name_junk(canonical_name)
    )


def _is_obvious_professor_name_junk(name: str | None) -> bool:
    return bool(
        name
        and (
            name in _STALE_PROFESSOR_NAME_JUNK_TITLES
            or is_obvious_non_person_name(name)
        )
    )


def _claim_source_page_for_professor(
    conn: Connection,
    *,
    page_id: UUID,
    professor_id: str,
    run_id: UUID | str,
) -> None:
    conn.execute(
        """
        UPDATE source_page
           SET owner_scope_kind = COALESCE(owner_scope_kind, 'professor'),
               owner_scope_ref = COALESCE(owner_scope_ref, %s),
               run_id = COALESCE(%s, run_id)
         WHERE page_id = %s
           AND (owner_scope_ref IS NULL OR owner_scope_ref = %s)
        """,
        (professor_id, run_id, page_id, professor_id),
    )


def _upsert_owned_homepage_source_pages(
    conn: Connection,
    *,
    enriched: EnrichedProfessorProfile,
    professor_id: str,
    run_id: UUID | str,
) -> None:
    for source_url, page_role in _iter_owned_homepage_source_pages(enriched):
        upsert_source_page_for_url(
            conn,
            url=source_url,
            page_role=page_role,
            owner_scope_kind="professor",
            owner_scope_ref=professor_id,
            is_official_source=is_official_url(source_url),
            run_id=run_id,
        )


def _upsert_professor_row(
    conn: Connection,
    *,
    professor_id: str,
    enriched: EnrichedProfessorProfile,
    primary_page_id: UUID,
    name_identity_gate: Callable[
        [NameIdentityCandidate], NameIdentityDecision
    ]
    | None = None,
    run_id: UUID | str,
) -> bool:
    canonical_name = _clean_text(getattr(enriched, "name", None))
    if not canonical_name or _is_obvious_professor_name_junk(canonical_name):
        raise ValueError(f"non-person canonical name rejected: {canonical_name!r}")

    is_new = (
        conn.execute(
            "SELECT 1 FROM professor WHERE professor_id = %s",
            (professor_id,),
        ).fetchone()
        is None
    )
    now = datetime.now(timezone.utc)
    candidate_name_en = _clean_text(getattr(enriched, "name_en", None))
    profile_summary = _clean_text(getattr(enriched, "profile_summary", None))
    paper_summary = _clean_text(getattr(enriched, "paper_summary", None))
    profile_raw_text = _clean_text(getattr(enriched, "profile_raw_text", None))
    if candidate_name_en and canonical_name and name_identity_gate is not None:
        if inspect.iscoroutinefunction(name_identity_gate):
            raise TypeError("name_identity_gate must be sync")
        decision = name_identity_gate(
            NameIdentityCandidate(
                canonical_name=canonical_name,
                candidate_name_en=candidate_name_en,
                source_url=getattr(enriched, "homepage", None),
            )
        )
        if not decision.accepted:
            logger.info(
                "name_identity_gate rejected canonical_name_en for %s / %s "
                "(confidence=%.2f, error=%s)",
                canonical_name,
                candidate_name_en,
                decision.confidence,
                decision.error,
            )
            candidate_name_en = None
    conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            canonical_name_en,
            discipline_family,
            primary_official_profile_page_id,
            profile_summary,
            paper_summary,
            profile_raw_text,
            first_seen_at,
            last_refreshed_at,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (professor_id) DO UPDATE
           SET canonical_name                    = EXCLUDED.canonical_name,
               canonical_name_en                 = EXCLUDED.canonical_name_en,
               discipline_family                 = EXCLUDED.discipline_family,
               primary_official_profile_page_id  = EXCLUDED.primary_official_profile_page_id,
               profile_summary                   = COALESCE(EXCLUDED.profile_summary, professor.profile_summary),
               paper_summary                     = COALESCE(EXCLUDED.paper_summary, professor.paper_summary),
               profile_raw_text                  = COALESCE(EXCLUDED.profile_raw_text, professor.profile_raw_text),
               last_refreshed_at                 = EXCLUDED.last_refreshed_at,
               run_id                            = COALESCE(EXCLUDED.run_id, professor.run_id),
               updated_at                        = now()
        """,
        (
            professor_id,
            canonical_name,
            candidate_name_en,
            _classify_discipline(enriched),
            primary_page_id,
            profile_summary,
            paper_summary,
            profile_raw_text,
            now,
            now,
            run_id,
        ),
    )
    return is_new


def _build_primary_affiliation(
    enriched: EnrichedProfessorProfile,
) -> dict[str, str | None] | None:
    institution = _clean_text(getattr(enriched, "institution", None))
    if not institution:
        return None
    return {
        "institution": institution,
        "department": _clean_text(getattr(enriched, "department", None)),
        "title": _clean_text(getattr(enriched, "title", None)),
    }


def _upsert_affiliation(
    conn: Connection,
    *,
    professor_id: str,
    institution: str,
    department: str | None,
    title: str | None,
    is_primary: bool,
    is_current: bool,
    start_year: int | None,
    end_year: int | None,
    source_page_id: UUID,
    run_id: UUID | str,
) -> None:
    row = conn.execute(
        """
        SELECT affiliation_id
        FROM professor_affiliation
        WHERE professor_id = %s
          AND institution = %s
          AND department IS NOT DISTINCT FROM %s
          AND title IS NOT DISTINCT FROM %s
          AND is_current = %s
          AND start_year IS NOT DISTINCT FROM %s
          AND end_year IS NOT DISTINCT FROM %s
          AND source_page_id = %s
        LIMIT 1
        """,
        (
            professor_id,
            institution,
            department,
            title,
            is_current,
            start_year,
            end_year,
            source_page_id,
        ),
    ).fetchone()
    affiliation_id = _row_value(row, "affiliation_id") if row is not None else None
    if is_primary:
        _demote_existing_primary_affiliations(
            conn, professor_id=professor_id, keep_affiliation_id=affiliation_id
        )
    if is_primary and is_current:
        _supersede_current_primary_affiliation_variants(
            conn,
            professor_id=professor_id,
            institution=institution,
            department=department,
            source_page_id=source_page_id,
            keep_affiliation_id=affiliation_id,
        )
    if row is not None:
        conn.execute(
            """
            UPDATE professor_affiliation
               SET updated_at = now(),
                   is_primary = %s,
                   is_current = %s,
                   run_id = COALESCE(%s, run_id)
             WHERE affiliation_id = %s
            """,
            (is_primary, is_current, run_id, affiliation_id),
        )
        return

    conn.execute(
        """
        INSERT INTO professor_affiliation (
            professor_id,
            institution,
            department,
            title,
            is_primary,
            is_current,
            start_year,
            end_year,
            source_page_id,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            professor_id,
            institution,
            department,
            title,
            is_primary,
            is_current,
            start_year,
            end_year,
            source_page_id,
            run_id,
        ),
    )


def _demote_existing_primary_affiliations(
    conn: Connection,
    *,
    professor_id: str,
    keep_affiliation_id: UUID | None,
) -> None:
    if keep_affiliation_id is None:
        conn.execute(
            """
            UPDATE professor_affiliation
               SET is_primary = false,
                   updated_at = now()
             WHERE professor_id = %s
               AND is_primary = true
            """,
            (professor_id,),
        )
        return
    conn.execute(
        """
        UPDATE professor_affiliation
           SET is_primary = false,
               updated_at = now()
         WHERE professor_id = %s
           AND is_primary = true
           AND affiliation_id <> %s
        """,
        (professor_id, keep_affiliation_id),
    )


def _supersede_current_primary_affiliation_variants(
    conn: Connection,
    *,
    professor_id: str,
    institution: str,
    department: str | None,
    source_page_id: UUID,
    keep_affiliation_id: UUID | None,
) -> None:
    conn.execute(
        """
        UPDATE professor_affiliation
           SET is_current = false,
               updated_at = now()
         WHERE professor_id = %s
           AND institution = %s
           AND department IS NOT DISTINCT FROM %s
           AND source_page_id = %s
           AND is_current = true
           AND affiliation_id IS DISTINCT FROM %s
        """,
        (professor_id, institution, department, source_page_id, keep_affiliation_id),
    )


def _upsert_fact(
    conn: Connection,
    *,
    professor_id: str,
    fact_type: str,
    value_raw: str,
    value_normalized: str | None = None,
    source_page_id: UUID,
    evidence_span: str,
    confidence: Decimal,
    run_id: UUID | str,
) -> str:
    value_raw = _strip_postgres_nul(value_raw) or ""
    value_normalized = _strip_postgres_nul(value_normalized)
    if value_normalized == "":
        value_normalized = None
    evidence_span = _strip_postgres_nul(evidence_span) or ""

    rows = conn.execute(
        """
        SELECT fact_id, value_raw, value_normalized
        FROM professor_fact
        WHERE professor_id = %s
          AND fact_type = %s
          AND status = 'active'
        """,
        (
            professor_id,
            fact_type,
        ),
    ).fetchall()

    # Format-normalizing semantic match: the same logical fact written as pipe,
    # JSON, bilingual prose or a gloss twin counts as one entry (see
    # fact_dedup_key). A literal-text key cannot match across encodings, which
    # is what let duplicates accumulate.
    matches = [
        row
        for row in rows
        if facts_are_duplicates(
            fact_type,
            value_raw,
            _row_value(row, "value_raw", 1) or _row_value(row, "value_normalized", 2),
        )
    ]

    def _supersede(fact_id: Any) -> None:
        conn.execute(
            """
            UPDATE professor_fact
               SET status = 'superseded',
                   run_id = COALESCE(%s, run_id),
                   updated_at = now()
             WHERE fact_id = %s
            """,
            (run_id, fact_id),
        )

    def _insert() -> None:
        conn.execute(
            """
            INSERT INTO professor_fact (
                professor_id,
                fact_type,
                value_raw,
                value_normalized,
                source_page_id,
                evidence_span,
                confidence,
                run_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                professor_id,
                fact_type,
                value_raw,
                value_normalized,
                source_page_id,
                evidence_span,
                confidence,
                run_id,
            ),
        )

    if not matches:
        _insert()
        return "inserted"

    # Keep-richest: structured-with-more-fields outranks prose; pipe-with-years
    # outranks year-less JSON. The richer representation stays active.
    best = max(
        matches,
        key=lambda r: completeness_score(
            _row_value(r, "value_raw", 1), _row_value(r, "value_normalized", 2)
        ),
    )
    candidate_score = completeness_score(value_raw, value_normalized)
    best_score = completeness_score(
        _row_value(best, "value_raw", 1), _row_value(best, "value_normalized", 2)
    )

    if candidate_score > best_score:
        # Candidate is richer: retire every duplicate twin, insert the candidate.
        for row in matches:
            _supersede(_row_value(row, "fact_id", 0))
        _insert()
        return "inserted"

    # Existing richest twin is kept untouched; retire any other duplicate twins
    # so exactly one active row remains for this logical fact.
    best_id = _row_value(best, "fact_id", 0)
    for row in matches:
        row_id = _row_value(row, "fact_id", 0)
        if row_id != best_id:
            _supersede(row_id)
    return "updated"


def _retire_conflicting_contact_email_facts(
    conn: Connection,
    *,
    professor_id: str,
    source_page_id: UUID,
    accepted_email: str,
    run_id: UUID | str,
) -> None:
    normalized_email = _normalize_contact_value(accepted_email)
    if not normalized_email or _is_generic_contact_email(normalized_email):
        return

    conn.execute(
        """
        UPDATE professor_fact
           SET status = 'superseded',
               run_id = COALESCE(%s, run_id),
               updated_at = now()
         WHERE professor_id = %s
           AND source_page_id = %s
           AND fact_type = 'contact'
           AND status = 'active'
           AND lower(regexp_replace(value_raw, '\\s+', '', 'g')) <> %s
           AND value_raw LIKE '%%@%%'
        """,
        (
            run_id,
            professor_id,
            source_page_id,
            normalized_email,
        ),
    )


def _is_generic_contact_email(value: object) -> bool:
    normalized = _normalize_contact_value(value)
    if not normalized:
        return False
    if normalized in _GENERIC_CONTACT_EMAILS:
        return True
    return any(marker in normalized for marker in _GENERIC_CONTACT_FOOTER_MARKERS)


def _normalize_contact_value(value: object) -> str:
    text = _clean_text(value) or ""
    return "".join(text.casefold().split())


def _upsert_professor_paper_link(
    conn: Connection,
    *,
    professor_id: str,
    paper_id: str,
    link_status: str,
    evidence_source_type: str,
    evidence_page_id: UUID | None,
    evidence_api_source: str | None,
    match_reason: str,
    author_name_match_score: Decimal,
    topic_consistency_score: Decimal | None,
    institution_consistency_score: Decimal | None,
    is_officially_listed: bool,
    run_id: UUID | str,
) -> None:
    run_id = require_real_run_id(run_id, writer_name="_upsert_professor_paper_link")
    verified_by = "rule_auto" if link_status == "verified" else None
    verified_at = datetime.now(timezone.utc) if link_status == "verified" else None
    conn.execute(
        """
        INSERT INTO professor_paper_link (
            professor_id,
            paper_id,
            link_status,
            evidence_source_type,
            evidence_page_id,
            evidence_api_source,
            match_reason,
            author_name_match_score,
            topic_consistency_score,
            institution_consistency_score,
            is_officially_listed,
            verified_by,
            verified_at,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (professor_id, paper_id) DO UPDATE
           SET link_status                    = EXCLUDED.link_status,
               evidence_source_type           = EXCLUDED.evidence_source_type,
               evidence_page_id               = EXCLUDED.evidence_page_id,
               evidence_api_source            = EXCLUDED.evidence_api_source,
               match_reason                   = EXCLUDED.match_reason,
               author_name_match_score        = EXCLUDED.author_name_match_score,
               topic_consistency_score        = EXCLUDED.topic_consistency_score,
               institution_consistency_score  = EXCLUDED.institution_consistency_score,
               is_officially_listed           = EXCLUDED.is_officially_listed,
               verified_by                    = EXCLUDED.verified_by,
               verified_at                    = EXCLUDED.verified_at,
               run_id                         = COALESCE(EXCLUDED.run_id, professor_paper_link.run_id),
               updated_at                     = now()
        """,
        (
            professor_id,
            paper_id,
            link_status,
            evidence_source_type,
            evidence_page_id,
            evidence_api_source,
            match_reason,
            author_name_match_score,
            topic_consistency_score,
            institution_consistency_score,
            is_officially_listed,
            verified_by,
            verified_at,
            run_id,
        ),
    )


def _primary_evidence_url(enriched: EnrichedProfessorProfile) -> str | None:
    candidates = [
        _clean_text(getattr(enriched, "profile_url", None)),
        *[
            _clean_text(url)
            for url in _iter_list(getattr(enriched, "evidence_urls", None))
        ],
    ]
    candidates = [candidate for candidate in candidates if candidate]
    for candidate in candidates:
        if is_official_url(candidate):
            return candidate
    return candidates[0] if candidates else None


def _fact_evidence_span(
    enriched: EnrichedProfessorProfile,
    fallback_text: str,
) -> str:
    anchor = getattr(enriched, "official_anchor_profile", None)
    candidate_text = _clean_text(_get_attr(anchor, "bio_text")) or _clean_text(
        getattr(enriched, "profile_summary", None)
    )
    evidence = (
        candidate_text
        or _clean_text(fallback_text)
        or _primary_evidence_url(enriched)
        or ""
    )
    return evidence[:200]


def _fact_confidence_for_url(url: str | None) -> Decimal:
    if url and is_official_url(url):
        return OFFICIAL_FACT_CONFIDENCE
    return NON_OFFICIAL_FACT_CONFIDENCE


def _classify_discipline(enriched: EnrichedProfessorProfile) -> str:
    haystack = " ".join(
        item
        for item in [
            _clean_text(getattr(enriched, "department", None)),
            *[
                _clean_text(item)
                for item in _iter_list(getattr(enriched, "research_directions", None))
            ],
        ]
        if item
    ).lower()
    for discipline, keywords in _DISCIPLINE_KEYWORDS:
        if any(keyword.lower() in haystack for keyword in keywords):
            return discipline
    return "other"


def _format_education_entry(entry: Any) -> str:
    school = _clean_text(_get_attr(entry, "school"))
    if not school:
        return ""
    parts = [school]
    degree = _clean_text(_get_attr(entry, "degree"))
    field = _clean_text(_get_attr(entry, "field"))
    years = _format_year_range(
        _get_attr(entry, "start_year"),
        _get_attr(entry, "end_year"),
    )
    if degree:
        parts.append(degree)
    if field:
        parts.append(field)
    if years:
        parts.append(years)
    return " | ".join(parts)


def _format_work_entry(entry: Any) -> str:
    organization = _clean_text(_get_attr(entry, "organization"))
    if not organization:
        return ""
    parts = [organization]
    role = _clean_text(_get_attr(entry, "role"))
    years = _format_year_range(
        _get_attr(entry, "start_year"),
        _get_attr(entry, "end_year"),
    )
    if role:
        parts.append(role)
    if years:
        parts.append(years)
    return " | ".join(parts)


def _format_year_range(start_year: object, end_year: object) -> str:
    if start_year is None and end_year is None:
        return ""
    return f"{start_year or '?'}-{end_year or 'present'}"


def _dedupe_strings(values: list[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _iter_owned_homepage_source_pages(
    enriched: EnrichedProfessorProfile,
) -> list[tuple[str, str]]:
    source_pages: dict[str, str] = {}

    provenance = getattr(enriched, "field_provenance", None)
    if isinstance(provenance, Mapping):
        for key, raw_role in provenance.items():
            if not isinstance(key, str):
                continue
            if not key.startswith(_SOURCE_PAGE_ROLE_PROVENANCE_PREFIX):
                continue
            source_url = _clean_text(key[len(_SOURCE_PAGE_ROLE_PROVENANCE_PREFIX):])
            page_role = _clean_text(raw_role)
            if (
                source_url
                and page_role in _OWNED_HOMEPAGE_SOURCE_PAGE_ROLES
                and is_homepage_publication_ingest_url(source_url)
            ):
                source_pages[source_url] = page_role

    for source_url in _dedupe_strings(
        _iter_list(getattr(enriched, "publication_evidence_urls", None))
    ):
        if not is_homepage_publication_ingest_url(source_url):
            continue
        source_pages.setdefault(
            source_url,
            _fallback_publication_source_page_role(source_url),
        )

    return list(source_pages.items())


def _fallback_publication_source_page_role(source_url: str) -> str:
    if is_official_url(source_url):
        return "official_publication_page"
    lowered = source_url.casefold()
    if any(token in lowered for token in ("lab", "group", "team", "课题组", "实验室")):
        return "lab_homepage"
    return "personal_homepage"


def _classify_homepage_source_page_role(source_url: object) -> str | None:
    url = _clean_text(source_url)
    if not url or any(char.isspace() for char in url):
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    hostname = (parsed.hostname or "").casefold().strip(".")
    if not hostname or hostname in {"https", "www.https"} or hostname.endswith(".https"):
        return None
    if _is_external_academic_profile_host(hostname):
        return "official_external_profile"
    if is_official_url(url):
        return "official_profile"
    lowered = url.casefold()
    if any(token in lowered for token in ("lab", "group", "team", "课题组", "实验室")):
        return "lab_homepage"
    return "personal_homepage"


def _is_external_academic_profile_host(hostname: str) -> bool:
    return any(token in hostname for token in _EXTERNAL_ACADEMIC_PROFILE_HOST_CONTAINS) or any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in _EXTERNAL_ACADEMIC_PROFILE_HOST_SUFFIXES
    )


def _iter_list(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _clean_text(value: object) -> str | None:
    text = _strip_postgres_nul(value)
    if text is None:
        return None
    text = text.strip()
    return text or None


def _strip_postgres_nul(value: object) -> str | None:
    if value is None:
        return None
    # PostgreSQL text values cannot contain U+0000; preserve all other Unicode.
    return str(value).replace("\x00", "")


def _lifecycle_audit_note(
    *,
    previous_state: str,
    next_state: str,
    previous_target: str | None,
    next_target: str | None,
    note: str | None,
) -> str:
    parts = [f"lifecycle_state {previous_state} -> {next_state}"]
    if previous_target != next_target:
        parts.append(
            "lifecycle_merged_into_id "
            f"{previous_target or '<none>'} -> {next_target or '<none>'}"
        )
    cleaned_note = _clean_text(note)
    if cleaned_note:
        parts.append(cleaned_note)
    return "; ".join(parts)


def _get_attr(obj: object, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _row_value(row: object, column: str, index: int = 0) -> Any:
    if isinstance(row, Mapping):
        return row[column]
    return row[index]  # type: ignore[index]


def _authors_display(record: Any) -> str | None:
    authors = [
        _clean_text(author)
        for author in _iter_list(_get_attr(record, "authors"))
        if _clean_text(author)
    ]
    if not authors:
        return None
    return ", ".join(authors)


def _paper_canonical_source(record: Any) -> str:
    source = (_clean_text(_get_attr(record, "source")) or "").lower()
    if source in {"openalex", "semantic_scholar", "crossref", "dblp", "arxiv"}:
        return source
    if source in {
        "official_publication_page",
        "personal_homepage",
        "cv_pdf",
        "official_external_profile",
    }:
        return "official_page"
    return "manual"


def _map_paper_evidence_source(record: Any) -> str:
    source = (
        _clean_text(_get_attr(record, "evidence_source"))
        or _clean_text(_get_attr(record, "source"))
        or ""
    ).lower()
    if source in PROFESSOR_PAPER_LINK_PROMOTION.allowed_evidence_sources:
        return source
    if source in {"official_site", "official_publication_list"}:
        return "official_publication_page"
    if source.startswith("official_linked_") or source in {"orcid", "google_scholar"}:
        return "official_external_profile"
    if source in {"openalex", "semantic_scholar", "crossref", "dblp", "arxiv"}:
        return "academic_api_with_affiliation_match"
    return "academic_api_with_affiliation_match"


def _paper_evidence_page_id(
    conn: Connection,
    *,
    professor_id: str,
    staging_record: Any,
    evidence_source_type: str,
    run_id: UUID | str,
) -> UUID | None:
    if evidence_source_type == "academic_api_with_affiliation_match":
        return None
    source_url = _clean_text(_get_attr(staging_record, "source_url"))
    if not source_url:
        return None
    return upsert_source_page_for_url(
        conn,
        url=source_url,
        page_role=evidence_source_type,
        owner_scope_kind="professor",
        owner_scope_ref=professor_id,
        is_official_source=evidence_source_type
        in {"official_publication_page", "official_external_profile"},
        run_id=run_id,
    )


def _promote_link_status(record: Any, evidence_source_type: str) -> str:
    try:
        author_score = float(
            _get_attr(record, "disambiguation_confidence", 0.85) or 0.85
        )
        topic_score = _as_float(_get_attr(record, "topic_consistency_score"))
        institution_score = _as_float(
            _get_attr(record, "institution_consistency_score")
        )
        if (
            evidence_source_type
            not in PROFESSOR_PAPER_LINK_PROMOTION.allowed_evidence_sources
        ):
            return "candidate"
        if author_score < PROFESSOR_PAPER_LINK_PROMOTION.min_author_name_score:
            return "candidate"
        if _has_institution_conflict(record):
            return "candidate"
        if evidence_source_type == "academic_api_with_affiliation_match":
            if institution_score is None:
                return "candidate"
            if (
                institution_score
                < PROFESSOR_PAPER_LINK_PROMOTION.min_institution_score_for_api_only
            ):
                return "candidate"
            if topic_score is None:
                return "candidate"
            if (
                topic_score
                < PROFESSOR_PAPER_LINK_PROMOTION.min_topic_score_or_none_if_official
            ):
                return "candidate"
        return "verified"
    except Exception:
        return "candidate"


def _has_institution_conflict(record: Any) -> bool:
    for attr in ("institution_conflict", "has_institution_conflict"):
        value = _get_attr(record, attr)
        if isinstance(value, bool):
            return value
    return False


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _decimal_score(value: object, default: Decimal | None = None) -> Decimal | None:
    float_value = _as_float(value)
    if float_value is None:
        return default
    bounded = min(max(float_value, 0.0), 1.0)
    return Decimal(f"{bounded:.2f}")


def _link_match_reason(*, evidence_source_type: str, link_status: str) -> str:
    if link_status == "verified":
        return f"Auto-verified from {evidence_source_type} using threshold_config promotion rules."
    return f"Candidate from {evidence_source_type}; auto-verification requirements were not fully met."
