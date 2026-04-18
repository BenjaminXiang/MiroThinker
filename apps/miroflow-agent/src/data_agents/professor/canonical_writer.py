from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID

from psycopg import Connection

from src.data_agents.paper.canonical_writer import upsert_paper
from src.data_agents.paper.title_cleaner import clean_paper_title
from src.data_agents.quality.threshold_config import (
    PROFESSOR_PAPER_LINK_PROMOTION,
)

from .name_identity_gate import NameIdentityCandidate, NameIdentityDecision
from .publish_helpers import build_professor_id, is_official_url

if TYPE_CHECKING:
    from src.data_agents.professor.cross_domain import PaperStagingRecord
    from src.data_agents.professor.models import EnrichedProfessorProfile


logger = logging.getLogger(__name__)

OFFICIAL_FACT_CONFIDENCE = Decimal("0.85")
NON_OFFICIAL_FACT_CONFIDENCE = Decimal("0.70")

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
) -> ProfessorCanonicalReport:
    """Upsert a professor bundle into canonical Postgres tables."""

    professor_name = _clean_text(getattr(enriched, "name", None))
    if not professor_name:
        raise ValueError("enriched.name must be non-empty")

    professor_id = build_professor_id(enriched)
    primary_page_id = official_profile_page_id or _resolve_primary_profile_page_id(
        conn,
        enriched=enriched,
        professor_id=professor_id,
    )
    if primary_page_id is None:
        raise ValueError(
            "write_professor_bundle requires an official_profile_page_id or at least one evidence URL"
        )

    is_new_professor = _upsert_professor_row(
        conn,
        professor_id=professor_id,
        enriched=enriched,
        primary_page_id=primary_page_id,
        name_identity_gate=name_identity_gate,
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
        )
        affiliation_count += 1

    facts_written = 0
    for direction in _dedupe_strings(
        _iter_list(getattr(enriched, "research_directions", None))
    ):
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="research_topic",
            value_raw=direction,
            source_page_id=primary_page_id,
            evidence_span=_fact_evidence_span(enriched, direction),
            confidence=_fact_confidence_for_url(_primary_evidence_url(enriched)),
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
        )
        facts_written += 1

    email = _clean_text(getattr(enriched, "email", None))
    if email:
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="contact",
            value_raw=email,
            source_page_id=primary_page_id,
            evidence_span=_fact_evidence_span(enriched, email),
            confidence=_fact_confidence_for_url(_primary_evidence_url(enriched)),
        )
        facts_written += 1

    homepage_url = _clean_text(getattr(enriched, "homepage", None))
    if homepage_url:
        homepage_page_id = upsert_source_page_for_url(
            conn,
            url=homepage_url,
            page_role="personal_homepage",
            owner_scope_kind="professor",
            owner_scope_ref=professor_id,
            is_official_source=is_official_url(homepage_url),
        )
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="homepage",
            value_raw=homepage_url,
            source_page_id=homepage_page_id,
            evidence_span=_fact_evidence_span(enriched, homepage_url),
            confidence=_fact_confidence_for_url(homepage_url),
        )
        facts_written += 1

    for external_url in _dedupe_strings(
        _iter_list(getattr(enriched, "scholarly_profile_urls", None))
    ):
        external_page_id = upsert_source_page_for_url(
            conn,
            url=external_url,
            page_role="official_external_profile",
            owner_scope_kind="professor",
            owner_scope_ref=professor_id,
            is_official_source=True,
        )
        _upsert_fact(
            conn,
            professor_id=professor_id,
            fact_type="external_profile",
            value_raw=external_url,
            source_page_id=external_page_id,
            evidence_span=_fact_evidence_span(enriched, external_url),
            confidence=_fact_confidence_for_url(external_url),
        )
        facts_written += 1

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
        )
        written_paper_ids.add(paper_report.paper_id)

        link_status = _promote_link_status(staging_record, evidence_source_type)
        evidence_page_id = _paper_evidence_page_id(
            conn,
            professor_id=professor_id,
            staging_record=staging_record,
            evidence_source_type=evidence_source_type,
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
        )
        link_key = (professor_id, paper_report.paper_id)
        written_link_keys.add(link_key)
        if link_status == "verified":
            verified_link_keys.add(link_key)

    return ProfessorCanonicalReport(
        professor_id=professor_id,
        is_new_professor=is_new_professor,
        affiliations_written=affiliation_count,
        facts_written=facts_written,
        papers_written=len(written_paper_ids),
        professor_paper_links_written=len(written_link_keys),
        professor_paper_links_verified=len(verified_link_keys),
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
) -> UUID:
    """Upsert a source_page row keyed by URL and return its page id."""

    normalized_url = _clean_text(url)
    if not normalized_url:
        raise ValueError("url must be non-empty")
    effective_fetched_at = fetched_at or datetime.now(timezone.utc)
    row = conn.execute(
        """
        INSERT INTO source_page (
            url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            fetched_at,
            is_official_source
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (url) DO UPDATE
           SET page_role          = EXCLUDED.page_role,
               owner_scope_kind   = COALESCE(EXCLUDED.owner_scope_kind, source_page.owner_scope_kind),
               owner_scope_ref    = COALESCE(EXCLUDED.owner_scope_ref, source_page.owner_scope_ref),
               fetched_at         = GREATEST(source_page.fetched_at, EXCLUDED.fetched_at),
               is_official_source = source_page.is_official_source OR EXCLUDED.is_official_source
        RETURNING page_id
        """,
        (
            normalized_url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            effective_fetched_at,
            is_official_source,
        ),
    ).fetchone()
    assert row is not None
    return row[0]


def _resolve_primary_profile_page_id(
    conn: Connection,
    *,
    enriched: EnrichedProfessorProfile,
    professor_id: str,
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
) -> bool:
    is_new = (
        conn.execute(
            "SELECT 1 FROM professor WHERE professor_id = %s",
            (professor_id,),
        ).fetchone()
        is None
    )
    now = datetime.now(timezone.utc)
    canonical_name = _clean_text(getattr(enriched, "name", None))
    candidate_name_en = _clean_text(getattr(enriched, "name_en", None))
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
            first_seen_at,
            last_refreshed_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (professor_id) DO UPDATE
           SET canonical_name                    = EXCLUDED.canonical_name,
               canonical_name_en                 = EXCLUDED.canonical_name_en,
               discipline_family                 = EXCLUDED.discipline_family,
               primary_official_profile_page_id  = COALESCE(EXCLUDED.primary_official_profile_page_id, professor.primary_official_profile_page_id),
               last_refreshed_at                 = EXCLUDED.last_refreshed_at,
               updated_at                        = now()
        """,
        (
            professor_id,
            canonical_name,
            candidate_name_en,
            _classify_discipline(enriched),
            primary_page_id,
            now,
            now,
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
) -> None:
    row = conn.execute(
        """
        SELECT affiliation_id
        FROM professor_affiliation
        WHERE professor_id = %s
          AND institution = %s
          AND department IS NOT DISTINCT FROM %s
          AND title IS NOT DISTINCT FROM %s
          AND is_primary = %s
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
            is_primary,
            is_current,
            start_year,
            end_year,
            source_page_id,
        ),
    ).fetchone()
    if row is not None:
        conn.execute(
            """
            UPDATE professor_affiliation
               SET updated_at = now()
             WHERE affiliation_id = %s
            """,
            (row[0],),
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
            source_page_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        ),
    )


def _upsert_fact(
    conn: Connection,
    *,
    professor_id: str,
    fact_type: str,
    value_raw: str,
    source_page_id: UUID,
    evidence_span: str,
    confidence: Decimal,
) -> None:
    row = conn.execute(
        """
        SELECT fact_id
        FROM professor_fact
        WHERE professor_id = %s
          AND fact_type = %s
          AND value_raw = %s
          AND source_page_id = %s
        LIMIT 1
        """,
        (
            professor_id,
            fact_type,
            value_raw,
            source_page_id,
        ),
    ).fetchone()
    if row is not None:
        conn.execute(
            """
            UPDATE professor_fact
               SET evidence_span = %s,
                   confidence = %s,
                   updated_at = now()
             WHERE fact_id = %s
            """,
            (
                evidence_span,
                confidence,
                row[0],
            ),
        )
        return

    conn.execute(
        """
        INSERT INTO professor_fact (
            professor_id,
            fact_type,
            value_raw,
            source_page_id,
            evidence_span,
            confidence
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            professor_id,
            fact_type,
            value_raw,
            source_page_id,
            evidence_span,
            confidence,
        ),
    )


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
) -> None:
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
            verified_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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


def _iter_list(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _get_attr(obj: object, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


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
    if source in {"openalex", "semantic_scholar", "crossref"}:
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
