#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import faulthandler
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import signal
import sys
import time
from typing import Any
from urllib.parse import urlparse

# Ensure imports work when running the script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.professor.discovery import (
    discover_professor_seeds,
    fetch_html_with_fallback,
    get_allowed_registered_domains,
    get_registered_domain,
)
from src.data_agents.professor.enrichment import (
    build_profile_record,
    extract_profile_record,
    is_structured_profile,
    normalize_text,
)
from src.data_agents.professor.models import DiscoveredProfessorSeed
from src.data_agents.professor.parser import parse_roster_seed_markdown

faulthandler.register(signal.SIGUSR1, all_threads=True)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_seed_doc() -> Path:
    return _repo_root() / "docs" / "教授 URL.md"


def _default_output_path() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _repo_root() / "logs" / "debug" / f"professor_crawler_e2e_{ts}.json"


def _identity_key(seed: DiscoveredProfessorSeed) -> tuple[str, str, str]:
    return (
        normalize_text(seed.name) or "",
        normalize_text(seed.institution) or "",
        normalize_text(seed.department) or "",
    )


def _is_official_domain(url: str, allowed_suffixes: tuple[str, ...]) -> bool:
    hostname = (urlparse(url).hostname or "").lower().strip(".")
    if not hostname:
        return False
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}") for suffix in allowed_suffixes
    )


def _fetch_html(url: str, timeout: float) -> str:
    result = fetch_html_with_fallback(url, timeout=timeout)
    if result.html is not None:
        return result.html
    if result.browser_error:
        raise RuntimeError(result.browser_error)
    raise RuntimeError(f"unable to fetch usable html from {url}")

def run_e2e(
    seed_doc: Path,
    timeout: float,
    official_domain_suffixes: tuple[str, ...],
    include_external_profiles: bool,
    skip_profile_fetch: bool,
) -> dict[str, Any]:
    started_at = time.monotonic()
    markdown = seed_doc.read_text(encoding="utf-8")
    seeds = parse_roster_seed_markdown(markdown)
    seed_url_counter = Counter(seed.roster_url for seed in seeds)
    discovery = discover_professor_seeds(
        seeds=seeds,
        fetch_html=lambda url: _fetch_html(url, timeout),
    )
    discovered_professors = discovery.professors
    roster_pages = []
    status_by_url = {status.seed_url: status for status in discovery.source_statuses}

    for index, seed in enumerate(seeds, start=1):
        status = status_by_url.get(seed.roster_url)
        institution = normalize_text(seed.institution) or "UNKNOWN_INSTITUTION"
        department = normalize_text(seed.department)
        roster_pages.append(
            {
                "seed_index": index,
                "roster_url": seed.roster_url,
                "institution": institution,
                "department": department,
                "status": status.status if status else "unresolved",
                "reason": status.reason if status else "missing_status",
                "visited_urls": status.visited_urls if status else [seed.roster_url],
                "discovered_professor_count": status.discovered_professor_count if status else 0,
                "error": None if not status or status.status != "failed" else status.error,
            }
        )

    identity_counter: Counter[tuple[str, str, str]] = Counter(
        _identity_key(seed) for seed in discovered_professors
    )
    unique_professors: dict[tuple[str, str, str], DiscoveredProfessorSeed] = {}
    for seed in discovered_professors:
        unique_professors.setdefault(_identity_key(seed), seed)

    official_profile_candidate_count = 0
    profile_fetch_success_count = 0
    profile_fetch_failed_count = 0
    skipped_external_profile_count = 0
    structured_profile_count = 0
    partial_profile_count = 0
    official_suffixes = set(official_domain_suffixes)
    official_suffixes.update(
        domain
        for seed in seeds
        for domain in get_allowed_registered_domains(seed.roster_url)
    )
    profile_jobs: list[tuple[int, DiscoveredProfessorSeed]] = []

    ordered_professors = list(unique_professors.values())
    fetched_profile_records: dict[int, dict[str, Any]] = {}
    for index, roster_seed in enumerate(ordered_professors):
        is_official_profile = _is_official_domain(
            roster_seed.profile_url, allowed_suffixes=tuple(sorted(official_suffixes))
        )
        if is_official_profile:
            official_profile_candidate_count += 1

        if not is_official_profile and not include_external_profiles:
            skipped_external_profile_count += 1
            fetched_profile_records[index] = build_profile_record(
                roster_seed=roster_seed,
                extracted=None,
                extraction_status="skipped",
                skip_reason="external_profile_domain_not_allowed_by_default",
            ).to_dict()
            continue
        if skip_profile_fetch:
            skipped_external_profile_count += 1
            fetched_profile_records[index] = build_profile_record(
                roster_seed=roster_seed,
                extracted=None,
                extraction_status="skipped",
                skip_reason="profile_fetch_disabled",
            ).to_dict()
            continue
        profile_jobs.append((index, roster_seed))

    max_workers = min(4, max(1, len(profile_jobs)))
    print(
        (
            f"[professor-crawler-e2e] discovery done in {time.monotonic() - started_at:.1f}s, "
            f"seeds={len(seeds)}, discovered={len(discovered_professors)}, "
            f"unique={len(unique_professors)}, profile_jobs={len(profile_jobs)}"
        ),
        file=sys.stderr,
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {
            executor.submit(
                extract_profile_record,
                roster_seed,
                timeout,
                _fetch_html,
            ): (index, roster_seed)
            for index, roster_seed in profile_jobs
        }
        completed_jobs = 0
        for future in as_completed(future_to_job):
            index, roster_seed = future_to_job[future]
            extracted, error = future.result()
            completed_jobs += 1
            if completed_jobs % 100 == 0 or completed_jobs == len(profile_jobs):
                print(
                    (
                        "[professor-crawler-e2e] profiles "
                        f"{completed_jobs}/{len(profile_jobs)} "
                        f"elapsed={time.monotonic() - started_at:.1f}s "
                        f"success={profile_fetch_success_count} "
                        f"failed={profile_fetch_failed_count}"
                    ),
                    file=sys.stderr,
                    flush=True,
                )
            if error is not None:
                profile_fetch_failed_count += 1
                fetched_profile_records[index] = build_profile_record(
                    roster_seed=roster_seed,
                    extracted=None,
                    extraction_status="failed",
                    skip_reason=None,
                    error=error,
                ).to_dict()
                continue
            assert extracted is not None
            profile_fetch_success_count += 1
            extraction_status = "structured" if is_structured_profile(extracted) else "partial"
            if extraction_status == "structured":
                structured_profile_count += 1
            else:
                partial_profile_count += 1
            fetched_profile_records[index] = build_profile_record(
                roster_seed=roster_seed,
                extracted=extracted,
                extraction_status=extraction_status,
                skip_reason=None,
            ).to_dict()

    profile_records: list[dict[str, Any]] = []
    for index in range(len(ordered_professors)):
        if index in fetched_profile_records:
            profile_records.append(fetched_profile_records[index])

    duplicate_professor_count = sum(count - 1 for count in identity_counter.values() if count > 1)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed_document": str(seed_doc),
        "summary": {
            "seed_url_count": len(seeds),
            "discovered_professor_count": len(discovered_professors),
            "unique_professor_count": len(unique_professors),
            "duplicate_professor_count": duplicate_professor_count,
            "failed_roster_fetch_count": len(discovery.failed_fetch_urls),
            "unresolved_seed_source_count": len(
                [status for status in discovery.source_statuses if status.status == "unresolved"]
            ),
            "official_profile_candidate_count": official_profile_candidate_count,
            "profile_fetch_success_count": profile_fetch_success_count,
            "profile_fetch_failed_count": profile_fetch_failed_count,
            "skipped_external_profile_count": skipped_external_profile_count,
            "structured_profile_count": structured_profile_count,
            "partial_profile_count": partial_profile_count,
        },
        "seed_urls": {
            "counts": dict(sorted(seed_url_counter.items())),
            "duplicate_seed_urls": sorted(
                [url for url, count in seed_url_counter.items() if count > 1]
            ),
        },
        "failed_fetch_urls": discovery.failed_fetch_urls,
        "rosters": roster_pages,
        "profiles": profile_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run real professor crawler e2e against roster seeds and output a structured JSON report."
        )
    )
    parser.add_argument(
        "--seed-doc",
        type=Path,
        default=_default_seed_doc(),
        help="Path to markdown document containing roster seed URLs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_output_path(),
        help="Output JSON path. Use '-' to print JSON to stdout.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP request timeout in seconds.",
    )
    parser.add_argument(
        "--official-domain-suffix",
        action="append",
        default=["sustech.edu.cn"],
        help=(
            "Allowed official domain suffix for profile fetching. "
            "Can be provided multiple times. Default: sustech.edu.cn"
        ),
    )
    parser.add_argument(
        "--include-external-profiles",
        action="store_true",
        help="Fetch external profile URLs too. Default behavior skips them explicitly.",
    )
    parser.add_argument(
        "--skip-profile-fetch",
        action="store_true",
        help="Validate roster discovery only and skip individual profile page fetches.",
    )
    args = parser.parse_args()

    if not args.seed_doc.exists():
        print(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "seed_document": str(args.seed_doc),
                    "error": f"seed document not found: {args.seed_doc}",
                },
                ensure_ascii=False,
            )
        )
        return 1

    suffixes = tuple(
        sorted(
            {
                suffix.lower().strip().lstrip(".")
                for suffix in args.official_domain_suffix
                if suffix and suffix.strip()
            }
        )
    )
    report = run_e2e(
        seed_doc=args.seed_doc,
        timeout=args.timeout,
        official_domain_suffixes=suffixes,
        include_external_profiles=args.include_external_profiles,
        skip_profile_fetch=args.skip_profile_fetch,
    )

    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if str(args.output) == "-":
        print(encoded)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
