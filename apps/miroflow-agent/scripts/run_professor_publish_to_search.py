#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Publish enriched professor profiles into the shared search service stores.

Reads enriched.jsonl (EnrichedProfessorProfile), converts each to
ProfessorRecord → ReleasedObject, and upserts into SqliteReleasedObjectStore
+ MilvusVectorStore so that DataSearchService can search them.

Usage:
    .venv/bin/python scripts/run_professor_publish_to_search.py
    .venv/bin/python scripts/run_professor_publish_to_search.py --enriched-jsonl path/to/enriched.jsonl
    .venv/bin/python scripts/run_professor_publish_to_search.py --test-queries
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.contracts import Evidence, ProfessorRecord, ReleasedObject
from src.data_agents.normalization import build_stable_id, normalize_person_name
from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.service.search_service import DataSearchService
from src.data_agents.storage.milvus_store import MilvusVectorStore
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

# All Shenzhen university edu.cn suffixes — used to classify evidence as official_site
_OFFICIAL_DOMAIN_SUFFIXES = {
    "sustech.edu.cn",
    "szu.edu.cn",
    "tsinghua.edu.cn",
    "sigs.tsinghua.edu.cn",
    "pkusz.edu.cn",
    "pku.edu.cn",
    "hitsz.edu.cn",
    "hit.edu.cn",
    "cuhk.edu.cn",
    "siat.ac.cn",
    "suat-sz.edu.cn",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_enriched_path() -> Path:
    return _repo_root() / "logs" / "data_agents" / "professor" / "enriched.jsonl"


def _default_output_dir() -> Path:
    return _repo_root() / "logs" / "data_agents" / "professor" / "search_service"


def _is_official_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower().strip(".")
    if not hostname:
        return False
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in _OFFICIAL_DOMAIN_SUFFIXES
    )


def _build_evidence(urls: list[str], fetched_at: datetime) -> list[Evidence]:
    seen: set[str] = set()
    evidence: list[Evidence] = []
    for url in urls:
        url = url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        source_type = "official_site" if _is_official_url(url) else "public_web"
        evidence.append(
            Evidence(
                source_type=source_type,
                source_url=url,
                fetched_at=fetched_at,
                confidence=0.8,
            )
        )
    return evidence


def _build_natural_key(profile: EnrichedProfessorProfile) -> str:
    name = normalize_person_name(profile.name)
    institution = profile.institution.strip().lower()
    if profile.department:
        disambiguator = profile.department.strip().lower()
    elif profile.title:
        disambiguator = f"title:{profile.title.strip().lower()}"
    elif profile.profile_url:
        parsed = urlparse(profile.profile_url)
        hostname = (parsed.hostname or "").lower().strip(".")
        path = (parsed.path or "").strip().rstrip("/").lower()
        disambiguator = f"profile:{hostname}{path}"
    else:
        disambiguator = "missing-department-and-title"
    return f"{name}|{institution}|{disambiguator}"


def enriched_to_professor_record(
    profile: EnrichedProfessorProfile,
    now: datetime,
) -> ProfessorRecord | None:
    """Convert EnrichedProfessorProfile to ProfessorRecord.

    Returns None if the profile cannot meet ProfessorRecord validation.
    """
    name = profile.name.strip()
    institution = profile.institution.strip()
    if not name or not institution:
        return None

    # Build evidence from evidence_urls + profile_url + roster_source
    all_urls = list(profile.evidence_urls)
    if profile.profile_url and profile.profile_url not in all_urls:
        all_urls.insert(0, profile.profile_url)
    if profile.roster_source and profile.roster_source not in all_urls:
        all_urls.append(profile.roster_source)
    evidence = _build_evidence(all_urls, now)

    # Must have at least one official_site evidence
    if not any(e.source_type == "official_site" for e in evidence):
        return None

    natural_key = _build_natural_key(profile)
    professor_id = build_stable_id("PROF", natural_key)

    # Ensure summaries meet min length
    profile_summary = profile.profile_summary.strip()
    evaluation_summary = profile.evaluation_summary.strip()
    if not profile_summary or not evaluation_summary:
        return None

    research_dirs = [d.strip() for d in profile.research_directions if d.strip()]

    try:
        return ProfessorRecord(
            id=professor_id,
            name=name,
            institution=institution,
            department=profile.department,
            title=profile.title,
            email=profile.email,
            homepage=profile.homepage or profile.profile_url,
            office=profile.office,
            research_directions=research_dirs,
            education_structured=[],
            work_experience=[],
            h_index=profile.h_index,
            citation_count=profile.citation_count,
            awards=profile.awards or [],
            academic_positions=profile.academic_positions or [],
            projects=profile.projects or [],
            profile_summary=profile_summary,
            evaluation_summary=evaluation_summary,
            company_roles=[],
            top_papers=[],
            patent_ids=[],
            evidence=evidence,
            last_updated=now,
            quality_status="ready",
        )
    except Exception:
        return None


def load_enriched_profiles(path: Path) -> list[EnrichedProfessorProfile]:
    profiles: list[EnrichedProfessorProfile] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            profiles.append(EnrichedProfessorProfile.model_validate_json(line))
    return profiles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish enriched professors to shared search service stores."
    )
    parser.add_argument(
        "--enriched-jsonl",
        type=Path,
        default=_default_enriched_path(),
        help="Path to enriched.jsonl with EnrichedProfessorProfile entries.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_default_output_dir(),
        help="Output directory for SQLite/Milvus stores and released JSONL.",
    )
    parser.add_argument(
        "--test-queries",
        action="store_true",
        help="Run test queries after publishing to verify searchability.",
    )
    args = parser.parse_args()

    if not args.enriched_jsonl.exists():
        print(f"ERROR: enriched JSONL not found: {args.enriched_jsonl}")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = args.output_dir / "released_objects.sqlite3"
    milvus_path = args.output_dir / "released_objects_milvus.db"
    released_jsonl_path = args.output_dir / "professor_released_objects.jsonl"

    # Step 1: Load enriched profiles
    print(f"Loading enriched profiles from {args.enriched_jsonl}...")
    profiles = load_enriched_profiles(args.enriched_jsonl)
    print(f"  Loaded {len(profiles)} enriched profiles")

    # Step 2: Convert to ProfessorRecord → ReleasedObject
    now = datetime.now(timezone.utc)
    professor_records: list[ProfessorRecord] = []
    released_objects: list[ReleasedObject] = []
    skip_reasons: Counter[str] = Counter()

    for profile in profiles:
        record = enriched_to_professor_record(profile, now)
        if record is None:
            if not profile.name.strip() or not profile.institution.strip():
                skip_reasons["missing_name_or_institution"] += 1
            else:
                skip_reasons["validation_failed"] += 1
            continue
        professor_records.append(record)
        released_objects.append(record.to_released_object())

    print(f"  Converted {len(released_objects)} to ReleasedObject")
    if skip_reasons:
        print(f"  Skipped: {dict(skip_reasons)}")

    # Step 3: Write released_objects.jsonl
    with released_jsonl_path.open("w", encoding="utf-8") as f:
        for obj in released_objects:
            f.write(obj.model_dump_json() + "\n")
    print(f"  Wrote {released_jsonl_path}")

    # Step 4: Upsert into SQLite store
    print("Upserting into SQLite store...")
    t0 = time.monotonic()
    sql_store = SqliteReleasedObjectStore(sqlite_path)
    sql_store.upsert_released_objects(released_objects)
    print(f"  SQLite upsert done in {time.monotonic() - t0:.1f}s → {sqlite_path}")

    # Step 5: Upsert into Milvus vector store (hash-based 64-dim)
    print("Upserting into Milvus vector store...")
    t0 = time.monotonic()
    vector_store = MilvusVectorStore(
        uri=str(milvus_path),
        collection_name="released_objects",
    )
    # Batch upsert in chunks to avoid memory issues
    batch_size = 500
    for i in range(0, len(released_objects), batch_size):
        batch = released_objects[i : i + batch_size]
        vector_store.upsert_released_objects(batch)
        if (i + batch_size) % 1000 == 0 or i + batch_size >= len(released_objects):
            print(f"  Milvus batch {i + len(batch)}/{len(released_objects)}")
    print(f"  Milvus upsert done in {time.monotonic() - t0:.1f}s → {milvus_path}")

    # Step 6: Verify counts
    domain_counts = sql_store.count_by_domain()
    print(f"  Domain counts in SQLite: {domain_counts}")

    # Step 7: Test queries
    if args.test_queries:
        print("\nRunning test queries via DataSearchService...")
        service = DataSearchService(sql_store=sql_store, vector_store=vector_store)

        test_queries = [
            "南方科技大学 教授",
            "深圳大学 老师 计算机",
            "清华深圳 研究方向 人工智能",
            "教授 机器学习",
            "导师 材料科学",
            "哈工大深圳 教授",
        ]
        for query in test_queries:
            result = service.search(query, limit=5)
            names = [r.display_name for r in result.results]
            print(f"  Q: {query!r}")
            print(f"    domains={result.domains} type={result.query_type} hits={len(result.results)}")
            if names:
                print(f"    top: {', '.join(names[:5])}")

    # Summary report
    report = {
        "generated_at": now.isoformat(timespec="seconds"),
        "input_enriched_count": len(profiles),
        "converted_count": len(released_objects),
        "skip_reasons": dict(skip_reasons),
        "sqlite_path": str(sqlite_path),
        "milvus_path": str(milvus_path),
        "released_jsonl_path": str(released_jsonl_path),
        "domain_counts": domain_counts,
    }
    report_path = args.output_dir / "publish_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nReport: {report_path}")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
