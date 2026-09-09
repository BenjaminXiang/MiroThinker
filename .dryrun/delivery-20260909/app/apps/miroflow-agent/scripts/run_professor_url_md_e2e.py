#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Run professor pipeline V3 once per seed URL entry for URL-MD E2E validation."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "apps" / "miroflow-agent"))

from src.data_agents.contracts import SHENZHEN_INSTITUTION_KEYWORDS
from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.quality_gate import (
    evaluate_quality,
    has_scholarly_output_signal,
)
from src.data_agents.professor.llm_profiles import (
    render_professor_llm_profile_names,
    resolve_professor_llm_settings,
)
from src.data_agents.professor.name_selection import (
    is_obvious_non_person_name,
    looks_like_profile_blob,
)
from src.data_agents.professor.pipeline_v3 import PipelineV3Config, run_professor_pipeline_v3
from src.data_agents.professor.parser import parse_roster_seed_markdown

DEFAULT_SAMPLE_SEED = 20260414
DEFAULT_TIMEOUT = 30.0
DEFAULT_LIMIT_PER_URL = 3
_DEFAULT_LLM_PROFILE = "gemma4"
_REQUIRED_PROFILE_FIELDS = (
    "name",
    "institution",
    "profile_summary",
    "research_directions",
    "evidence_urls",
)


class SeedEntry(TypedDict):
    index: int
    label: str
    url: str
    institution: str


@dataclass(frozen=True)
class UrlE2EResult:
    rerun_id: str
    index: int
    institution: str
    label: str
    url: str
    released: int
    ready: int
    name: str | None
    resolved_institution: str | None
    paper_count: int | None
    h_index: int | None
    citation_count: int | None
    top_papers_len: int
    quality_status: str | None
    identity_passed: bool
    paper_backed_passed: bool
    required_fields_passed: bool
    quality_status_passed: bool
    gate_passed: bool
    missing_required_fields: list[str]
    failure_reasons: list[str]
    output_dir: str
    error: str | None = None


def _default_seed_doc() -> Path:
    return _REPO_ROOT / "docs" / "教授 URL.md"


def _default_output_dir() -> Path:
    return _REPO_ROOT / "logs" / "data_agents" / "professor_url_md_e2e"


def _infer_institution(label: str, url: str) -> str:
    for keyword in SHENZHEN_INSTITUTION_KEYWORDS:
        if keyword in label:
            return keyword

    host = (urlparse(url).hostname or "").lower()
    host_hints = {
        "sigs.tsinghua.edu.cn": "清华大学深圳国际研究生院",
        "pkusz.edu.cn": "北京大学深圳研究生院",
        "sustech.edu.cn": "南方科技大学",
        "szu.edu.cn": "深圳大学",
        "suat-sz.edu.cn": "深圳理工大学",
        "sztu.edu.cn": "深圳技术大学",
        "hit.edu.cn": "哈尔滨工业大学（深圳）",
        "cuhk.edu.cn": "香港中文大学（深圳）",
        "sysu.edu.cn": "中山大学（深圳）",
    }
    for suffix, institution in host_hints.items():
        if suffix in host:
            return institution
    return "unknown_institution"


def _render_seed_label(seed) -> str:
    if getattr(seed, "label", None):
        return seed.label
    parts = [part for part in [getattr(seed, "institution", None), getattr(seed, "department", None)] if part]
    return " ".join(parts) or seed.roster_url


def _parse_seed_lines(path: Path) -> list[SeedEntry]:
    entries: list[SeedEntry] = []
    seeds = parse_roster_seed_markdown(path.read_text(encoding="utf-8"))
    for index, seed in enumerate(seeds, start=1):
        label = _render_seed_label(seed)
        institution = seed.institution or _infer_institution(label, seed.roster_url)
        entries.append(
            SeedEntry(
                index=index,
                label=label,
                url=seed.roster_url,
                institution=institution,
            )
        )
    return entries


def _slug(index: int, label: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in label).strip("_")
    safe = safe[:60] or "seed"
    return f"{index:03d}_{safe}"


def _build_config(
    seed_doc: Path,
    output_dir: Path,
    *,
    llm_settings: dict[str, str],
    timeout: float,
    skip_web_search: bool,
    skip_vectorize: bool,
    limit_per_url: int,
    store_db_path: Path | None = None,
) -> PipelineV3Config:
    resolved_limit = limit_per_url if limit_per_url > 0 else None
    resolved_store_db_path = store_db_path or (output_dir / "released_objects.db")
    return PipelineV3Config(
        seed_doc=seed_doc,
        output_dir=output_dir,
        local_llm_base_url=llm_settings["local_llm_base_url"],
        local_llm_model=llm_settings["local_llm_model"],
        local_llm_api_key=llm_settings["local_llm_api_key"],
        online_llm_base_url=llm_settings["online_llm_base_url"],
        online_llm_model=llm_settings["online_llm_model"],
        online_llm_api_key=llm_settings["online_llm_api_key"],
        embedding_base_url="" if skip_vectorize else os.getenv(
            "EMBEDDING_BASE_URL",
            "http://100.64.0.27:18005/v1",
        ),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", os.getenv("API_KEY", "")),
        milvus_uri=str(output_dir / "milvus.db"),
        serper_api_key=os.getenv("SERPER_API_KEY", ""),
        crawl_timeout=timeout,
        limit=resolved_limit,
        skip_web_search=skip_web_search,
        skip_vectorize=skip_vectorize,
        store_db_path=str(resolved_store_db_path),
    )


def _load_profiles(output_dir: Path) -> list[dict[str, object]]:
    enriched_path = output_dir / "enriched_v3.jsonl"
    if not enriched_path.exists():
        return []
    return [
        json.loads(line)
        for line in enriched_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _select_best_profile(profiles: list[dict[str, object]]) -> dict[str, object]:
    return max(
        profiles,
        key=lambda item: (
            len(item.get("top_papers", [])),
            item.get("paper_count") or 0,
            item.get("h_index") or 0,
            item.get("citation_count") or 0,
            len(str(item.get("profile_summary") or "")),
        ),
        default={},
    )


def _is_missing_required_field(profile: dict[str, object], field_name: str) -> bool:
    value = profile.get(field_name)
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    return False


def _normalize_institution_name(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    table = str.maketrans({
        "（": "(",
        "）": ")",
        "-": "",
        "_": "",
        " ": "",
    })
    normalized = raw.translate(table)
    normalized = normalized.replace("southernuniversityofscienceandtechnology", "南方科技大学")
    normalized = normalized.replace("sustech", "南方科技大学")
    normalized = normalized.replace("cuhkshenzhen", "香港中文大学(深圳)")
    normalized = normalized.replace("hitshenzhen", "哈尔滨工业大学(深圳)")
    return normalized


def _institution_matches(expected: str, actual: str | None) -> bool:
    actual_normalized = _normalize_institution_name(actual)
    if not actual_normalized:
        return False
    if expected == "unknown_institution":
        return True
    expected_normalized = _normalize_institution_name(expected)
    return (
        expected_normalized == actual_normalized
        or expected_normalized in actual_normalized
        or actual_normalized in expected_normalized
    )


def _compute_failure_reasons(
    *,
    released: int,
    identity_passed: bool,
    paper_backed_passed: bool,
    required_fields_passed: bool,
    quality_status_passed: bool,
    quality_status: str | None,
    missing_required_fields: list[str],
    expected_institution: str,
    resolved_institution: str | None,
    error: str | None,
) -> list[str]:
    if error:
        return ["runtime_failure"]

    reasons: list[str] = []
    if released <= 0:
        reasons.append("not_released")
    if not identity_passed:
        if resolved_institution:
            reasons.append(
                f"identity_failed:{expected_institution}->{resolved_institution}"
            )
        else:
            reasons.append("identity_failed:missing_profile_identity")
    if not paper_backed_passed:
        reasons.append("paper_backed_failed")
    if not required_fields_passed:
        reasons.append(
            "missing_required_fields:" + ",".join(missing_required_fields)
        )
    if released > 0 and not quality_status_passed:
        reasons.append(f"quality_status_failed:{quality_status or 'missing'}")
    return reasons


def _evaluate_gate(
    *,
    entry: SeedEntry,
    rerun_id: str,
    released: int,
    ready: int,
    profile: dict[str, object],
    output_dir: Path,
    error: str | None = None,
) -> UrlE2EResult:
    resolved_institution = None
    quality_status = None
    identity_passed = False
    required_fields_passed = False
    quality_status_passed = False
    missing_required_fields: list[str] = []

    if profile:
        resolved_institution = str(profile.get("institution") or "").strip() or None
        missing_required_fields = [
            field_name
            for field_name in _REQUIRED_PROFILE_FIELDS
            if _is_missing_required_field(profile, field_name)
        ]
        required_fields_passed = len(missing_required_fields) == 0
        profile_name = str(profile.get("name") or "").strip()
        identity_passed = (
            bool(profile_name)
            and not is_obvious_non_person_name(profile_name)
            and not looks_like_profile_blob(profile_name)
            and _institution_matches(entry["institution"], resolved_institution)
        )
        try:
            validated_profile = EnrichedProfessorProfile.model_validate(profile)
            quality = evaluate_quality(validated_profile)
            quality_status = quality.quality_status
            paper_backed_passed = has_scholarly_output_signal(validated_profile)
            quality_status_passed = released > 0 and quality.passed_l1 and quality_status == "ready"
        except Exception:
            quality_status = None
            paper_backed_passed = False
            quality_status_passed = False
    else:
        paper_backed_passed = False

    paper_count = profile.get("paper_count") if profile else None
    h_index = profile.get("h_index") if profile else None
    citation_count = profile.get("citation_count") if profile else None
    top_papers_len = len(profile.get("top_papers", [])) if profile else 0
    failure_reasons = _compute_failure_reasons(
        released=released,
        identity_passed=identity_passed,
        paper_backed_passed=paper_backed_passed,
        required_fields_passed=required_fields_passed,
        quality_status_passed=quality_status_passed,
        quality_status=quality_status,
        missing_required_fields=missing_required_fields,
        expected_institution=entry["institution"],
        resolved_institution=resolved_institution,
        error=error,
    )
    gate_passed = not failure_reasons

    return UrlE2EResult(
        rerun_id=rerun_id,
        index=entry["index"],
        institution=entry["institution"],
        label=entry["label"],
        url=entry["url"],
        released=released,
        ready=ready,
        name=profile.get("name") if profile else None,
        resolved_institution=resolved_institution,
        paper_count=paper_count,
        h_index=h_index,
        citation_count=citation_count,
        top_papers_len=top_papers_len,
        quality_status=quality_status,
        identity_passed=identity_passed,
        paper_backed_passed=paper_backed_passed,
        required_fields_passed=required_fields_passed,
        quality_status_passed=quality_status_passed,
        gate_passed=gate_passed,
        missing_required_fields=missing_required_fields,
        failure_reasons=failure_reasons,
        output_dir=str(output_dir),
        error=error,
    )


def _build_markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# Professor URL-MD E2E Summary",
        "",
        "## Batch",
        f"- Seed doc: `{summary['seed_doc']}`",
        f"- Output dir: `{summary['output_dir']}`",
        f"- LLM profile: `{summary['llm_profile']}`",
        f"- Sampled URLs: `{summary['sampled_urls']}` / `{summary['candidate_urls']}`",
        f"- Elapsed seconds: `{summary['elapsed_seconds']}`",
        "",
        "## Gate Summary",
        f"- Gate passed URLs: `{summary['gate_passed_urls']}`",
        f"- Released URLs: `{summary['released_urls']}`",
        f"- Ready URLs: `{summary['ready_urls']}`",
        f"- Identity passed URLs: `{summary['identity_passed_urls']}`",
        f"- Paper-backed URLs: `{summary['paper_backed_urls']}`",
        f"- Required-fields passed URLs: `{summary['required_fields_passed_urls']}`",
        f"- Quality-ready URLs: `{summary['quality_ready_urls']}`",
        f"- Degraded URLs: `{summary['degraded_urls']}`",
        f"- Consolidated store path: `{summary.get('consolidated_store_path', '')}`",
        f"- Consolidated store counts: `{summary.get('consolidated_store_counts', {})}`",
        "",
        "## Failure Reasons TopN",
    ]
    failure_reason_counts = summary.get("failure_reason_counts", {})
    if failure_reason_counts:
        for reason, count in sorted(
            failure_reason_counts.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            lines.append(f"- `{reason}`: `{count}`")
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Rerun IDs",
    ])
    rerun_ids = summary.get("rerun_ids", [])
    if rerun_ids:
        for rerun_id in rerun_ids:
            lines.append(f"- `{rerun_id}`")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _has_paper_data(result: UrlE2EResult) -> bool:
    return (result.paper_count is not None and result.paper_count > 0) or (
        result.top_papers_len > 0
    )


def _school_counts(entries: list[SeedEntry]) -> dict[str, int]:
    return dict(Counter(e["institution"] for e in entries))


def _consolidate_batch_store(output_dir: Path, target_path: Path) -> dict[str, int]:
    from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

    source_paths = sorted(output_dir.glob("*/released_objects.db"))
    if target_path.exists():
        target_path.unlink()
    target_store = SqliteReleasedObjectStore(target_path)
    for source_path in source_paths:
        source_store = SqliteReleasedObjectStore(source_path)
        for domain in source_store.count_by_domain().keys():
            objects = source_store.list_domain_objects(domain)
            if objects:
                target_store.upsert_released_objects(objects)
    return target_store.count_by_domain()


def _weighted_school_sample(
    entries: list[SeedEntry],
    sample_size: int,
    *,
    random_seed: int = DEFAULT_SAMPLE_SEED,
    enable_weighting: bool = True,
) -> list[SeedEntry]:
    if sample_size <= 0:
        return []
    if sample_size >= len(entries):
        rng = random.Random(random_seed)
        sampled = entries.copy()
        rng.shuffle(sampled)
        return sampled

    rng = random.Random(random_seed)
    candidates = entries.copy()
    selected: list[SeedEntry] = []

    if not enable_weighting:
        for _ in range(sample_size):
            if not candidates:
                break
            selected.append(candidates.pop(rng.randrange(len(candidates))))
        return selected

    school_buckets: dict[str, list[SeedEntry]] = {}
    for entry in candidates:
        school_buckets.setdefault(entry["institution"], []).append(entry)

    for _ in range(sample_size):
        if not school_buckets:
            break
        school_counts = {
            school: len(items)
            for school, items in school_buckets.items()
            if items
        }
        total_weight = sum(school_counts.values())
        if total_weight <= 0:
            break
        threshold = rng.uniform(0, total_weight)
        cumulative = 0.0
        chosen_school = ""
        for school, weight in school_counts.items():
            cumulative += weight
            if threshold <= cumulative:
                chosen_school = school
                break
        if chosen_school == "":
            chosen_school = next(iter(school_counts))
        bucket = school_buckets[chosen_school]
        selected.append(bucket.pop(rng.randrange(len(bucket))))
        if not bucket:
            school_buckets.pop(chosen_school, None)
    return selected


async def _run_sampled_entries(
    *,
    sampled_entries: list[SeedEntry],
    output_dir: Path,
    timeout: float,
    skip_web_search: bool,
    skip_vectorize: bool,
    limit_per_url: int,
    store_db_path: Path | None,
    logging_profile: dict[str, str],
) -> tuple[list[UrlE2EResult], Counter[str], int, Counter[str]]:
    results: list[UrlE2EResult] = []
    failure_reason_counts: Counter[str] = Counter()
    degradation_by_type: Counter[str] = Counter()
    runtime_failures = 0

    for entry in sampled_entries:
        label = entry["label"]
        url = entry["url"]
        index = entry["index"]
        slug = _slug(index, label)
        seed_file = output_dir / f"{slug}.md"
        run_dir = output_dir / slug
        seed_file.write_text(f"{label} {url}\n", encoding="utf-8")

        started = time.monotonic()
        try:
            result = await run_professor_pipeline_v3(
                _build_config(
                    seed_doc=seed_file,
                    output_dir=run_dir,
                    llm_settings=logging_profile,
                    timeout=timeout,
                    skip_web_search=skip_web_search,
                    skip_vectorize=skip_vectorize,
                    limit_per_url=limit_per_url,
                    store_db_path=store_db_path,
                )
            )
            profiles = _load_profiles(run_dir)
            profile = _select_best_profile(profiles)
            quality_distribution = result.report.quality_distribution
            entry_result = _evaluate_gate(
                entry=entry,
                rerun_id=slug,
                released=result.report.released_count,
                ready=quality_distribution.get("ready", 0),
                profile=profile,
                output_dir=run_dir,
            )
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            runtime_failures += 1
            degradation_by_type[type(exc).__name__] += 1
            entry_result = _evaluate_gate(
                entry=entry,
                rerun_id=slug,
                released=0,
                ready=0,
                profile={},
                output_dir=run_dir,
                error=error,
            )
        results.append(entry_result)
        failure_reason_counts.update(entry_result.failure_reasons)
        elapsed = time.monotonic() - started
        print(
            json.dumps(
                {
                    "index": index,
                    "rerun_id": slug,
                    "label": label,
                    "url": url,
                    "released": entry_result.released,
                    "ready": entry_result.ready,
                    "quality_status": entry_result.quality_status,
                    "gate_passed": entry_result.gate_passed,
                    "failure_reasons": entry_result.failure_reasons,
                    "paper_count": entry_result.paper_count,
                    "top_papers_len": entry_result.top_papers_len,
                    "elapsed_seconds": round(elapsed, 1),
                    "error": entry_result.error,
                },
                ensure_ascii=False,
            )
        )

    return results, failure_reason_counts, runtime_failures, degradation_by_type


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run professor V3 E2E for URLs in 教授 URL.md."
    )
    parser.add_argument("--seed-doc", type=Path, default=_default_seed_doc())
    parser.add_argument("--output-dir", type=Path, default=_default_output_dir())
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--limit-per-url",
        type=int,
        default=DEFAULT_LIMIT_PER_URL,
        help="Maximum professors to process per seed URL. Use 0 for no per-URL cap.",
    )
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int, default=None)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=0,
        help=(
            "Number of seed URLs to sample. 0 means all URLs (full run with randomized order)."
        ),
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=DEFAULT_SAMPLE_SEED,
        help="Random seed used for URL sampling.",
    )
    parser.add_argument(
        "--disable-school-weighting",
        action="store_true",
        help="Disable school-weighted sampling and use uniform random.",
    )
    parser.add_argument("--skip-web-search", action="store_true")
    parser.add_argument("--skip-vectorize", action="store_true")
    parser.add_argument(
        "--store-db-path",
        type=Path,
        default=None,
        help=(
            "SQLite store path used during the E2E run. Defaults to "
            "<output-dir>/released_objects.db so validation runs do not mutate the shared serving store."
        ),
    )
    parser.add_argument(
        "--llm-profile",
        type=str,
        default=None,
        help=(
            "LLM profile to use for local/online routing."
            " Supported aliases: gemma, gemma4, qwen, qwen35, miro, mirothinker, ark, volc, volces, doubao."
            f" Defaults to {_DEFAULT_LLM_PROFILE}."
        ),
    )
    parser.add_argument(
        "--degraded-ratio-threshold",
        type=float,
        default=0.0,
        help=(
            "If degraded_urls / sampled_urls >= threshold, exit with non-zero code."
            " Set 0 to skip threshold checks (default)."
        ),
    )
    args = parser.parse_args()

    try:
        logging_profile = resolve_professor_llm_settings(
            profile_name=args.llm_profile,
            default_profile=_DEFAULT_LLM_PROFILE,
            strict=True,
            include_profile=True,
        )
    except ValueError as exc:
        parser.error(f"{exc} Available profiles: {render_professor_llm_profile_names()}")
        return 1

    print(f"Using LLM profile: {logging_profile.get('llm_profile', _DEFAULT_LLM_PROFILE)}")
    print(f"Available profiles: {render_professor_llm_profile_names()}")

    if not args.seed_doc.exists():
        print(json.dumps({"error": f"seed doc not found: {args.seed_doc}"}, ensure_ascii=False))
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    start_ts = time.time()

    seed_entries = _parse_seed_lines(args.seed_doc)
    if not seed_entries:
        print(json.dumps({"error": "No valid seed entries found"}, ensure_ascii=False))
        return 1

    end_index = args.end_index or len(seed_entries)
    candidate_entries = [
        entry
        for entry in seed_entries
        if args.start_index <= entry["index"] <= end_index
    ]
    candidate_school_counts = _school_counts(candidate_entries)
    sample_size = args.sample_size if args.sample_size > 0 else len(candidate_entries)
    sampled_entries = _weighted_school_sample(
        candidate_entries,
        sample_size,
        random_seed=args.sample_seed,
        enable_weighting=not args.disable_school_weighting,
    )

    selected_school_counts = _school_counts(sampled_entries)
    results, failure_reason_counts, runtime_failures, degradation_by_type = asyncio.run(
        _run_sampled_entries(
            sampled_entries=sampled_entries,
            output_dir=args.output_dir,
            timeout=args.timeout,
            skip_web_search=args.skip_web_search,
            skip_vectorize=args.skip_vectorize,
            limit_per_url=args.limit_per_url,
            store_db_path=args.store_db_path,
            logging_profile=logging_profile,
        )
    )

    total_elapsed = time.time() - start_ts
    consolidated_store_path = args.store_db_path or (args.output_dir / "released_objects.db")
    consolidated_store_counts: dict[str, int] = {}
    if args.store_db_path is None:
        consolidated_store_counts = _consolidate_batch_store(args.output_dir, consolidated_store_path)

    summary = {
        "seed_doc": str(args.seed_doc),
        "output_dir": str(args.output_dir),
        "total_urls": len(seed_entries),
        "candidate_urls": len(candidate_entries),
        "sampled_urls": len(sampled_entries),
        "sample_size": sample_size,
        "sample_seed": args.sample_seed,
        "degraded_ratio_threshold": args.degraded_ratio_threshold,
        "school_weighted": not args.disable_school_weighting,
        "start_index": args.start_index,
        "end_index": end_index,
        "candidate_school_counts": candidate_school_counts,
        "selected_school_counts": selected_school_counts,
        "llm_profile": logging_profile.get("llm_profile", _DEFAULT_LLM_PROFILE),
        "degradation_alerts": dict(degradation_by_type),
        "degraded_urls": runtime_failures,
        "degraded_ratio": (runtime_failures / len(sampled_entries))
        if sampled_entries
        else 0,
        "gate_passed_urls": sum(1 for item in results if item.gate_passed),
        "released_urls": sum(1 for item in results if item.released > 0),
        "ready_urls": sum(1 for item in results if item.ready > 0),
        "identity_passed_urls": sum(1 for item in results if item.identity_passed),
        "paper_backed_urls": sum(1 for item in results if item.paper_backed_passed),
        "required_fields_passed_urls": sum(
            1 for item in results if item.required_fields_passed
        ),
        "quality_ready_urls": sum(
            1 for item in results if item.quality_status_passed
        ),
        "paper_data_urls": sum(1 for item in results if _has_paper_data(item)),
        "failed_urls": sum(1 for item in results if item.error),
        "failure_reason_counts": dict(failure_reason_counts),
        "consolidated_store_path": str(consolidated_store_path),
        "consolidated_store_counts": consolidated_store_counts,
        "rerun_ids": [item.rerun_id for item in results if not item.gate_passed],
        "elapsed_seconds": round(total_elapsed, 1),
        "results": [asdict(item) for item in results],
    }
    summary_path = args.output_dir / "url_e2e_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = args.output_dir / "url_e2e_summary.md"
    markdown_path.write_text(_build_markdown_summary(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nSummary saved to: {summary_path}")
    print(f"Markdown summary saved to: {markdown_path}")

    if args.degraded_ratio_threshold > 0:
        return 1 if summary["degraded_ratio"] >= args.degraded_ratio_threshold else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
