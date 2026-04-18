# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Professor Enrichment Pipeline v3 — Three-Layer Collection + Cross-Domain Linking.

Stage sequence:
1. Roster Discovery (existing)
2. Regex Extract (existing)
3. Direction Cleaning (direction_cleaner.py)
4. Homepage Crawl (homepage_crawler.py)
5. Paper Collection (existing paper_collector)
6. Agent Enrichment (existing agent_enrichment)
7. Web Search + Identity Verification (web_search_enrichment.py)
8. Company Linking (company_linker.py + cross_domain_linker.py)
9. LLM Summary Generation (LLM-only, no fallback padding)
10. Quality Gate + Release
11. Cross-Domain Bidirectional Writes
12. Vectorization (existing)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data_agents.contracts import quality_status_compatibility_rows
from src.data_agents.publish import publish_jsonl

from .company_linker import verify_company_link
from .completeness import assess_completeness
from .cross_domain import CompanyLink, PaperStagingRecord
from .cross_domain_linker import find_company_by_name, write_bidirectional_link
from .direction_cleaner import clean_directions
from .enrichment import build_profile_record, normalize_text
from .homepage_crawler import _sanitize_title, crawl_homepage
from .models import EnrichedProfessorProfile, MergedProfessorProfileRecord
from .paper_publication import build_paper_domain_publication
from .pipeline import run_professor_pipeline
from .publish_helpers import (
    build_professor_id as build_published_professor_id,
    build_professor_record_from_enriched,
)
from .quality_gate import QualityResult, build_quality_report, evaluate_quality
from .web_search_enrichment import CompanyMention, search_and_enrich
from .llm_profiles import resolve_professor_llm_settings

logger = logging.getLogger(__name__)
_DEFAULT_LLM_TIMEOUT_SECONDS = 60.0


@dataclass
class PipelineV3Config:
    seed_doc: Path
    output_dir: Path
    # LLM
    local_llm_base_url: str = ""
    local_llm_model: str = ""
    local_llm_api_key: str = ""
    online_llm_base_url: str = ""
    online_llm_model: str = ""
    online_llm_api_key: str = ""
    # Embedding
    embedding_base_url: str = "http://100.64.0.27:18005/v1"
    embedding_api_key: str = ""
    # Milvus
    milvus_uri: str = ""
    # Web search
    serper_api_key: str = ""
    # Concurrency
    max_concurrent: int = 8  # Max professors processed concurrently
    embedding_batch_size: int = 50
    # Timeouts
    crawl_timeout: float = 30.0
    agent_timeout: float = 300.0
    # Domain
    official_domain_suffixes: tuple[str, ...] = ("sustech.edu.cn",)
    # Limits
    limit: int | None = None
    institution_filter: str | None = None
    # V3 specific
    identity_confidence_threshold: float = 0.8
    skip_web_search: bool = False
    skip_vectorize: bool = False
    # Store
    store_db_path: str | None = None

    def __post_init__(self) -> None:
        if (
            self.local_llm_base_url
            and self.local_llm_model
            and self.local_llm_api_key is not None
            and self.online_llm_base_url
            and self.online_llm_model
            and self.online_llm_api_key is not None
        ):
            return

        defaults = resolve_professor_llm_settings(
            default_profile="gemma4",
            strict=False,
        )
        if not self.local_llm_base_url:
            self.local_llm_base_url = defaults["local_llm_base_url"]
        if not self.local_llm_model:
            self.local_llm_model = defaults["local_llm_model"]
        if not self.local_llm_api_key:
            self.local_llm_api_key = defaults["local_llm_api_key"]
        if not self.online_llm_base_url:
            self.online_llm_base_url = defaults["online_llm_base_url"]
        if not self.online_llm_model:
            self.online_llm_model = defaults["online_llm_model"]
        if not self.online_llm_api_key:
            self.online_llm_api_key = defaults["online_llm_api_key"]


@dataclass
class PipelineV3Report:
    # Stage 1 (from V2)
    seed_count: int = 0
    discovered_count: int = 0
    unique_count: int = 0
    # Stage 2a
    regex_structured_count: int = 0
    regex_partial_count: int = 0
    # Stage 2.1 — Direction Cleaning
    direction_cleaned_count: int = 0
    # Stage 3 — Homepage Crawl
    homepage_crawled_count: int = 0
    homepage_fields_filled: int = 0
    # Stage 2b (papers)
    paper_enriched_count: int = 0
    papers_collected_total: int = 0
    paper_staging_count: int = 0
    paper_observation_count: int = 0
    paper_school_hit_count: int = 0
    paper_fallback_count: int = 0
    paper_name_disambiguation_conflict_count: int = 0
    paper_source_breakdown: dict[str, int] = field(default_factory=dict)
    # Stage 2c (agent)
    agent_triggered_count: int = 0
    agent_local_success_count: int = 0
    agent_online_escalation_count: int = 0
    agent_failed_count: int = 0
    # Stage 5 — Web Search
    web_search_count: int = 0
    identity_verified_count: int = 0
    # Stage 6 — Company Linking
    company_links_confirmed: int = 0
    # Stage 7 — Summary
    summary_generated_count: int = 0
    summary_fallback_count: int = 0
    # Stage 8 — Release
    l1_blocked_count: int = 0
    released_count: int = 0
    quality_distribution: dict[str, int] = field(default_factory=dict)
    vectorized_count: int = 0
    alerts: list[str] = field(default_factory=list)


@dataclass
class PipelineV3Result:
    report: PipelineV3Report
    output_files: dict[str, Path]


def _log(msg: str) -> None:
    logger.info(msg)
    print(f"[V3] {msg}")


def _clear_proxy_env() -> None:
    """Clear proxy env vars that interfere with local LLM calls."""
    for key in ("all_proxy", "ALL_PROXY", "http_proxy", "HTTP_PROXY",
                "https_proxy", "HTTPS_PROXY"):
        os.environ.pop(key, None)


def _build_llm_client(base_url: str, api_key: str) -> Any:
    """Build OpenAI-compatible LLM client."""
    _clear_proxy_env()
    from openai import OpenAI
    return OpenAI(
        base_url=base_url,
        api_key=api_key or "EMPTY",
        timeout=_DEFAULT_LLM_TIMEOUT_SECONDS,
    )


def _build_fallback_llm_client(
    *,
    primary_client: Any,
    primary_model: str,
    backup_client: Any | None,
    backup_model: str | None,
) -> Any:
    """Wrap an OpenAI-compatible client and fall back to backup on request failure."""
    if backup_client is None or not backup_model:
        return primary_client

    class _FallbackCompletions:
        def create(self, **kwargs):
            try:
                return primary_client.chat.completions.create(**kwargs)
            except Exception as primary_error:
                fallback_kwargs = dict(kwargs)
                fallback_kwargs["model"] = backup_model
                logger.warning(
                    "Primary LLM call failed for model %s; falling back to %s: %s",
                    kwargs.get("model") or primary_model,
                    backup_model,
                    primary_error,
                )
                return backup_client.chat.completions.create(**fallback_kwargs)

    class _FallbackChat:
        completions = _FallbackCompletions()

    return type("FallbackLLMClient", (), {"chat": _FallbackChat()})()


def _merged_to_enriched(
    record: MergedProfessorProfileRecord,
) -> EnrichedProfessorProfile:
    """Convert v1 MergedProfessorProfileRecord to EnrichedProfessorProfile."""
    return EnrichedProfessorProfile(
        name=record.name or "",
        institution=record.institution or "",
        department=record.department,
        title=_sanitize_title(record.title),
        email=record.email,
        homepage=record.homepage,
        office=record.office,
        research_directions=list(record.research_directions),
        research_directions_source="official_only",
        profile_url=record.profile_url,
        roster_source=record.roster_source,
        extraction_status=record.extraction_status,
        enrichment_source="regex_only",
        evidence_urls=list(record.evidence),
    )


def _build_professor_id(profile: EnrichedProfessorProfile) -> str:
    return build_published_professor_id(profile)


def _load_completed_ids(path: Path) -> set[str]:
    """Load profile URLs from existing JSONL for resume."""
    completed: set[str] = set()
    if not path.exists():
        return completed
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                url = data.get("profile_url", "")
                if url:
                    completed.add(url)
            except json.JSONDecodeError:
                continue
    return completed


def _append_jsonl(path: Path, obj: Any) -> None:
    """Append a Pydantic model or dict to JSONL."""
    with path.open("a", encoding="utf-8") as f:
        if hasattr(obj, "model_dump"):
            data = obj.model_dump(mode="json")
        elif hasattr(obj, "to_dict"):
            data = obj.to_dict()
        else:
            data = obj
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def _load_enriched_profiles(path: Path) -> list[EnrichedProfessorProfile]:
    """Load all enriched profiles from JSONL."""
    if not path.exists():
        return []
    profiles = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                profiles.append(EnrichedProfessorProfile(**data))
            except Exception:
                continue
    return profiles


def _load_paper_staging_records(path: Path) -> list[PaperStagingRecord]:
    """Load all paper staging records from JSONL."""
    if not path.exists():
        return []
    records: list[PaperStagingRecord] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                records.append(PaperStagingRecord(**data))
            except Exception:
                continue
    return records


def _profile_has_paper_signal(profile: EnrichedProfessorProfile) -> bool:
    return bool(
        profile.paper_count
        or profile.top_papers
        or profile.h_index
        or profile.citation_count
    )


def _paper_input_signature(profile: EnrichedProfessorProfile) -> tuple[object, ...]:
    return (
        profile.official_paper_count,
        tuple(url.strip() for url in profile.publication_evidence_urls),
        tuple(url.strip() for url in profile.scholarly_profile_urls),
        tuple(url.strip() for url in profile.cv_urls),
        tuple(paper.title for paper in profile.official_top_papers),
    )


def _should_retry_paper_collection_after_web_search(
    *,
    before_search: EnrichedProfessorProfile,
    after_search: EnrichedProfessorProfile,
) -> bool:
    if _profile_has_paper_signal(after_search):
        return False
    return _paper_input_signature(after_search) != _paper_input_signature(before_search)


async def _process_single_professor_v3(
    *,
    record: MergedProfessorProfileRecord,
    config: PipelineV3Config,
    local_client: Any,
    online_client: Any | None,
    search_provider: Any | None,
    semaphore: asyncio.Semaphore,
    report: PipelineV3Report,
) -> tuple[EnrichedProfessorProfile, list[PaperStagingRecord], list[CompanyMention]]:
    """Process a single professor through all V3 stages."""
    async with semaphore:
        resilient_client = _build_fallback_llm_client(
            primary_client=local_client,
            primary_model=config.local_llm_model,
            backup_client=online_client,
            backup_model=config.online_llm_model,
        )
        # Stage 2a: Convert to enriched profile
        profile = _merged_to_enriched(record)
        staging_records: list[PaperStagingRecord] = []
        company_mentions: list[CompanyMention] = []

        # Stage 2.1: Direction Cleaning
        if profile.research_directions:
            cleaned = clean_directions(profile.research_directions)
            if cleaned != profile.research_directions:
                profile = profile.model_copy(update={"research_directions": cleaned})
                report.direction_cleaned_count += 1

        # Stage 3: Homepage Crawl
        from .discovery import fetch_html_with_fallback

        def fetch_html(url: str, timeout: float = 20.0):
            return fetch_html_with_fallback(url, timeout=timeout)

        try:
            homepage_result = await crawl_homepage(
                profile=profile,
                fetch_html_fn=fetch_html,
                llm_client=resilient_client,
                llm_model=config.local_llm_model,
                timeout=config.crawl_timeout,
            )
            if homepage_result.success:
                profile = homepage_result.profile
                report.homepage_crawled_count += 1
                report.homepage_fields_filled += homepage_result.pages_fetched
        except Exception as e:
            logger.warning("Homepage crawl failed for %s: %s", profile.name, e)

        # Stage 2b: Paper Collection
        from .paper_collector import enrich_from_papers
        from src.data_agents.paper.author_id_picker import pick_author_id

        def fetch_html_str(url: str, timeout: float) -> str:
            result = fetch_html_with_fallback(url, timeout=timeout)
            if result.html is not None:
                return result.html
            raise RuntimeError(f"unable to fetch html from {url}")

        def author_picker(*, target_name, target_institution, target_directions, candidates):
            return pick_author_id(
                target_name=target_name,
                target_institution=target_institution,
                target_directions=target_directions,
                candidates=candidates,
                llm_client=resilient_client,
                llm_model=config.local_llm_model,
            )

        async def run_paper_collection(current_profile: EnrichedProfessorProfile) -> tuple[EnrichedProfessorProfile, list[PaperStagingRecord]]:
            prof_id = _build_professor_id(current_profile)
            paper_result = await enrich_from_papers(
                name=current_profile.name,
                name_en=current_profile.name_en,
                institution=current_profile.institution,
                institution_en=None,
                official_directions=current_profile.research_directions,
                official_paper_count=current_profile.official_paper_count,
                official_top_papers=current_profile.official_top_papers,
                official_anchor_profile=current_profile.official_anchor_profile,
                publication_evidence_urls=current_profile.publication_evidence_urls,
                scholarly_profile_urls=current_profile.scholarly_profile_urls,
                cv_urls=current_profile.cv_urls,
                professor_id=prof_id,
                homepage_url=current_profile.profile_url or current_profile.homepage,
                fetch_html=fetch_html_str,
                llm_client=resilient_client,
                llm_model=config.local_llm_model,
                timeout=config.crawl_timeout,
                author_picker=author_picker,
            )

            updated_profile = current_profile.model_copy(update={
                "research_directions": paper_result.research_directions,
                "research_directions_source": paper_result.research_directions_source,
                "h_index": paper_result.h_index,
                "citation_count": paper_result.citation_count,
                "paper_count": paper_result.paper_count,
                "top_papers": paper_result.top_papers,
                "enrichment_source": "paper_enriched",
            })
            report.papers_collected_total += len(paper_result.staging_records)
            report.paper_observation_count += 1
            if paper_result.school_matched:
                report.paper_school_hit_count += 1
            if paper_result.fallback_used:
                report.paper_fallback_count += 1
            if paper_result.name_disambiguation_conflict:
                report.paper_name_disambiguation_conflict_count += 1
            if paper_result.paper_source:
                report.paper_source_breakdown[paper_result.paper_source] = (
                    report.paper_source_breakdown.get(paper_result.paper_source, 0) + 1
                )
            return updated_profile, paper_result.staging_records

        try:
            profile, staging_records = await run_paper_collection(profile)
        except Exception as e:
            logger.warning("Paper collection failed for %s: %s", profile.name, e)

        # Stage 2c: Agent Enrichment
        assessment = assess_completeness(profile)
        if assessment.should_trigger_agent:
            report.agent_triggered_count += 1
            try:
                from .agent_enrichment import run_agent_enrichment

                # Fetch profile HTML for agent
                profile_html = ""
                try:
                    html_result = fetch_html_with_fallback(profile.profile_url, timeout=config.crawl_timeout)
                    if html_result.html:
                        profile_html = html_result.html
                except Exception:
                    pass

                agent_result = await run_agent_enrichment(
                    profile=profile,
                    missing_fields=assessment.missing_fields,
                    html_text=profile_html,
                    local_llm_client=local_client,
                    local_llm_model=config.local_llm_model,
                    online_llm_client=online_client,
                    online_llm_model=config.online_llm_model,
                    timeout=config.agent_timeout,
                )
                profile = agent_result.profile
                if agent_result.enrichment_source == "agent_online":
                    report.agent_online_escalation_count += 1
                elif agent_result.enrichment_source == "agent_failed":
                    report.agent_failed_count += 1
                else:
                    report.agent_local_success_count += 1
            except Exception as e:
                logger.warning("Agent enrichment failed for %s: %s", profile.name, e)
                report.agent_failed_count += 1

        # Stage 5: Web Search + Identity Verification
        if not config.skip_web_search and search_provider is not None:
            try:
                before_web_search_profile = profile
                web_result = await search_and_enrich(
                    profile=profile,
                    search_provider=search_provider,
                    fetch_html_fn=fetch_html,
                    llm_client=resilient_client,
                    llm_model=config.local_llm_model,
                )
                report.web_search_count += 1
                report.identity_verified_count += web_result.pages_verified
                profile = web_result.profile
                company_mentions.extend(web_result.company_mentions)
                if _should_retry_paper_collection_after_web_search(
                    before_search=before_web_search_profile,
                    after_search=profile,
                ):
                    profile, staging_records = await run_paper_collection(profile)
            except Exception as e:
                logger.warning("Web search failed for %s: %s", profile.name, e)

        # Stage 6: Company Link Verification
        for mention in company_mentions:
            try:
                link_result = await verify_company_link(
                    professor=profile,
                    company_mention=mention,
                    llm_client=resilient_client,
                    llm_model=config.local_llm_model,
                    evidence_text=mention.evidence_text,
                )
                if link_result is not None:
                    # Append to profile's company_roles
                    roles = list(profile.company_roles)
                    existing_names = {r.company_name for r in roles}
                    if link_result.company_link.company_name not in existing_names:
                        roles.append(link_result.company_link)
                        profile = profile.model_copy(update={"company_roles": roles})
                        report.company_links_confirmed += 1
            except Exception as e:
                logger.warning(
                    "Company link verification failed for %s → %s: %s",
                    profile.name, mention.company_name, e,
                )

        # Stage 7: LLM Summary (LLM-only, no fallback padding)
        needs_profile_summary = not profile.profile_summary or len(profile.profile_summary) < 200
        needs_evaluation_summary = not profile.evaluation_summary
        if needs_profile_summary or needs_evaluation_summary:
            try:
                from .summary_generator import generate_summaries
                summaries = await generate_summaries(
                    profile=profile,
                    llm_client=resilient_client,
                    llm_model=config.local_llm_model,
                )
                profile = profile.model_copy(update={
                    "profile_summary": (
                        summaries.profile_summary if needs_profile_summary else profile.profile_summary
                    ),
                    "evaluation_summary": (
                        summaries.evaluation_summary
                        if needs_evaluation_summary
                        else profile.evaluation_summary
                    ),
                })
                report.summary_generated_count += 1
            except Exception:
                # LLM failed — leave empty, quality gate marks as needs_review
                profile = profile.model_copy(update={
                    "profile_summary": "" if needs_profile_summary else profile.profile_summary,
                    "evaluation_summary": "" if needs_evaluation_summary else profile.evaluation_summary,
                })
                report.summary_fallback_count += 1

        return profile, staging_records, company_mentions


async def run_professor_pipeline_v3(
    config: PipelineV3Config,
) -> PipelineV3Result:
    """Run the full V3 professor enrichment pipeline."""
    _clear_proxy_env()
    report = PipelineV3Report()
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    enriched_path = output_dir / "enriched_v3.jsonl"
    paper_staging_path = output_dir / "paper_staging.jsonl"
    quality_report_path = output_dir / "quality_report.json"
    failed_tasks_path = output_dir / "failed_tasks.jsonl"

    # --- Stage 1: Roster Discovery ---
    _log("Stage 1: Roster Discovery")
    v1_result = run_professor_pipeline(
        config.seed_doc,
        timeout=config.crawl_timeout,
        official_domain_suffixes=config.official_domain_suffixes,
        max_profile_fetch=config.limit,
    )

    report.seed_count = v1_result.report.seed_url_count
    report.discovered_count = v1_result.report.discovered_professor_count
    report.unique_count = v1_result.report.unique_professor_count
    report.regex_structured_count = v1_result.report.structured_profile_count
    report.regex_partial_count = v1_result.report.partial_profile_count

    profiles = v1_result.profiles
    if config.institution_filter:
        profiles = [p for p in profiles if config.institution_filter in (p.institution or "")]
    if config.limit:
        profiles = profiles[: config.limit]

    _log(f"Stage 1 done: {report.unique_count} unique professors, processing {len(profiles)}")

    # --- Resume checkpoint ---
    completed_urls = _load_completed_ids(enriched_path)
    if completed_urls:
        _log(f"Resuming: {len(completed_urls)} professors already processed")

    # --- Build clients ---
    local_client = _build_llm_client(config.local_llm_base_url, config.local_llm_api_key)
    online_client = (
        _build_llm_client(config.online_llm_base_url, config.online_llm_api_key)
        if config.online_llm_api_key
        else None
    )

    # Build search provider
    search_provider = None
    if config.serper_api_key and not config.skip_web_search:
        from src.data_agents.providers.web_search import WebSearchProvider
        search_provider = WebSearchProvider(api_key=config.serper_api_key)

    # --- Stage 2-6: Per-Professor Processing ---
    _log("Stage 2-6: Per-Professor Processing")
    semaphore = asyncio.Semaphore(config.max_concurrent)
    enriched_profiles: list[EnrichedProfessorProfile] = []
    all_staging_records: list[PaperStagingRecord] = []
    failed_tasks: list[dict] = []

    tasks = []
    for record in profiles:
        if record.profile_url in completed_urls:
            continue
        tasks.append(
            _process_single_professor_v3(
                record=record,
                config=config,
                local_client=local_client,
                online_client=online_client,
                search_provider=search_provider,
                semaphore=semaphore,
                report=report,
            )
        )

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                _log(f"Professor failed: {result}")
                report.agent_failed_count += 1
                failed_tasks.append({
                    "error": str(result),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue
            enriched, staging, _company_mentions = result
            enriched_profiles.append(enriched)
            all_staging_records.extend(staging)

            _append_jsonl(enriched_path, enriched)
            for s in staging:
                _append_jsonl(paper_staging_path, s)

    # Load all enriched profiles and paper staging records (including previously processed)
    all_enriched = _load_enriched_profiles(enriched_path)
    all_staging_records = _load_paper_staging_records(paper_staging_path)
    report.paper_enriched_count = sum(
        1 for p in all_enriched if p.enrichment_source != "regex_only"
    )
    report.paper_staging_count = len(all_staging_records)

    _log(
        f"Stage 2-6 done: {len(enriched_profiles)} enriched, "
        f"{report.homepage_crawled_count} homepages crawled, "
        f"{report.web_search_count} web searched, "
        f"{report.company_links_confirmed} company links"
    )

    # --- Stage 8: Quality Gate + Release ---
    _log("Stage 8: Quality Gate + Release")
    quality_results: list[tuple[EnrichedProfessorProfile, QualityResult]] = []
    released_profiles: list[tuple[str, EnrichedProfessorProfile, str]] = []

    for profile in all_enriched:
        qr = evaluate_quality(profile)
        quality_results.append((profile, qr))
        if qr.passed_l1:
            prof_id = _build_professor_id(profile)
            released_profiles.append((prof_id, profile, qr.quality_status))
            report.released_count += 1
        else:
            report.l1_blocked_count += 1

    qreport = build_quality_report(quality_results)
    report.quality_distribution = {
        "ready": qreport.ready_count,
        "needs_review": qreport.needs_review_count,
        "low_confidence": qreport.low_confidence_count,
        "needs_enrichment": qreport.needs_enrichment_count,
    }
    report.alerts = qreport.alerts

    quality_report_path.write_text(
        json.dumps({
            "total": qreport.total_count,
            "released": qreport.released_count,
            "blocked": qreport.blocked_count,
            "quality_distribution": report.quality_distribution,
            "quality_distribution_legacy": qreport.legacy_breakdown,
            "quality_status_compatibility": quality_status_compatibility_rows(),
            "alerts": report.alerts,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- Stage 9: Cross-Domain Bidirectional Writes ---
    # Use verified company_roles from enriched profiles, NOT raw unverified mentions.
    if config.store_db_path:
        _log("Stage 9: Cross-Domain Writes")
        from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore
        store = SqliteReleasedObjectStore(config.store_db_path)
        publishable_ids: set[str] = set()
        released_objects = []

        for prof_id, profile, quality_status in released_profiles:
            record = build_professor_record_from_enriched(
                profile,
                datetime.now(timezone.utc),
                quality_status=quality_status,
            )
            if record is None:
                continue
            publishable_ids.add(prof_id)
            released_objects.append(record.to_released_object())

        if released_objects:
            store.upsert_released_objects(released_objects)

        published_staging_records = [
            record
            for record in all_staging_records
            if record.anchoring_professor_id in publishable_ids
        ]
        if published_staging_records:
            paper_publication = build_paper_domain_publication(
                staging_records=published_staging_records,
                now=datetime.now(timezone.utc),
            )
            paper_side_objects = [
                *paper_publication.paper_released_objects,
                *paper_publication.link_released_objects,
            ]
            if paper_side_objects:
                store.upsert_released_objects(paper_side_objects)

        filtered_count = len(released_profiles) - len(released_objects)
        if filtered_count > 0:
            report.alerts.append(f"publication_filtered_count:{filtered_count}")

        for profile in all_enriched:
            if not profile.company_roles:
                continue
            prof_id = _build_professor_id(profile)
            if prof_id not in publishable_ids:
                continue
            for link in profile.company_roles:
                # Resolve company_id from store if not already set
                if not link.company_id:
                    company_obj = find_company_by_name(store, link.company_name)
                    if company_obj:
                        link = CompanyLink(
                            company_id=company_obj.id,
                            company_name=link.company_name,
                            role=link.role,
                            evidence_url=link.evidence_url,
                            source=link.source,
                        )
                try:
                    write_bidirectional_link(store, prof_id, link)
                except Exception as e:
                    logger.warning("Cross-domain write failed: %s", e)

    # --- Stage 10: Vectorization ---
    if not config.skip_vectorize and config.embedding_base_url and released_profiles:
        _log("Stage 10: Vectorization")
        try:
            from .vectorizer import EmbeddingClient, ProfessorVectorizer

            milvus_uri = config.milvus_uri or str(output_dir / "milvus.db")
            embedding_client = EmbeddingClient(
                base_url=config.embedding_base_url,
                api_key=config.embedding_api_key,
            )
            vectorizer = ProfessorVectorizer(
                embedding_client=embedding_client,
                milvus_uri=milvus_uri,
            )
            vectorizer.ensure_collection()

            for i in range(0, len(released_profiles), config.embedding_batch_size):
                batch = released_profiles[i : i + config.embedding_batch_size]
                count = vectorizer.vectorize_and_upsert(batch)
                report.vectorized_count += count
        except Exception as e:
            _log(f"Vectorization failed: {e}")
            report.alerts.append(f"vectorization_failed: {e}")

    # Write failed tasks
    if failed_tasks:
        with failed_tasks_path.open("w", encoding="utf-8") as f:
            for task in failed_tasks:
                f.write(json.dumps(task, ensure_ascii=False) + "\n")

    _log(
        f"Pipeline V3 complete: {report.released_count} released, "
        f"{report.l1_blocked_count} blocked, "
        f"{report.vectorized_count} vectorized"
    )

    return PipelineV3Result(
        report=report,
        output_files={
            "enriched": enriched_path,
            "paper_staging": paper_staging_path,
            "quality_report": quality_report_path,
        },
    )
