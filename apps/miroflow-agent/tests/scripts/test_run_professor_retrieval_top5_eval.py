# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.contracts import ProfessorRecord
from src.data_agents.evidence import build_evidence
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


TIMESTAMP = datetime(2026, 4, 14, tzinfo=timezone.utc)


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_script():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_professor_retrieval_top5_eval.py"
    return _load_module("run_professor_retrieval_top5_eval", script_path)


def _write_query_set(path: Path, queries: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps({"queries": queries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _professor_record(
    *,
    professor_id: str,
    name: str,
    institution: str,
    directions: list[str],
) -> ProfessorRecord:
    return ProfessorRecord(
        id=professor_id,
        name=name,
        institution=institution,
        department="计算机学院",
        title="教授",
        research_directions=directions,
        profile_summary=f"{name}现任{institution}教授，研究方向包括{'、'.join(directions)}。",
        evaluation_summary="资料完整。",
        evidence=[
            build_evidence(
                source_type="official_site",
                source_url=f"https://example.edu.cn/{professor_id.lower()}",
                fetched_at=TIMESTAMP,
                confidence=0.9,
            )
        ],
        last_updated=TIMESTAMP,
    )


def test_retrieval_eval_generates_report_from_shared_db(tmp_path, monkeypatch) -> None:
    module = _load_script()
    shared_db_path = tmp_path / "released_objects.db"
    vector_db_path = tmp_path / "released_objects_milvus.db"
    output_dir = tmp_path / "eval"

    store = SqliteReleasedObjectStore(shared_db_path)
    store.upsert_released_objects(
        [
            _professor_record(
                professor_id="PROF-1",
                name="靳玉乐",
                institution="深圳大学",
                directions=["课程思政"],
            ).to_released_object(),
            _professor_record(
                professor_id="PROF-2",
                name="吴亚北",
                institution="南方科技大学",
                directions=["地震学", "地球物理"],
            ).to_released_object(),
        ]
    )

    query_set_path = _write_query_set(
        tmp_path / "queries.json",
        [
            {
                "query_id": "q1",
                "query": "深圳大学 靳玉乐 教授",
                "expected_name": "靳玉乐",
                "expected_institution": "深圳大学",
            }
        ],
    )

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--query-set-json",
            str(query_set_path),
            "--shared-db-path",
            str(shared_db_path),
            "--vector-db-path",
            str(vector_db_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    code = module.main()
    assert code == 0

    report = json.loads((output_dir / "retrieval_top5_report.json").read_text(encoding="utf-8"))
    assert report["query_count"] == 1
    [item] = report["queries"]
    assert item["query_id"] == "q1"
    assert item["results"][0]["id"] == "PROF-1"
    assert item["results"][0]["display_name"] == "靳玉乐"
    assert item["expected"]["name"] == "靳玉乐"
    assert item["expected"]["institution"] == "深圳大学"
    assert item["machine"]["expected_target_rank"] == 1
    assert item["machine"]["expected_target_in_topk"] is True
    assert item["machine"]["expected_target_match_count"] == 1
    assert item["machine"]["duplicate_expected_target_in_topk"] is False
    assert item["manual"] == {
        "relevant_ranks": None,
        "notes": "",
    }


def test_retrieval_eval_aggregates_judged_report(tmp_path, monkeypatch) -> None:
    module = _load_script()
    report_path = tmp_path / "retrieval_top5_report.json"
    report_path.write_text(
        json.dumps(
            {
                "query_count": 2,
                "topk": 5,
                "queries": [
                    {
                        "query_id": "q1",
                        "query": "深圳大学 靳玉乐 教授",
                        "results": [{"rank": i} for i in range(1, 6)],
                        "manual": {
                            "relevant_ranks": [1, 2, 3, 5],
                            "notes": "",
                        },
                    },
                    {
                        "query_id": "q2",
                        "query": "南方科技大学 吴亚北 教授",
                        "results": [{"rank": i} for i in range(1, 6)],
                        "manual": {
                            "relevant_ranks": [1, 2, 4, 5],
                            "notes": "",
                        },
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "eval"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--judged-report-json",
            str(report_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    code = module.main()
    assert code == 0

    payload = json.loads((output_dir / "retrieval_eval.json").read_text(encoding="utf-8"))
    assert payload["query_count"] == 2
    assert payload["judged_result_count"] == 10
    assert payload["relevant_result_count"] == 8
    assert payload["top5_relevance_rate"] == 0.8


def test_retrieval_eval_aggregates_exact_target_metrics_without_manual_labels(tmp_path, monkeypatch) -> None:
    module = _load_script()
    report_path = tmp_path / "retrieval_top5_report.json"
    report_path.write_text(
        json.dumps(
            {
                "query_count": 2,
                "topk": 5,
                "queries": [
                    {
                        "query_id": "q1",
                        "query": "深圳大学 靳玉乐 教授",
                        "results": [{"rank": i} for i in range(1, 6)],
                        "expected": {
                            "name": "靳玉乐",
                            "institution": "深圳大学",
                        },
                        "machine": {
                            "expected_target_rank": 1,
                            "expected_target_in_topk": True,
                        },
                        "manual": {
                            "relevant_ranks": None,
                            "notes": "",
                        },
                    },
                    {
                        "query_id": "q2",
                        "query": "南方科技大学 吴亚北 教授",
                        "results": [{"rank": i} for i in range(1, 6)],
                        "expected": {
                            "name": "吴亚北",
                            "institution": "南方科技大学",
                        },
                        "machine": {
                            "expected_target_rank": 3,
                            "expected_target_in_topk": True,
                        },
                        "manual": {
                            "relevant_ranks": None,
                            "notes": "",
                        },
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "eval"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--judged-report-json",
            str(report_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    code = module.main()
    assert code == 0

    payload = json.loads((output_dir / "retrieval_eval.json").read_text(encoding="utf-8"))
    assert payload["query_count"] == 2
    assert payload["top5_exact_target_query_count"] == 2
    assert payload["top5_exact_target_rate"] == 1.0


def test_retrieval_eval_counts_exact_target_miss_in_denominator(tmp_path, monkeypatch) -> None:
    module = _load_script()
    report_path = tmp_path / "retrieval_top5_report.json"
    report_path.write_text(
        json.dumps(
            {
                "query_count": 2,
                "topk": 5,
                "queries": [
                    {
                        "query_id": "q1",
                        "query": "深圳大学 靳玉乐 教授",
                        "results": [{"rank": i} for i in range(1, 6)],
                        "expected": {
                            "name": "靳玉乐",
                            "institution": "深圳大学",
                        },
                        "machine": {
                            "expected_target_rank": 1,
                            "expected_target_in_topk": True,
                        },
                        "manual": {
                            "relevant_ranks": None,
                            "notes": "",
                        },
                    },
                    {
                        "query_id": "q2",
                        "query": "香港中文大学（深圳） WARSHEL, Arieh 教授",
                        "results": [{"rank": i} for i in range(1, 6)],
                        "expected": {
                            "name": "WARSHEL, Arieh",
                            "institution": "香港中文大学（深圳）",
                        },
                        "machine": {
                            "expected_target_rank": None,
                            "expected_target_in_topk": False,
                        },
                        "manual": {
                            "relevant_ranks": None,
                            "notes": "",
                        },
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "eval"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--judged-report-json",
            str(report_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    code = module.main()
    assert code == 0

    payload = json.loads((output_dir / "retrieval_eval.json").read_text(encoding="utf-8"))
    assert payload["query_count"] == 2
    assert payload["top5_exact_target_query_count"] == 1
    assert payload["top5_exact_target_rate"] == 0.5


def test_retrieval_eval_aggregates_duplicate_target_queries(tmp_path, monkeypatch) -> None:
    module = _load_script()
    report_path = tmp_path / "retrieval_top5_report.json"
    report_path.write_text(
        json.dumps(
            {
                "query_count": 2,
                "topk": 5,
                "queries": [
                    {
                        "query_id": "q1",
                        "query": "清华大学深圳国际研究生院 尤政院士 教授",
                        "results": [{"rank": i} for i in range(1, 6)],
                        "expected": {
                            "name": "尤政院士",
                            "institution": "清华大学深圳国际研究生院",
                        },
                        "machine": {
                            "expected_target_rank": 1,
                            "expected_target_in_topk": True,
                            "expected_target_match_count": 2,
                            "duplicate_expected_target_in_topk": True,
                        },
                        "manual": {
                            "relevant_ranks": None,
                            "notes": "",
                        },
                    },
                    {
                        "query_id": "q2",
                        "query": "南方科技大学 吴亚北 教授",
                        "results": [{"rank": i} for i in range(1, 6)],
                        "expected": {
                            "name": "吴亚北",
                            "institution": "南方科技大学",
                        },
                        "machine": {
                            "expected_target_rank": 1,
                            "expected_target_in_topk": True,
                            "expected_target_match_count": 1,
                            "duplicate_expected_target_in_topk": False,
                        },
                        "manual": {
                            "relevant_ranks": None,
                            "notes": "",
                        },
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "eval"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--judged-report-json",
            str(report_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    code = module.main()
    assert code == 0

    payload = json.loads((output_dir / "retrieval_eval.json").read_text(encoding="utf-8"))
    assert payload["top5_exact_target_query_count"] == 2
    assert payload["top5_duplicate_target_query_count"] == 1
    assert payload["top5_duplicate_target_rate"] == 0.5
