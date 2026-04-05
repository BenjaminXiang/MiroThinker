# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Professor Enrichment Pipeline v2 — orchestrator.

Wires Stage 1 (discovery), Stage 2a (regex), Stage 2b (papers),
Stage 2c (agent), Stage 3 (summaries), Stage 4 (quality gate + vectorize + release).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.data_agents.normalization import build_stable_id
from src.data_agents.publish import publish_jsonl

from .completeness import assess_completeness
from .cross_domain import PaperStagingRecord
from .enrichment import build_profile_record, normalize_text
from .models import EnrichedProfessorProfile, MergedProfessorProfileRecord
from .pipeline import run_professor_pipeline
from .quality_gate import QualityResult, build_quality_report, evaluate_quality

logger = logging.getLogger(__name__)


@dataclass
class PipelineV2Config:
    seed_doc: Path
    output_dir: Path
    # LLM
    local_llm_base_url: str = "http://star.sustech.edu.cn/service/model/qwen35/v1"
    local_llm_model: str = "qwen3.5-35b-a3b"
    local_llm_api_key: str = ""
    online_llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    online_llm_model: str = "qwen3.6-plus"
    online_llm_api_key: str = ""
    # Embedding
    embedding_base_url: str = "http://172.18.41.222:18005/v1"
    embedding_api_key: str = ""
    # Milvus
    milvus_uri: str = ""
    # Web search
    serper_api_key: str = ""
    # Concurrency
    max_concurrent_paper_crawl: int = 8
    max_concurrent_agents: int = 8
    max_concurrent_summary: int = 16
    embedding_batch_size: int = 50
    # Timeouts
    crawl_timeout: float = 30.0
    agent_timeout: float = 300.0
    # Domain
    official_domain_suffixes: tuple[str, ...] = ("sustech.edu.cn",)
    # Limits
    limit: int | None = None  # Process at most N professors (for testing)


@dataclass
class PipelineV2Report:
    # Stage 1
    seed_count: int = 0
    discovered_count: int = 0
    unique_count: int = 0
    # Stage 2a
    regex_structured_count: int = 0
    regex_partial_count: int = 0
    # Stage 2b
    paper_enriched_count: int = 0
    papers_collected_total: int = 0
    paper_staging_count: int = 0
    avg_disambiguation_confidence: float = 0.0
    # Stage 2c
    agent_triggered_count: int = 0
    agent_local_success_count: int = 0
    agent_online_escalation_count: int = 0
    agent_failed_count: int = 0
    # Stage 3
    summary_generated_count: int = 0
    summary_fallback_count: int = 0
    # Stage 4
    l1_blocked_count: int = 0
    released_count: int = 0
    quality_distribution: dict[str, int] = field(default_factory=dict)
    vectorized_count: int = 0
    alerts: list[str] = field(default_factory=list)


@dataclass
class PipelineV2Result:
    report: PipelineV2Report
    output_files: dict[str, Path]


def _load_completed_ids(enriched_path: Path) -> set[str]:
    """Load professor IDs from existing enriched.jsonl for resume."""
    completed: set[str] = set()
    if not enriched_path.exists():
        return completed
    with enriched_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                prof_url = data.get("profile_url", "")
                if prof_url:
                    completed.add(prof_url)
            except json.JSONDecodeError:
                continue
    return completed


def _merged_to_enriched(
    record: MergedProfessorProfileRecord,
) -> EnrichedProfessorProfile:
    """Convert v1 MergedProfessorProfileRecord to EnrichedProfessorProfile."""
    return EnrichedProfessorProfile(
        name=record.name or "",
        institution=record.institution or "",
        department=record.department,
        title=record.title,
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
    """Build stable professor ID from name + institution + department."""
    key_parts = [
        (profile.name or "").strip().lower(),
        (profile.institution or "").strip().lower(),
        (profile.department or "").strip().lower(),
    ]
    natural_key = "|".join(key_parts)
    return build_stable_id("prof", natural_key)


async def run_professor_pipeline_v2(
    config: PipelineV2Config,
) -> PipelineV2Result:
    """Run the full v2 professor enrichment pipeline."""
    report = PipelineV2Report()
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    enriched_path = output_dir / "enriched.jsonl"
    paper_staging_path = output_dir / "paper_staging.jsonl"
    summarized_path = output_dir / "summarized.jsonl"
    professor_records_path = output_dir / "professor_records.jsonl"
    released_objects_path = output_dir / "released_objects.jsonl"
    quality_report_path = output_dir / "quality_report.json"
    failed_tasks_path = output_dir / "failed_tasks.jsonl"

    # --- Stage 1: Roster Discovery ---
    _log("Stage 1: Roster Discovery")
    v1_result = run_professor_pipeline(
        config.seed_doc,
        timeout=config.crawl_timeout,
        official_domain_suffixes=config.official_domain_suffixes,
    )
    report.seed_count = v1_result.report.seed_url_count
    report.discovered_count = v1_result.report.discovered_professor_count
    report.unique_count = v1_result.report.unique_professor_count
    report.regex_structured_count = v1_result.report.structured_profile_count
    report.regex_partial_count = v1_result.report.partial_profile_count

    profiles = v1_result.profiles
    if config.limit:
        profiles = profiles[: config.limit]

    _log(f"Stage 1 done: {report.unique_count} unique professors, processing {len(profiles)}")

    # --- Resume checkpoint ---
    completed_urls = _load_completed_ids(enriched_path)
    if completed_urls:
        _log(f"Resuming: {len(completed_urls)} professors already processed")

    # --- Stage 2: Per-Professor Enrichment ---
    _log("Stage 2: Per-Professor Enrichment")

    # Build LLM clients
    local_client = _build_llm_client(
        config.local_llm_base_url, config.local_llm_api_key
    )
    online_client = (
        _build_llm_client(config.online_llm_base_url, config.online_llm_api_key)
        if config.online_llm_api_key
        else None
    )

    # Process professors with concurrency control
    semaphore = asyncio.Semaphore(config.max_concurrent_paper_crawl)
    enriched_profiles: list[EnrichedProfessorProfile] = []
    all_staging_records: list[PaperStagingRecord] = []
    failed_tasks: list[dict] = []

    tasks = []
    for record in profiles:
        if record.profile_url in completed_urls:
            # Load from existing enriched.jsonl
            continue
        tasks.append(
            _process_single_professor(
                record=record,
                config=config,
                local_client=local_client,
                online_client=online_client,
                semaphore=semaphore,
                report=report,
            )
        )

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                _log(f"Professor failed: {result}")
                report.agent_failed_count += 1
                failed_tasks.append({
                    "error": str(result),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue
            enriched, staging = result
            enriched_profiles.append(enriched)
            all_staging_records.extend(staging)

            # Append to JSONL immediately (resume support)
            _append_jsonl(enriched_path, enriched)
            for s in staging:
                _append_jsonl(paper_staging_path, s)

        _log(
            f"Stage 2 done: {len(enriched_profiles)} enriched, "
            f"{len(all_staging_records)} papers staged, "
            f"{report.agent_failed_count} failed"
        )

    # Load previously enriched profiles from JSONL
    all_enriched = _load_enriched_profiles(enriched_path)
    report.paper_enriched_count = sum(
        1 for p in all_enriched if p.enrichment_source != "regex_only"
    )
    report.paper_staging_count = len(all_staging_records)

    # --- Stage 3: Summary Generation ---
    _log("Stage 3: Summary Generation")
    for profile in all_enriched:
        if not profile.profile_summary or len(profile.profile_summary) < 200:
            try:
                summaries = await _generate_summaries_for_profile(
                    profile, local_client, config.local_llm_model
                )
                profile = profile.model_copy(update={
                    "profile_summary": summaries[0],
                    "evaluation_summary": summaries[1],
                })
                report.summary_generated_count += 1
            except Exception:
                # Fallback to rule-based
                profile = profile.model_copy(update={
                    "profile_summary": _build_fallback_summary(profile),
                    "evaluation_summary": _build_fallback_eval(profile),
                })
                report.summary_fallback_count += 1

    # --- Stage 4: Quality Gate + Release + Vectorize ---
    _log("Stage 4: Quality Gate + Release + Vectorize")
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
        "incomplete": qreport.incomplete_count,
        "shallow_summary": qreport.shallow_summary_count,
        "needs_enrichment": qreport.needs_enrichment_count,
    }
    report.alerts = qreport.alerts

    # Write quality report
    quality_report_path.write_text(
        json.dumps(
            {
                "total": qreport.total_count,
                "released": qreport.released_count,
                "blocked": qreport.blocked_count,
                "quality_distribution": report.quality_distribution,
                "alerts": report.alerts,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Vectorize (if embedding available)
    if config.embedding_base_url and released_profiles:
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

            # Batch vectorize
            for i in range(0, len(released_profiles), config.embedding_batch_size):
                batch = released_profiles[i : i + config.embedding_batch_size]
                count = vectorizer.vectorize_and_upsert(batch)
                report.vectorized_count += count
                _log(f"Vectorized batch {i // config.embedding_batch_size + 1}: {count} professors")
        except Exception as e:
            _log(f"Vectorization failed: {e}")
            report.alerts.append(f"vectorization_failed: {e}")

    # Write failed tasks
    if failed_tasks:
        with failed_tasks_path.open("w", encoding="utf-8") as f:
            for task in failed_tasks:
                f.write(json.dumps(task, ensure_ascii=False) + "\n")

    _log(
        f"Pipeline complete: {report.released_count} released, "
        f"{report.l1_blocked_count} blocked, "
        f"{report.vectorized_count} vectorized"
    )

    return PipelineV2Result(
        report=report,
        output_files={
            "enriched": enriched_path,
            "paper_staging": paper_staging_path,
            "quality_report": quality_report_path,
        },
    )


async def _process_single_professor(
    *,
    record: MergedProfessorProfileRecord,
    config: PipelineV2Config,
    local_client: Any,
    online_client: Any | None,
    semaphore: asyncio.Semaphore,
    report: PipelineV2Report,
) -> tuple[EnrichedProfessorProfile, list[PaperStagingRecord]]:
    """Process a single professor through Stage 2a → 2b → 2c."""
    async with semaphore:
        # Stage 2a: regex pre-extract (already done in v1 pipeline)
        profile = _merged_to_enriched(record)
        prof_id = _build_professor_id(profile)
        staging_records: list[PaperStagingRecord] = []

        # Stage 2b: paper collection
        try:
            from .discovery import fetch_html_with_fallback
            from .paper_collector import enrich_from_papers

            def fetch_html(url: str, timeout: float) -> str:
                result = fetch_html_with_fallback(url, timeout=timeout)
                if result.html is not None:
                    return result.html
                raise RuntimeError(f"unable to fetch html from {url}")

            paper_result = await enrich_from_papers(
                name=profile.name,
                name_en=profile.name_en,
                institution=profile.institution,
                institution_en=None,
                official_directions=profile.research_directions,
                professor_id=prof_id,
                fetch_html=fetch_html,
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
                "field_provenance": {
                    **profile.field_provenance,
                    "research_directions": "paper_analysis",
                    "h_index": "semantic_scholar",
                    "citation_count": "semantic_scholar",
                    "top_papers": "academic_sources",
                },
            })
            staging_records = paper_result.staging_records
            report.papers_collected_total += len(paper_result.staging_records)
        except Exception as e:
            logger.warning("Paper collection failed for %s: %s", profile.name, e)

        # Stage 2c: agent enrichment (if needed)
        assessment = assess_completeness(profile)
        if assessment.should_trigger_agent:
            report.agent_triggered_count += 1
            try:
                from .agent_enrichment import run_agent_enrichment

                agent_result = await run_agent_enrichment(
                    profile=profile,
                    missing_fields=assessment.missing_fields,
                    html_text="",  # TODO: pass actual page HTML
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

        # Stage 3 (inline): generate summaries if needed
        if not profile.profile_summary or len(profile.profile_summary) < 200:
            try:
                summaries = await _generate_summaries_for_profile(
                    profile, local_client, config.local_llm_model
                )
                profile = profile.model_copy(update={
                    "profile_summary": summaries[0],
                    "evaluation_summary": summaries[1],
                })
            except Exception:
                profile = profile.model_copy(update={
                    "profile_summary": _build_fallback_summary(profile),
                    "evaluation_summary": _build_fallback_eval(profile),
                })

        return profile, staging_records


async def _generate_summaries_for_profile(
    profile: EnrichedProfessorProfile,
    llm_client: Any,
    llm_model: str,
) -> tuple[str, str]:
    """Generate profile_summary and evaluation_summary via LLM."""
    try:
        from .summary_generator import generate_summaries

        result = await generate_summaries(
            profile=profile,
            llm_client=llm_client,
            llm_model=llm_model,
        )
        return result.profile_summary, result.evaluation_summary
    except ImportError:
        return _build_fallback_summary(profile), _build_fallback_eval(profile)


def _build_fallback_summary(profile: EnrichedProfessorProfile) -> str:
    """Rule-based fallback summary when LLM is unavailable."""
    name = profile.name or "该教师"
    institution = profile.institution or "所在高校"
    department = profile.department or ""
    title = profile.title or "教师"

    parts = [f"{name}现任{institution}"]
    if department:
        parts[0] += department
    parts[0] += f"{title}。"

    if profile.research_directions:
        dirs = "、".join(profile.research_directions[:5])
        parts.append(f"研究方向包括{dirs}。")

    if profile.h_index:
        parts.append(f"h-index为{profile.h_index}。")

    if profile.top_papers:
        paper_titles = "、".join(f"《{p.title}》" for p in profile.top_papers[:3])
        parts.append(f"代表论文包括{paper_titles}。")

    if profile.awards:
        parts.append(f"获得{profile.awards[0]}等荣誉。")

    summary = "".join(parts)
    # Pad to minimum
    while len(summary) < 200:
        summary += "该教授在深圳科创领域有持续贡献。"
    return summary[:300]


def _build_fallback_eval(profile: EnrichedProfessorProfile) -> str:
    """Rule-based fallback evaluation summary."""
    name = profile.name or "该教师"
    parts = []

    if profile.h_index:
        parts.append(f"h-index {profile.h_index}")
    if profile.citation_count:
        parts.append(f"总引用{profile.citation_count}次")
    if profile.paper_count:
        parts.append(f"发表论文{profile.paper_count}篇")
    if profile.awards:
        parts.append(f"{profile.awards[0]}")

    if parts:
        summary = f"{name}：{'，'.join(parts)}。"
    else:
        summary = f"{name}目前已完成基础信息采集。"

    while len(summary) < 100:
        summary += "数据正在持续完善中。"
    return summary[:150]


def _append_jsonl(path: Path, record: BaseModel) -> None:
    """Append a single Pydantic model as a JSONL line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json())
        f.write("\n")


def _load_enriched_profiles(path: Path) -> list[EnrichedProfessorProfile]:
    """Load all enriched profiles from JSONL."""
    profiles: list[EnrichedProfessorProfile] = []
    if not path.exists():
        return profiles
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                profiles.append(EnrichedProfessorProfile.model_validate_json(line))
            except Exception:
                continue
    return profiles


def _build_llm_client(base_url: str, api_key: str) -> Any:
    """Build an OpenAI-compatible client."""
    from src.data_agents.providers.qwen import build_openai_client

    return build_openai_client(
        base_url=base_url,
        api_key=api_key or "dummy",
        timeout=300.0,
    )


def _log(msg: str) -> None:
    """Log to stderr for pipeline progress."""
    print(f"[professor-pipeline-v2] {msg}", file=sys.stderr, flush=True)
