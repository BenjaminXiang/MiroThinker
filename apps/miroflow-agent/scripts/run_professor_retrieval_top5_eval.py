#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Generate and aggregate professor Top-5 retrieval evaluation reports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.service.search_service import DataSearchService
from src.data_agents.storage.milvus_store import MilvusVectorStore
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_shared_db_path() -> Path:
    return _repo_root() / "logs" / "data_agents" / "released_objects.db"


def _default_vector_db_path() -> Path:
    return _repo_root() / "logs" / "data_agents" / "professor_retrieval_eval" / "retrieval_eval_milvus.db"


def _default_output_dir() -> Path:
    return _repo_root() / "logs" / "data_agents" / "professor_retrieval_eval"


def _load_query_set(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("query set must contain a non-empty 'queries' list")
    return queries


def _prepare_service(
    *,
    shared_db_path: Path,
    vector_db_path: Path,
) -> DataSearchService:
    sql_store = SqliteReleasedObjectStore(shared_db_path)
    professor_objects = sql_store.list_domain_objects("professor")
    if not professor_objects:
        raise ValueError(f"no professor released objects found in {shared_db_path}")

    vector_store = MilvusVectorStore(
        uri=str(vector_db_path),
        collection_name="released_objects",
    )
    vector_store.upsert_released_objects(professor_objects)
    return DataSearchService(sql_store=sql_store, vector_store=vector_store)


def _build_result_snapshot(item: Any, rank: int) -> dict[str, Any]:
    core_facts = item.core_facts
    return {
        "rank": rank,
        "id": item.id,
        "display_name": item.display_name,
        "quality_status": item.quality_status,
        "institution": core_facts.get("institution"),
        "department": core_facts.get("department"),
        "title": core_facts.get("title"),
        "research_directions": core_facts.get("research_directions") or [],
        "top_papers": core_facts.get("top_papers") or [],
    }


def _normalize_institution(value: str | None) -> str:
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
    return raw.translate(table)


def _institution_matches(expected: str | None, actual: str | None) -> bool:
    expected_normalized = _normalize_institution(expected)
    actual_normalized = _normalize_institution(actual)
    if not expected_normalized or not actual_normalized:
        return False
    return (
        expected_normalized == actual_normalized
        or expected_normalized in actual_normalized
        or actual_normalized in expected_normalized
    )


def _compute_expected_target_ranks(
    *,
    expected_name: str | None,
    expected_institution: str | None,
    results: list[dict[str, Any]],
) -> list[int]:
    normalized_expected_name = (expected_name or "").strip()
    if not normalized_expected_name:
        return []
    matched_ranks: list[int] = []
    for result in results:
        if str(result.get("display_name") or "").strip() != normalized_expected_name:
            continue
        if expected_institution and not _institution_matches(
            expected_institution,
            result.get("institution"),
        ):
            continue
        matched_ranks.append(int(result["rank"]))
    return matched_ranks


def _generate_report(
    *,
    query_set_path: Path,
    shared_db_path: Path,
    vector_db_path: Path,
    output_dir: Path,
    default_topk: int,
    mode: str,
) -> dict[str, Any]:
    service = _prepare_service(
        shared_db_path=shared_db_path,
        vector_db_path=vector_db_path,
    )
    queries = _load_query_set(query_set_path)
    report_queries: list[dict[str, Any]] = []
    for index, query_item in enumerate(queries, start=1):
        query = str(query_item.get("query") or "").strip()
        if not query:
            raise ValueError(f"query entry {index} is missing a non-empty query")
        query_id = str(query_item.get("query_id") or f"q{index:03d}")
        topk = int(query_item.get("topk") or default_topk)
        response = service.search(query, mode=mode, limit=topk)
        expected_name = str(query_item.get("expected_name") or "").strip() or None
        expected_institution = str(query_item.get("expected_institution") or "").strip() or None
        results = [
            _build_result_snapshot(item, rank)
            for rank, item in enumerate(response.results[:topk], start=1)
        ]
        expected_target_ranks = _compute_expected_target_ranks(
            expected_name=expected_name,
            expected_institution=expected_institution,
            results=results,
        )
        expected_target_rank = expected_target_ranks[0] if expected_target_ranks else None
        report_queries.append(
            {
                "query_id": query_id,
                "query": query,
                "query_type": response.query_type,
                "domains": list(response.domains),
                "topk": topk,
                "results": results,
                "expected": {
                    "name": expected_name,
                    "institution": expected_institution,
                },
                "machine": {
                    "expected_target_rank": expected_target_rank,
                    "expected_target_in_topk": expected_target_rank is not None,
                    "expected_target_match_count": len(expected_target_ranks),
                    "duplicate_expected_target_in_topk": len(expected_target_ranks) > 1,
                },
                "manual": {
                    "relevant_ranks": None,
                    "notes": "",
                },
            }
        )

    report = {
        "query_set_json": str(query_set_path),
        "shared_db_path": str(shared_db_path),
        "vector_db_path": str(vector_db_path),
        "mode": mode,
        "topk": default_topk,
        "query_count": len(report_queries),
        "queries": report_queries,
    }
    report_path = output_dir / "retrieval_top5_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = output_dir / "retrieval_top5_report.md"
    markdown_path.write_text(_build_report_markdown(report), encoding="utf-8")
    return report


def _relevant_count(query_item: dict[str, Any]) -> int | None:
    manual = query_item.get("manual") or {}
    ranks = manual.get("relevant_ranks")
    if ranks is None:
        return None
    if not isinstance(ranks, list):
        raise ValueError("manual.relevant_ranks must be a list or null")
    topk = int(query_item.get("topk") or 5)
    seen: set[int] = set()
    for value in ranks:
        rank = int(value)
        if rank < 1 or rank > topk:
            raise ValueError(f"manual relevant rank {rank} is outside topk={topk}")
        seen.add(rank)
    return len(seen)


def _aggregate_judged_report(
    *,
    judged_report_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    report = json.loads(judged_report_path.read_text(encoding="utf-8"))
    queries = report.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("judged report must contain a non-empty 'queries' list")

    query_count = 0
    judged_result_count = 0
    relevant_result_count = 0
    exact_target_query_count = 0
    exact_target_hit_count = 0
    duplicate_target_query_count = 0
    for query_item in queries:
        relevant_count = _relevant_count(query_item)
        if relevant_count is None:
            expected = query_item.get("expected") or {}
            machine = query_item.get("machine") or {}
            if expected.get("name") or expected.get("institution"):
                exact_target_query_count += 1
                if bool(machine.get("duplicate_expected_target_in_topk")):
                    duplicate_target_query_count += 1
            expected_rank = machine.get("expected_target_rank")
            if expected_rank is not None:
                if int(expected_rank) >= 1:
                    exact_target_hit_count += 1
            continue
        results = query_item.get("results") or []
        topk = int(query_item.get("topk") or report.get("topk") or 5)
        considered = min(len(results), topk) if results else topk
        query_count += 1
        judged_result_count += considered
        relevant_result_count += min(relevant_count, considered)

    payload = {
        "judged_report_json": str(judged_report_path),
        "query_count": query_count if query_count > 0 else exact_target_query_count,
        "judged_result_count": judged_result_count,
        "relevant_result_count": relevant_result_count,
        "top5_relevance_rate": (
            relevant_result_count / judged_result_count
            if judged_result_count > 0
            else None
        ),
        "top5_exact_target_query_count": exact_target_hit_count,
        "top5_exact_target_rate": (
            exact_target_hit_count / exact_target_query_count
            if exact_target_query_count > 0
            else None
        ),
        "top5_duplicate_target_query_count": duplicate_target_query_count,
        "top5_duplicate_target_rate": (
            duplicate_target_query_count / exact_target_query_count
            if exact_target_query_count > 0
            else None
        ),
    }
    payload_path = output_dir / "retrieval_eval.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = output_dir / "retrieval_eval.md"
    markdown_path.write_text(_build_eval_markdown(payload), encoding="utf-8")
    return payload


def _build_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Professor Retrieval Top-5 Report",
        "",
        "## Batch",
        f"- Query set: `{report['query_set_json']}`",
        f"- Shared DB: `{report['shared_db_path']}`",
        f"- Vector DB: `{report['vector_db_path']}`",
        f"- Query count: `{report['query_count']}`",
        f"- Mode: `{report['mode']}`",
        "",
        "## Queries",
    ]
    for query_item in report["queries"]:
        lines.extend(
            [
                "",
                f"### {query_item['query_id']}",
                f"- Query: `{query_item['query']}`",
                f"- Query type: `{query_item['query_type']}`",
                f"- Domains: `{query_item['domains']}`",
                f"- TopK: `{query_item['topk']}`",
            ]
        )
        expected = query_item.get("expected") or {}
        machine = query_item.get("machine") or {}
        if expected.get("name") or expected.get("institution"):
            lines.append(
                f"- Expected target: `{expected.get('name')}` / `{expected.get('institution')}`"
            )
            lines.append(
                f"- Machine target rank: `{machine.get('expected_target_rank')}`"
            )
            lines.append(
                f"- Machine target match count: `{machine.get('expected_target_match_count')}`"
            )
            lines.append(
                f"- Machine duplicate target in TopK: `{machine.get('duplicate_expected_target_in_topk')}`"
            )
        for result in query_item["results"]:
            lines.append(
                f"- Rank {result['rank']}: `{result['display_name']}` / `{result['institution']}` / `{result['id']}`"
            )
        lines.append("- Manual relevant ranks: `[]`")
        lines.append("- Notes:")
    return "\n".join(lines) + "\n"


def _build_eval_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Professor Retrieval Eval",
        "",
        f"- Judged report: `{payload['judged_report_json']}`",
        f"- Query count: `{payload['query_count']}`",
        f"- Judged result count: `{payload['judged_result_count']}`",
        f"- Relevant result count: `{payload['relevant_result_count']}`",
        f"- Top-5 relevance rate: `{payload['top5_relevance_rate']}`",
        f"- Top-5 exact target query count: `{payload['top5_exact_target_query_count']}`",
        f"- Top-5 exact target rate: `{payload['top5_exact_target_rate']}`",
        f"- Top-5 duplicate target query count: `{payload['top5_duplicate_target_query_count']}`",
        f"- Top-5 duplicate target rate: `{payload['top5_duplicate_target_rate']}`",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and aggregate professor Top-5 retrieval evaluation reports."
    )
    parser.add_argument("--query-set-json", type=Path, default=None)
    parser.add_argument("--judged-report-json", type=Path, default=None)
    parser.add_argument("--shared-db-path", type=Path, default=_default_shared_db_path())
    parser.add_argument("--vector-db-path", type=Path, default=_default_vector_db_path())
    parser.add_argument("--output-dir", type=Path, default=_default_output_dir())
    parser.add_argument("--topk", type=int, default=5)
    parser.add_argument("--mode", type=str, default="hybrid")
    args = parser.parse_args()

    if args.query_set_json is None and args.judged_report_json is None:
        parser.error("one of --query-set-json or --judged-report-json is required")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.query_set_json is not None:
        if not args.query_set_json.exists():
            print(json.dumps({"error": f"query set not found: {args.query_set_json}"}, ensure_ascii=False))
            return 1
        report = _generate_report(
            query_set_path=args.query_set_json,
            shared_db_path=args.shared_db_path,
            vector_db_path=args.vector_db_path,
            output_dir=args.output_dir,
            default_topk=args.topk,
            mode=args.mode,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\nReport saved to: {args.output_dir / 'retrieval_top5_report.json'}")
        print(f"Markdown report saved to: {args.output_dir / 'retrieval_top5_report.md'}")
        return 0

    if not args.judged_report_json.exists():
        print(json.dumps({"error": f"judged report not found: {args.judged_report_json}"}, ensure_ascii=False))
        return 1
    payload = _aggregate_judged_report(
        judged_report_path=args.judged_report_json,
        output_dir=args.output_dir,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nEval payload saved to: {args.output_dir / 'retrieval_eval.json'}")
    print(f"Markdown eval saved to: {args.output_dir / 'retrieval_eval.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
