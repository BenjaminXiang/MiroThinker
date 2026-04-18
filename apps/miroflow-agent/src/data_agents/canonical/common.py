"""Shared enums and small types reused across domain contracts.

Values here MUST match the CHECK constraints in the alembic migrations.
The single source of truth is the migration file; this module mirrors it
so application code has Python-side type safety.
"""

from __future__ import annotations

from enum import Enum


class SeedKind(str, Enum):
    company_xlsx = "company_xlsx"
    patent_xlsx = "patent_xlsx"
    teacher_roster = "teacher_roster"
    department_hub = "department_hub"
    company_official_site = "company_official_site"
    company_news_feed = "company_news_feed"


class RunKind(str, Enum):
    import_xlsx = "import_xlsx"
    roster_crawl = "roster_crawl"
    profile_enrichment = "profile_enrichment"
    news_refresh = "news_refresh"
    team_resolver = "team_resolver"
    paper_link_resolver = "paper_link_resolver"
    projection_build = "projection_build"
    answer_readiness_eval = "answer_readiness_eval"
    quality_scan = "quality_scan"


class RunStatus(str, Enum):
    running = "running"
    succeeded = "succeeded"
    partial = "partial"
    failed = "failed"
    reverted = "reverted"  # valid only for import_batch.run_status


class IdentityStatus(str, Enum):
    resolved = "resolved"
    needs_review = "needs_review"
    merged_into = "merged_into"
    inactive = "inactive"


class LinkStatus(str, Enum):
    verified = "verified"
    candidate = "candidate"
    rejected = "rejected"


class QualityStatus(str, Enum):
    """Plan-wide quality tag for canonical entities / projections."""

    ready = "ready"
    needs_review = "needs_review"
    low_confidence = "low_confidence"
    needs_enrichment = "needs_enrichment"


class EvidenceKind(str, Enum):
    """Source kind for `company_fact.source_kind` and similar fields."""

    xlsx = "xlsx"
    official_website = "official_website"
    news = "news"
    llm_from_official = "llm_from_official"
    human_reviewed = "human_reviewed"


class EntityMergeAction(str, Enum):
    merge_entity = "merge_entity"
    split_entity = "split_entity"


class PaperAuthorMatch(str, Enum):
    """Evidence source tier for `professor_paper_link.evidence_source_type`.

    Ordered from strongest to weakest. Promotion rules in
    `data_agents/quality/threshold_config.py` consume this.
    """

    official_publication_page = "official_publication_page"
    personal_homepage = "personal_homepage"
    cv_pdf = "cv_pdf"
    official_external_profile = "official_external_profile"
    academic_api_with_affiliation_match = "academic_api_with_affiliation_match"
