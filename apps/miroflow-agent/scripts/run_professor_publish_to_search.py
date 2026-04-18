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
import math
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.contracts import Evidence, ProfessorRecord, ReleasedObject
from src.data_agents.evidence import merge_evidence
from src.data_agents.normalization import build_stable_id, normalize_person_name
from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.publish_helpers import (
    build_evidence as build_profile_evidence,
    build_professor_record_from_enriched,
)
from src.data_agents.service.search_service import DataSearchService
from src.data_agents.storage.milvus_store import MilvusVectorStore
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


_GENERIC_TITLE_SET = {
    "教授",
    "副教授",
    "助理教授",
    "研究员",
    "副研究员",
    "助理研究员",
}
_WEAK_EMAIL_MARKERS = (
    "public",
    "info",
    "admin",
    "office",
    "contact",
    "service",
    "mail",
    "copyright",
)
_STRONG_IDENTITY_ANCHORS = (
    "加拿大工程院院士",
    "中国科学院院士",
    "中国工程院院士",
    "国际欧亚科学院院士",
    "国家科技进步一等奖",
    "国家科技进步二等奖",
    "中国青年科技奖",
    "国务院特殊津贴",
    "长江学者",
    "杰青",
    "优青",
    "IEEE Fellow",
    "ACM Fellow",
    "CCF会士",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_enriched_path() -> Path:
    return _repo_root() / "logs" / "data_agents" / "professor" / "enriched.jsonl"


def _default_output_dir() -> Path:
    return _repo_root() / "logs" / "data_agents" / "professor" / "search_service"


def _default_shared_db_path() -> Path:
    return _repo_root() / "logs" / "data_agents" / "released_objects.db"


def _build_evidence(urls: list[str], fetched_at: datetime) -> list[Evidence]:
    return build_profile_evidence(urls, fetched_at)


def enriched_to_professor_record(
    profile: EnrichedProfessorProfile,
    now: datetime,
) -> ProfessorRecord | None:
    """Convert EnrichedProfessorProfile to ProfessorRecord.

    Returns None if the profile cannot meet ProfessorRecord validation.
    """
    return build_professor_record_from_enriched(profile, now)


def upsert_shared_professor_objects(
    *,
    released_objects: list[ReleasedObject],
    shared_db_path: Path,
    replace_domain: bool = False,
) -> int:
    shared_store = SqliteReleasedObjectStore(shared_db_path)
    if replace_domain:
        shared_store.delete_domain_objects("professor")
    shared_store.upsert_released_objects(released_objects)
    return len(released_objects)


def load_enriched_profiles(paths: list[Path]) -> list[EnrichedProfessorProfile]:
    profiles: list[EnrichedProfessorProfile] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                profiles.append(EnrichedProfessorProfile.model_validate_json(line))
    return profiles


def dedupe_professor_records_for_search(
    professor_records: list[ProfessorRecord],
) -> list[ProfessorRecord]:
    grouped: dict[str, list[ProfessorRecord]] = defaultdict(list)
    for record in professor_records:
        grouped[_search_identity_key(record)].append(record)

    deduped: list[ProfessorRecord] = []
    for group in grouped.values():
        for records in _build_record_clusters(group):
            deduped.append(
                _merge_professor_record_cluster(records)
                if len(records) > 1
                else records[0]
            )
    return deduped


def _build_record_clusters(
    records: list[ProfessorRecord],
) -> list[list[ProfessorRecord]]:
    if len(records) <= 1:
        return [records]

    adjacency: list[set[int]] = [set() for _ in records]
    for left_index, left in enumerate(records):
        left_anchors = _record_anchor_keys(left)
        for right_index in range(left_index + 1, len(records)):
            right = records[right_index]
            right_anchors = _record_anchor_keys(right)
            should_merge = bool(left_anchors and right_anchors and left_anchors.intersection(right_anchors))
            if not should_merge:
                should_merge = _records_likely_same_person(left, right)
            if should_merge:
                adjacency[left_index].add(right_index)
                adjacency[right_index].add(left_index)

    visited: set[int] = set()
    clusters: list[list[ProfessorRecord]] = []
    for start_index in range(len(records)):
        if start_index in visited:
            continue
        stack = [start_index]
        component: list[int] = []
        visited.add(start_index)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)
        component.sort()
        clusters.append([records[index] for index in component])
    return clusters


def _search_identity_key(record: ProfessorRecord) -> str:
    return f"{normalize_person_name(record.name)}|{record.institution.strip().lower()}"


def _record_anchor_keys(record: ProfessorRecord) -> set[str]:
    anchors: set[str] = set()
    homepage = _normalize_anchor_url(record.homepage)
    if homepage:
        anchors.add(f"url:{homepage}")
    email = (record.email or "").strip().lower()
    if email:
        anchors.add(f"email:{email}")
    for item in record.evidence:
        if item.source_type != "official_site" or not item.source_url:
            continue
        url = _normalize_anchor_url(item.source_url)
        if url:
            anchors.add(f"url:{url}")
    return anchors


def _normalize_anchor_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    hostname = (parsed.hostname or "").lower().strip(".")
    path = (parsed.path or "").rstrip("/")
    if not hostname or len(path) <= 1:
        return None
    return f"{hostname}{path}"


def _merge_professor_record_cluster(records: list[ProfessorRecord]) -> ProfessorRecord:
    base = max(records, key=_record_priority)
    merged_evidence = merge_evidence(*[record.evidence for record in records])
    merged = base.model_copy(
        update={
            "id": build_stable_id("PROF", _cluster_identity_key(records)),
            "department": _prefer_non_empty_text(
                base.department,
                *(record.department for record in records),
            ),
            "title": _prefer_non_empty_text(
                base.title,
                *(record.title for record in records),
            ),
            "email": _best_email(records),
            "homepage": _prefer_non_empty_text(
                base.homepage,
                *(record.homepage for record in records),
            ),
            "office": _prefer_non_empty_text(
                base.office,
                *(record.office for record in records),
            ),
            "research_directions": _merge_text_lists(
                record.research_directions for record in records
            ),
            "work_experience": _merge_text_lists(
                record.work_experience for record in records
            ),
            "awards": _merge_text_lists(record.awards for record in records),
            "academic_positions": _merge_text_lists(
                record.academic_positions for record in records
            ),
            "projects": _merge_text_lists(record.projects for record in records),
            "patent_ids": _merge_text_lists(record.patent_ids for record in records),
            "education_structured": _merge_model_lists(
                record.education_structured for record in records
            ),
            "company_roles": _merge_model_lists(record.company_roles for record in records),
            "h_index": _max_int(record.h_index for record in records),
            "citation_count": _max_int(record.citation_count for record in records),
            "paper_count": _max_int(record.paper_count for record in records),
            "profile_summary": _prefer_longer_text(
                base.profile_summary,
                *(record.profile_summary for record in records),
            ),
            "evaluation_summary": _prefer_longer_text(
                base.evaluation_summary,
                *(record.evaluation_summary for record in records),
            ),
            "last_updated": max(record.last_updated for record in records),
            "evidence": merged_evidence,
        },
        deep=True,
    )
    return merged


def _cluster_identity_key(records: list[ProfessorRecord]) -> str:
    base_identity = _search_identity_key(records[0])
    anchor_keys = sorted(
        {
            anchor
            for record in records
            for anchor in _record_anchor_keys(record)
        }
    )
    if anchor_keys:
        return f"{base_identity}|cluster:{'|'.join(anchor_keys)}"

    disambiguators = sorted(
        filter(
            None,
            (_record_cluster_disambiguator(record) for record in records),
        )
    )
    if disambiguators:
        return f"{base_identity}|cluster:{'|'.join(disambiguators)}"
    return f"{base_identity}|cluster:{'|'.join(sorted(record.id for record in records))}"


def _record_cluster_disambiguator(record: ProfessorRecord) -> str:
    homepage = _normalize_anchor_url(record.homepage)
    if homepage:
        return f"url:{homepage}"
    department = (record.department or "").strip().lower()
    if department:
        return f"dept:{department}"
    title = (record.title or "").strip().lower()
    if title:
        return f"title:{title}"
    return record.id


def _records_likely_same_person(left: ProfessorRecord, right: ProfessorRecord) -> bool:
    if normalize_person_name(left.name) != normalize_person_name(right.name):
        return False
    if left.institution.strip().lower() != right.institution.strip().lower():
        return False
    left_email = (left.email or "").strip().lower()
    right_email = (right.email or "").strip().lower()
    if (
        _is_strong_person_email(left_email)
        and _is_strong_person_email(right_email)
        and left_email != right_email
    ):
        return False

    normalized_title = _normalized_title(left.title)
    if not normalized_title or normalized_title != _normalized_title(right.title):
        return False

    shared_anchors = _shared_identity_anchors(left, right)
    summary_bigram = _cosine_similarity(
        _char_ngrams(left.profile_summary, 2),
        _char_ngrams(right.profile_summary, 2),
    )
    summary_trigram = _cosine_similarity(
        _char_ngrams(left.profile_summary, 3),
        _char_ngrams(right.profile_summary, 3),
    )
    direction_overlap = len(
        set(_merge_text_lists([left.research_directions]))
        & set(_merge_text_lists([right.research_directions]))
    )

    if summary_trigram >= 0.45 and (direction_overlap >= 2 or len(shared_anchors) >= 1):
        return True
    if len(shared_anchors) >= 1 and summary_bigram >= 0.2:
        return True
    return False


def _normalized_title(value: str | None) -> str:
    title = (value or "").strip()
    if not title or title in _GENERIC_TITLE_SET:
        return ""
    return title


def _shared_identity_anchors(left: ProfessorRecord, right: ProfessorRecord) -> set[str]:
    left_text = "\n".join(
        [left.profile_summary, *left.awards, *left.academic_positions]
    )
    right_text = "\n".join(
        [right.profile_summary, *right.awards, *right.academic_positions]
    )
    return {
        anchor
        for anchor in _STRONG_IDENTITY_ANCHORS
        if anchor in left_text and anchor in right_text
    }


def _char_ngrams(text: str, size: int) -> Counter[str]:
    normalized = re.sub(r"\s+", "", (text or "").lower())
    if len(normalized) < size:
        return Counter()
    return Counter(normalized[index : index + size] for index in range(len(normalized) - size + 1))


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(left[token] * right[token] for token in left.keys() & right.keys())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _record_priority(record: ProfessorRecord) -> tuple[int, int, int, int]:
    quality_order = {
        "ready": 3,
        "needs_review": 2,
        "needs_enrichment": 1,
        "low_confidence": 0,
    }
    return (
        quality_order.get(record.quality_status, -1),
        record.paper_count or -1,
        len(record.research_directions),
        len(record.profile_summary),
    )


def _merge_text_lists(groups: Iterable[Iterable[str]]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            text = value.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


def _merge_model_lists(groups: Iterable[Iterable[object]]) -> list[object]:
    merged: list[object] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            key = json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            merged.append(value)
    return merged


def _max_int(values: Iterable[int | None]) -> int | None:
    candidates = [value for value in values if value is not None]
    return max(candidates) if candidates else None


def _prefer_longer_text(primary: str, *values: str) -> str:
    best = primary or ""
    for value in values:
        if len(value or "") > len(best):
            best = value
    return best


def _prefer_non_empty_text(primary: str | None, *values: str | None) -> str | None:
    best = (primary or "").strip()
    for value in values:
        candidate = (value or "").strip()
        if candidate and not best:
            best = candidate
    return best or None


def _best_email(records: list[ProfessorRecord]) -> str | None:
    strong_candidates = [
        (record.email or "").strip()
        for record in records
        if _is_strong_person_email(record.email)
    ]
    if strong_candidates:
        return strong_candidates[0]
    return _prefer_non_empty_text(*(record.email for record in records))


def _is_strong_person_email(value: str | None) -> bool:
    email = (value or "").strip().lower()
    if "@" not in email:
        return False
    local_part = email.split("@", 1)[0]
    if any(marker in local_part for marker in _WEAK_EMAIL_MARKERS):
        return False
    return True


def resolve_enriched_inputs(
    *,
    enriched_jsonl: Path | None,
    enriched_dir: Path | None,
) -> list[Path]:
    if enriched_dir is not None:
        paths = sorted(
            path for path in enriched_dir.rglob("enriched_v3.jsonl")
            if path.is_file()
        )
        if paths:
            return paths
    if enriched_jsonl is not None:
        return [enriched_jsonl]
    return [_default_enriched_path()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish enriched professors to shared search service stores."
    )
    parser.add_argument(
        "--enriched-jsonl",
        type=Path,
        help="Path to enriched.jsonl with EnrichedProfessorProfile entries.",
    )
    parser.add_argument(
        "--enriched-dir",
        type=Path,
        help="Directory to recursively discover enriched_v3.jsonl files from URL E2E runs.",
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
    parser.add_argument(
        "--upsert-shared-db",
        action="store_true",
        help="Also upsert released professor objects into the shared released_objects.db used by admin console.",
    )
    parser.add_argument(
        "--shared-db-path",
        type=Path,
        default=_default_shared_db_path(),
        help="Shared SQLite path to update when --upsert-shared-db is set.",
    )
    parser.add_argument(
        "--replace-shared-domain",
        action="store_true",
        help="Delete existing professor objects from shared DB before upserting fresh professor records.",
    )
    args = parser.parse_args()

    enriched_inputs = resolve_enriched_inputs(
        enriched_jsonl=args.enriched_jsonl,
        enriched_dir=args.enriched_dir,
    )
    missing_inputs = [path for path in enriched_inputs if not path.exists()]
    if not enriched_inputs or missing_inputs:
        requested = args.enriched_dir or args.enriched_jsonl or _default_enriched_path()
        print(f"ERROR: enriched input not found: {requested}")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = args.output_dir / "released_objects.sqlite3"
    milvus_path = args.output_dir / "released_objects_milvus.db"
    released_jsonl_path = args.output_dir / "professor_released_objects.jsonl"

    # Step 1: Load enriched profiles
    print("Loading enriched profiles from:")
    for path in enriched_inputs:
        print(f"  - {path}")
    profiles = load_enriched_profiles(enriched_inputs)
    print(f"  Loaded {len(profiles)} enriched profiles")

    # Step 2: Convert to ProfessorRecord → ReleasedObject
    now = datetime.now(timezone.utc)
    raw_professor_records: list[ProfessorRecord] = []
    skip_reasons: Counter[str] = Counter()

    for profile in profiles:
        record = enriched_to_professor_record(profile, now)
        if record is None:
            if not profile.name.strip() or not profile.institution.strip():
                skip_reasons["missing_name_or_institution"] += 1
            else:
                skip_reasons["validation_failed"] += 1
            continue
        raw_professor_records.append(record)

    professor_records = dedupe_professor_records_for_search(raw_professor_records)
    released_objects = [record.to_released_object() for record in professor_records]
    deduped_duplicate_count = len(raw_professor_records) - len(professor_records)

    print(f"  Converted {len(released_objects)} to ReleasedObject")
    if skip_reasons:
        print(f"  Skipped: {dict(skip_reasons)}")
    if deduped_duplicate_count > 0:
        print(f"  Deduped {deduped_duplicate_count} professor duplicates for search")

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

    if args.upsert_shared_db:
        print("Upserting into shared SQLite store...")
        t0 = time.monotonic()
        upsert_shared_professor_objects(
            released_objects=released_objects,
            shared_db_path=args.shared_db_path,
            replace_domain=args.replace_shared_domain,
        )
        print(
            f"  Shared SQLite upsert done in {time.monotonic() - t0:.1f}s → {args.shared_db_path}"
        )

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
        "input_paths": [str(path) for path in enriched_inputs],
        "input_enriched_count": len(profiles),
        "raw_converted_count": len(raw_professor_records),
        "converted_count": len(released_objects),
        "deduped_duplicate_count": deduped_duplicate_count,
        "skip_reasons": dict(skip_reasons),
        "sqlite_path": str(sqlite_path),
        "milvus_path": str(milvus_path),
        "released_jsonl_path": str(released_jsonl_path),
        "shared_db_path": str(args.shared_db_path) if args.upsert_shared_db else None,
        "domain_counts": domain_counts,
    }
    report_path = args.output_dir / "publish_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nReport: {report_path}")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
