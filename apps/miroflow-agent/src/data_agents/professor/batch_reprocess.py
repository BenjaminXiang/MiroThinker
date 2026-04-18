# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Batch re-processing — re-enrich existing professors through V3 pipeline.

Loads professor records from the SQLite store, converts them to
EnrichedProfessorProfile, and runs V3 enrichment stages (homepage crawl,
papers, agent, web search, company linking, summary, quality gate).
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

from src.data_agents.contracts import ReleasedObject
from src.data_agents.normalization import build_stable_id
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

from .completeness import assess_completeness
from .cross_domain import CompanyLink, PaperStagingRecord
from .direction_cleaner import clean_directions
from .models import EnrichedProfessorProfile
from .web_search_enrichment import CompanyMention
from .llm_profiles import resolve_professor_llm_settings

logger = logging.getLogger(__name__)


@dataclass
class BatchReprocessConfig:
    store_db_path: str
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
    max_concurrent: int = 8
    # Timeouts
    crawl_timeout: float = 30.0
    agent_timeout: float = 300.0
    # Limits
    limit: int | None = None
    institution_filter: str | None = None
    # Flags
    skip_web_search: bool = False
    skip_vectorize: bool = False
    # Stages to run (default: all)
    skip_homepage_crawl: bool = False
    skip_papers: bool = False
    skip_agent_enrichment: bool = False
    skip_summary: bool = False

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


def load_professors_from_store(
    store: SqliteReleasedObjectStore,
    *,
    institution_filter: str | None = None,
    limit: int | None = None,
) -> list[EnrichedProfessorProfile]:
    """Load existing professor records from store and convert to profiles.

    Skips professors without a homepage URL since V3 enrichment
    relies on homepage crawling as the primary data source.
    """
    all_objects = store.list_domain_objects("professor")

    profiles: list[EnrichedProfessorProfile] = []
    for obj in all_objects:
        cf = obj.core_facts or {}
        name = cf.get("name", obj.display_name)
        institution = cf.get("institution", "")

        # Filter by institution
        if institution_filter and institution_filter not in institution:
            continue

        # Get homepage URL from core_facts or evidence
        homepage = cf.get("homepage")
        profile_url = ""
        if obj.evidence:
            for e in obj.evidence:
                if e.source_url:
                    profile_url = e.source_url
                    break

        # Skip professors without any URL
        if not homepage and not profile_url:
            continue

        profile = EnrichedProfessorProfile(
            name=name,
            institution=institution,
            department=cf.get("department"),
            title=cf.get("title"),
            email=cf.get("email"),
            homepage=homepage,
            office=cf.get("office"),
            research_directions=cf.get("research_directions", []),
            research_directions_source="store",
            profile_url=profile_url or homepage or "",
            roster_source="store_reprocess",
            extraction_status="store_loaded",
            enrichment_source="store",
            evidence_urls=[e.source_url for e in obj.evidence if e.source_url],
            education_structured=cf.get("education_structured", []),
            work_experience=cf.get("work_experience", []),
            awards=cf.get("awards", []),
            academic_positions=cf.get("academic_positions", []),
            projects=cf.get("projects", []),
            company_roles=cf.get("company_roles", []),
            h_index=cf.get("h_index"),
            citation_count=cf.get("citation_count"),
            top_papers=cf.get("top_papers", []),
            patent_ids=cf.get("patent_ids", []),
        )
        profiles.append(profile)

        if limit and len(profiles) >= limit:
            break

    return profiles


@dataclass
class BatchReprocessReport:
    total_loaded: int = 0
    processed: int = 0
    direction_cleaned: int = 0
    homepage_crawled: int = 0
    paper_enriched: int = 0
    agent_triggered: int = 0
    agent_success: int = 0
    web_searched: int = 0
    identity_verified: int = 0
    company_links: int = 0
    summary_generated: int = 0
    released: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class BatchReprocessResult:
    report: BatchReprocessReport
    output_dir: Path


def _clear_proxy_env() -> None:
    """Clear proxy env vars so local LLM calls don't route through proxy."""
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY"):
        os.environ.pop(var, None)


def _build_llm_client(base_url: str, api_key: str) -> Any:
    _clear_proxy_env()
    from openai import OpenAI
    return OpenAI(base_url=base_url, api_key=api_key or "EMPTY")


def _build_professor_id(profile: EnrichedProfessorProfile) -> str:
    key_parts = [
        (profile.name or "").strip().lower(),
        (profile.institution or "").strip().lower(),
        (profile.department or "").strip().lower(),
    ]
    return build_stable_id("prof", "|".join(key_parts))


def _log(msg: str) -> None:
    logger.info(msg)
    print(f"[BATCH] {msg}")


async def _reprocess_single(
    *,
    profile: EnrichedProfessorProfile,
    config: BatchReprocessConfig,
    local_client: Any,
    online_client: Any | None,
    search_provider: Any | None,
    semaphore: asyncio.Semaphore,
    report: BatchReprocessReport,
) -> tuple[EnrichedProfessorProfile, list[CompanyMention]]:
    """Re-process a single professor through V3 enrichment stages."""
    async with semaphore:
        company_mentions: list[CompanyMention] = []

        # Stage: Direction Cleaning
        if profile.research_directions:
            cleaned = clean_directions(profile.research_directions)
            if cleaned != profile.research_directions:
                profile = profile.model_copy(update={"research_directions": cleaned})
                report.direction_cleaned += 1

        # Stage: Homepage Crawl
        if not config.skip_homepage_crawl:
            from .discovery import fetch_html_with_fallback
            from .homepage_crawler import crawl_homepage

            def fetch_html(url: str, timeout: float = 20.0):
                return fetch_html_with_fallback(url, timeout=timeout)

            try:
                result = await crawl_homepage(
                    profile=profile,
                    fetch_html_fn=fetch_html,
                    llm_client=local_client,
                    llm_model=config.local_llm_model,
                    timeout=config.crawl_timeout,
                )
                if result.success:
                    profile = result.profile
                    report.homepage_crawled += 1
            except Exception as e:
                logger.warning("Homepage crawl failed for %s: %s", profile.name, e)

        # Stage: Paper Collection
        if not config.skip_papers:
            try:
                from .discovery import fetch_html_with_fallback
                from .paper_collector import enrich_from_papers

                def fetch_html_str(url: str, timeout: float) -> str:
                    r = fetch_html_with_fallback(url, timeout=timeout)
                    if r.html is not None:
                        return r.html
                    raise RuntimeError(f"unable to fetch html from {url}")

                prof_id = _build_professor_id(profile)
                paper_result = await enrich_from_papers(
                    name=profile.name,
                    name_en=profile.name_en,
                    institution=profile.institution,
                    institution_en=None,
                    official_directions=profile.research_directions,
                    official_paper_count=profile.official_paper_count,
                    official_top_papers=profile.official_top_papers,
                    publication_evidence_urls=profile.publication_evidence_urls,
                    scholarly_profile_urls=profile.scholarly_profile_urls,
                    cv_urls=profile.cv_urls,
                    professor_id=prof_id,
                    homepage_url=profile.profile_url or profile.homepage,
                    fetch_html=fetch_html_str,
                    llm_client=local_client,
                    llm_model=config.local_llm_model,
                    timeout=config.crawl_timeout,
                )
                profile = profile.model_copy(update={
                    "research_directions": paper_result.research_directions,
                    "research_directions_source": paper_result.research_directions_source,
                    "h_index": paper_result.h_index,
                    "citation_count": paper_result.citation_count,
                    "paper_count": paper_result.paper_count,
                    "top_papers": paper_result.top_papers,
                    "enrichment_source": "paper_enriched",
                })
                report.paper_enriched += 1
            except Exception as e:
                logger.warning("Paper collection failed for %s: %s", profile.name, e)

        # Stage: Agent Enrichment
        if not config.skip_agent_enrichment:
            assessment = assess_completeness(profile)
            if assessment.should_trigger_agent:
                report.agent_triggered += 1
                try:
                    from .agent_enrichment import run_agent_enrichment
                    from .discovery import fetch_html_with_fallback

                    profile_html = ""
                    try:
                        html_result = fetch_html_with_fallback(
                            profile.profile_url, timeout=config.crawl_timeout
                        )
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
                    if agent_result.enrichment_source != "agent_failed":
                        report.agent_success += 1
                except Exception as e:
                    logger.warning("Agent enrichment failed for %s: %s", profile.name, e)

        # Stage: Web Search
        if not config.skip_web_search and search_provider is not None:
            from .web_search_enrichment import search_and_enrich
            from .discovery import fetch_html_with_fallback

            def fetch_html_ws(url: str, timeout: float = 20.0):
                return fetch_html_with_fallback(url, timeout=timeout)

            try:
                web_result = await search_and_enrich(
                    profile=profile,
                    search_provider=search_provider,
                    fetch_html_fn=fetch_html_ws,
                    llm_client=local_client,
                    llm_model=config.local_llm_model,
                )
                report.web_searched += 1
                report.identity_verified += web_result.pages_verified
                company_mentions.extend(web_result.company_mentions)
            except Exception as e:
                logger.warning("Web search failed for %s: %s", profile.name, e)

        # Stage: Company Linking
        if company_mentions:
            from .company_linker import verify_company_link

            for mention in company_mentions:
                try:
                    link_result = await verify_company_link(
                        professor=profile,
                        company_mention=mention,
                        llm_client=local_client,
                        llm_model=config.local_llm_model,
                    )
                    if link_result is not None:
                        roles = list(profile.company_roles)
                        existing = {r.company_name for r in roles}
                        if link_result.company_link.company_name not in existing:
                            roles.append(link_result.company_link)
                            profile = profile.model_copy(update={"company_roles": roles})
                            report.company_links += 1
                except Exception as e:
                    logger.warning("Company link failed for %s: %s", profile.name, e)

        # Stage: Summary
        if not config.skip_summary:
            needs_profile_summary = not profile.profile_summary or len(profile.profile_summary) < 200
            needs_evaluation_summary = not profile.evaluation_summary
            if needs_profile_summary or needs_evaluation_summary:
                try:
                    from .summary_generator import generate_summaries
                    summaries = await generate_summaries(
                        profile=profile,
                        llm_client=local_client,
                        llm_model=config.local_llm_model,
                    )
                    profile = profile.model_copy(update={
                        "profile_summary": (
                            summaries.profile_summary
                            if needs_profile_summary
                            else profile.profile_summary
                        ),
                        "evaluation_summary": (
                            summaries.evaluation_summary
                            if needs_evaluation_summary
                            else profile.evaluation_summary
                        ),
                    })
                    report.summary_generated += 1
                except Exception:
                    profile = profile.model_copy(update={
                        "profile_summary": "" if needs_profile_summary else profile.profile_summary,
                        "evaluation_summary": "" if needs_evaluation_summary else profile.evaluation_summary,
                    })

        report.processed += 1
        return profile, company_mentions


async def run_batch_reprocess(config: BatchReprocessConfig) -> BatchReprocessResult:
    """Re-process existing professors from the store through V3 enrichment."""
    _clear_proxy_env()
    report = BatchReprocessReport()
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    enriched_path = output_dir / "batch_enriched.jsonl"
    progress_path = output_dir / "batch_progress.json"

    # Load existing professors
    store = SqliteReleasedObjectStore(config.store_db_path)
    profiles = load_professors_from_store(
        store,
        institution_filter=config.institution_filter,
        limit=config.limit,
    )
    report.total_loaded = len(profiles)
    _log(f"Loaded {len(profiles)} professors from store")

    if not profiles:
        _log("No professors to process")
        return BatchReprocessResult(report=report, output_dir=output_dir)

    # Resume: skip already-processed
    completed_urls: set[str] = set()
    if enriched_path.exists():
        with enriched_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    url = data.get("profile_url", "")
                    if url:
                        completed_urls.add(url)
                except json.JSONDecodeError:
                    continue
        if completed_urls:
            _log(f"Resuming: {len(completed_urls)} already processed")

    pending = [p for p in profiles if p.profile_url not in completed_urls]
    _log(f"Processing {len(pending)} professors")

    # Build clients
    local_client = _build_llm_client(config.local_llm_base_url, config.local_llm_api_key)
    online_client = (
        _build_llm_client(config.online_llm_base_url, config.online_llm_api_key)
        if config.online_llm_api_key
        else None
    )
    search_provider = None
    if config.serper_api_key and not config.skip_web_search:
        from src.data_agents.providers.web_search import WebSearchProvider
        search_provider = WebSearchProvider(api_key=config.serper_api_key)

    semaphore = asyncio.Semaphore(config.max_concurrent)

    # Process in batches for progress reporting
    batch_size = config.max_concurrent * 2
    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start : batch_start + batch_size]
        tasks = [
            _reprocess_single(
                profile=p,
                config=config,
                local_client=local_client,
                online_client=online_client,
                search_provider=search_provider,
                semaphore=semaphore,
                report=report,
            )
            for p in batch
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                report.failed += 1
                report.errors.append(str(result))
                continue

            enriched, _ = result
            # Append to JSONL
            with enriched_path.open("a", encoding="utf-8") as f:
                data = enriched.model_dump(mode="json")
                f.write(json.dumps(data, ensure_ascii=False) + "\n")

        # Progress update
        _log(
            f"Progress: {report.processed}/{len(pending)} "
            f"(homepage: {report.homepage_crawled}, papers: {report.paper_enriched}, "
            f"agent: {report.agent_success}, failed: {report.failed})"
        )

        # Save progress
        progress_path.write_text(
            json.dumps({
                "total": len(pending),
                "processed": report.processed,
                "failed": report.failed,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Update store with enriched profiles
    _log("Updating store with enriched profiles...")
    _update_store_with_enriched(store, enriched_path)

    _log(
        f"Batch complete: {report.processed} processed, "
        f"{report.homepage_crawled} homepages, {report.paper_enriched} papers, "
        f"{report.agent_success} agent, {report.failed} failed"
    )

    return BatchReprocessResult(report=report, output_dir=output_dir)


def _update_store_with_enriched(
    store: SqliteReleasedObjectStore,
    enriched_path: Path,
) -> int:
    """Update store with enriched profiles from JSONL via the release gate."""
    from .publish_helpers import build_professor_record_from_enriched

    if not enriched_path.exists():
        return 0

    updated = 0
    with enriched_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                profile = EnrichedProfessorProfile(**data)
                record = build_professor_record_from_enriched(
                    profile,
                    datetime.now(timezone.utc),
                )
                if record is None:
                    continue
                store.upsert_released_objects([record.to_released_object()])
                updated += 1
            except Exception as e:
                logger.warning("Failed to update store record: %s", e)

    return updated
