#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Audit released_objects.db against workbook-driven entity coverage expectations."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "apps" / "miroflow-agent"))

from src.data_agents.contracts import ReleasedObject
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


def _default_db_path() -> Path:
    return _REPO_ROOT / "logs" / "data_agents" / "released_objects.db"


def _default_output_dir() -> Path:
    return _REPO_ROOT / "logs" / "data_agents" / "workbook_coverage_audit"


def _default_workbook_path() -> Path:
    return _REPO_ROOT / "docs" / "测试集答案.xlsx"


QUESTION_SPECS: list[dict[str, Any]] = [
    {
        "id": "q1",
        "title": "介绍清华的丁文伯 -> 他是否有参与哪些企业的创立",
        "blocking_check_ids": ("professor_exists", "professor_company_link"),
        "checks": [
            {"id": "professor_exists", "type": "object_exists", "domain": "professor", "query": "丁文伯"},
            {"id": "company_exists", "type": "object_exists", "domain": "company", "query": "深圳无界智航科技有限公司"},
            {"id": "professor_company_link", "type": "professor_company_link", "professor": "丁文伯", "company": "深圳无界智航科技有限公司"},
        ],
    },
    {
        "id": "q2",
        "title": "酒店送餐机器人供应商及深圳筛选",
        "checks": [
            {"id": "pudu_exists", "type": "object_exists", "domain": "company", "query": "普渡科技"},
            {"id": "kepler_exists", "type": "object_exists", "domain": "company", "query": "开普勒机器人"},
            {"id": "yunji_exists", "type": "object_exists", "domain": "company", "query": "云迹科技"},
            {"id": "qinglang_exists", "type": "object_exists", "domain": "company", "query": "擎朗智能"},
            {"id": "segway_exists", "type": "object_exists", "domain": "company", "query": "九号机器人"},
        ],
    },
    {"id": "q3", "title": "深圳涉黄赌毒地点", "status_override": "out_of_scope", "checks": []},
    {
        "id": "q4",
        "title": "无界智航企业信息与同名消歧",
        "checks": [
            {"id": "company_exists", "type": "object_exists", "domain": "company", "query": "深圳无界智航科技有限公司"}
        ],
    },
    {
        "id": "q5",
        "title": "PCB 打板推荐与深圳企业筛选",
        "checks": [
            {"id": "jlc_exists", "type": "object_exists", "domain": "company", "query": "嘉立创"},
            {"id": "scc_exists", "type": "object_exists", "domain": "company", "query": "深南电路"},
            {"id": "yibo_exists", "type": "object_exists", "domain": "company", "query": "一博科技"},
        ],
    },
    {
        "id": "q6",
        "title": "特定论文 pFedGPA 的详情与链接",
        "checks": [
            {"id": "paper_exists", "type": "object_exists", "domain": "paper", "query": "pFedGPA"}
        ],
    },
    {
        "id": "q7",
        "title": "早稻田背景且在深圳做机器人行业的企业家",
        "checks": [
            {"id": "pacsense_exists", "type": "object_exists", "domain": "company", "query": "帕西尼感知科技（深圳）有限公司"},
            {"id": "steprobot_exists", "type": "object_exists", "domain": "company", "query": "深圳市迈步机器人科技有限公司"},
        ],
    },
    {
        "id": "q8",
        "title": "华力创科学企业信息、产量特点、市场竞争力",
        "checks": [
            {"id": "company_exists", "type": "object_exists", "domain": "company", "query": "华力创科学（深圳）有限公司"}
        ],
    },
    {
        "id": "q9",
        "title": "王学谦评价及是否属于大牛",
        "checks": [
            {"id": "professor_exists", "type": "object_exists", "domain": "professor", "query": "王学谦"}
        ],
    },
    {
        "id": "q10",
        "title": "爱博合创企业情况、创始人信息、市场评价",
        "checks": [
            {"id": "company_exists", "type": "object_exists", "domain": "company", "query": "深圳爱博合创医疗机器人有限公司"}
        ],
    },
    {
        "id": "q11",
        "title": "具身智能厂商数据路线分类",
        "checks": [
            {"id": "real_route_exists", "type": "company_field_contains_any", "field": "data_route_types", "expected": "real_data"},
            {"id": "synthetic_route_exists", "type": "company_field_contains_any", "field": "data_route_types", "expected": "synthetic_data"},
        ],
    },
    {
        "id": "q12",
        "title": "真实数据采集路线具体方式",
        "checks": [
            {"id": "teleoperation_exists", "type": "company_field_contains_any", "field": "real_data_methods", "expected": "teleoperation"},
            {"id": "motion_capture_exists", "type": "company_field_contains_any", "field": "real_data_methods", "expected": "motion_capture"},
            {"id": "real_world_execution_exists", "type": "company_field_contains_any", "field": "real_data_methods", "expected": "real_world_execution"},
        ],
    },
    {
        "id": "q13",
        "title": "模拟器生成数据路线具体方式",
        "checks": [
            {"id": "physics_simulation_exists", "type": "company_field_contains_any", "field": "synthetic_data_methods", "expected": "physics_simulation"},
            {"id": "generative_model_exists", "type": "company_field_contains_any", "field": "synthetic_data_methods", "expected": "generative_model"},
            {"id": "rule_based_generation_exists", "type": "company_field_contains_any", "field": "synthetic_data_methods", "expected": "rule_based_generation"},
        ],
    },
    {
        "id": "q14",
        "title": "深圳具身智能/灵巧手厂商数据路线",
        "checks": [
            {"id": "agibot_route_exists", "type": "company_field_nonempty", "query": "自变量机器人", "field": "data_route_types"},
            {"id": "cyborg_route_exists", "type": "company_field_nonempty", "query": "赛博格机器人", "field": "data_route_types"},
            {"id": "xspark_route_exists", "type": "company_field_nonempty", "query": "无界智航", "field": "data_route_types"},
            {"id": "saigan_route_exists", "type": "company_field_nonempty", "query": "赛感科技", "field": "data_route_types"},
        ],
    },
    {
        "id": "q15",
        "title": "具身智能合成数据实现方法与代表厂商",
        "checks": [
            {"id": "crossdim_synth_exists", "type": "company_field_nonempty", "query": "跨维", "field": "synthetic_data_methods"},
            {"id": "guanglun_synth_exists", "type": "company_field_nonempty", "query": "光轮智能", "field": "synthetic_data_methods"},
            {"id": "yinhe_synth_exists", "type": "company_field_nonempty", "query": "银河通用", "field": "synthetic_data_methods"},
            {"id": "qunhe_synth_exists", "type": "company_field_nonempty", "query": "群核科技", "field": "synthetic_data_methods"},
        ],
    },
    {
        "id": "q16",
        "title": "运动层与操作层的数据需求差异及采集方式",
        "checks": [
            {"id": "movement_need_exists", "type": "company_field_contains_any", "field": "movement_data_needs", "expected": "proprioception"},
            {"id": "operation_need_exists", "type": "company_field_contains_any", "field": "operation_data_needs", "expected": "tactile_interaction"},
            {"id": "mixed_collection_exists", "type": "company_field_contains_any", "field": "real_data_methods", "expected": "teleoperation"},
        ],
    },
    {
        "id": "q17",
        "title": "优必选有哪些专利 -> 特定专利号 CN117873146A 详情",
        "checks": [
            {"id": "ubtech_patents_exist", "type": "object_exists", "domain": "patent", "query": "深圳市优必选科技股份有限公司"},
            {"id": "exact_patent_exists", "type": "object_exists", "domain": "patent", "query": "CN117873146A"},
        ],
    },
]


def _normalize(text: str) -> str:
    return (text or "").casefold().strip()


def _normalize_company_identity(text: str) -> str:
    normalized = _normalize(text)
    normalized = normalized.translate(str.maketrans({"（": "(", "）": ")", "-": "", "_": "", " ": ""}))
    normalized = re.sub(r"\((深圳|北京|上海|杭州|广州)\)", "", normalized)
    normalized = re.sub(r"^(深圳市|深圳|上海市|上海|北京市|北京|广州市|广州|杭州市|杭州)", "", normalized)
    for suffix in ("有限责任公司", "股份有限公司", "有限公司", "股份公司", "公司", "集团"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def _load_objects_by_domain(db_path: Path) -> tuple[dict[str, list[ReleasedObject]], dict[str, int]]:
    store = SqliteReleasedObjectStore(db_path)
    counts = store.count_by_domain()
    objects_by_domain = {domain: store.list_domain_objects(domain) for domain in counts}
    return objects_by_domain, counts


def _payload(obj: ReleasedObject) -> dict[str, Any]:
    return obj.model_dump(mode="json")


def _company_identity_texts(obj: ReleasedObject) -> list[str]:
    payload = _payload(obj)
    core_facts = payload.get("core_facts", {})
    return [text for text in [payload.get("display_name", ""), core_facts.get("name"), core_facts.get("normalized_name")] if text]


def _professor_identity_texts(obj: ReleasedObject) -> list[str]:
    payload = _payload(obj)
    core_facts = payload.get("core_facts", {})
    return [text for text in [payload.get("display_name", ""), core_facts.get("name")] if text]


def _paper_identity_texts(obj: ReleasedObject) -> list[str]:
    payload = _payload(obj)
    core_facts = payload.get("core_facts", {})
    return [
        text
        for text in [
            payload.get("display_name", ""),
            core_facts.get("title"),
            core_facts.get("title_zh"),
            core_facts.get("doi"),
            core_facts.get("arxiv_id"),
        ]
        if text
    ]


def _patent_identity_texts(obj: ReleasedObject) -> list[str]:
    payload = _payload(obj)
    core_facts = payload.get("core_facts", {})
    return [
        text
        for text in [
            payload.get("display_name", ""),
            core_facts.get("title"),
            core_facts.get("patent_number"),
        ]
        if text
    ]


def _patent_relation_texts(obj: ReleasedObject) -> list[str]:
    payload = _payload(obj)
    core_facts = payload.get("core_facts", {})
    values: list[str] = []
    for key in ("applicants", "assignees", "inventors"):
        for item in core_facts.get(key, []):
            if item:
                values.append(str(item))
    return values


_SAFE_COMPANY_TAILS = {
    "科技",
    "智能",
    "技术",
    "电路",
    "股份",
    "科技集团",
    "智能科技",
    "机器人科技",
    "智能数字科技",
    "数字科技",
}


def _company_match(query: str, text: str) -> bool:
    q = _normalize_company_identity(query)
    t = _normalize_company_identity(text)
    if not q or not t:
        return False
    if t == q:
        return True
    if t.startswith(q):
        return t[len(q):] in _SAFE_COMPANY_TAILS
    return False


def _company_field_values(obj: ReleasedObject, field: str) -> list[str]:
    payload = _payload(obj)
    core_facts = payload.get("core_facts", {})
    value = core_facts.get(field)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def _company_field_nonempty(
    objects_by_domain: dict[str, list[ReleasedObject]],
    *,
    query: str,
    field: str,
) -> bool:
    for obj in objects_by_domain.get("company", []):
        if not any(_company_match(query, text) for text in _company_identity_texts(obj)):
            continue
        if _company_field_values(obj, field):
            return True
    return False


def _company_field_contains_any(
    objects_by_domain: dict[str, list[ReleasedObject]],
    *,
    field: str,
    expected: str,
) -> bool:
    needle = _normalize(expected)
    for obj in objects_by_domain.get("company", []):
        for value in _company_field_values(obj, field):
            if _normalize(value) == needle:
                return True
    return False


def _object_exists(objects_by_domain: dict[str, list[ReleasedObject]], *, domain: str, query: str) -> bool:
    if domain == "company":
        return any(
            any(_company_match(query, text) for text in _company_identity_texts(obj))
            for obj in objects_by_domain.get(domain, [])
        )
    if domain == "professor":
        needle = _normalize(query)
        return any(
            any(_normalize(text) == needle for text in _professor_identity_texts(obj))
            for obj in objects_by_domain.get(domain, [])
        )
    if domain == "paper":
        needle = _normalize(query)
        return any(
            any(needle in _normalize(text) for text in _paper_identity_texts(obj))
            for obj in objects_by_domain.get(domain, [])
        )
    if domain == "patent":
        needle = _normalize(query)
        for obj in objects_by_domain.get(domain, []):
            if any(_normalize(text) == needle or needle in _normalize(text) for text in _patent_identity_texts(obj)):
                return True
            if any(_company_match(query, text) for text in _patent_relation_texts(obj)):
                return True
        return False
    raise ValueError(f"Unsupported domain for workbook coverage audit: {domain}")


def _professor_company_link_exists(objects_by_domain: dict[str, list[ReleasedObject]], *, professor: str, company: str) -> bool:
    professor_name = _normalize(professor)
    for obj in objects_by_domain.get("professor", []):
        payload = _payload(obj)
        core_facts = payload.get("core_facts", {})
        if _normalize(str(payload.get("display_name") or core_facts.get("name") or "")) != professor_name:
            continue
        for role in core_facts.get("company_roles", []):
            if _company_match(company, role.get("company_name", "")):
                return True
    return False


def _run_check(check: dict[str, Any], objects_by_domain: dict[str, list[ReleasedObject]]) -> bool:
    check_type = check["type"]
    if check_type == "object_exists":
        return _object_exists(objects_by_domain, domain=check["domain"], query=check["query"])
    if check_type == "professor_company_link":
        return _professor_company_link_exists(objects_by_domain, professor=check["professor"], company=check["company"])
    if check_type == "company_field_nonempty":
        return _company_field_nonempty(objects_by_domain, query=check["query"], field=check["field"])
    if check_type == "company_field_contains_any":
        return _company_field_contains_any(objects_by_domain, field=check["field"], expected=check["expected"])
    raise ValueError(f"Unsupported workbook coverage check type: {check_type}")


def _question_status(*, check_results: list[dict[str, Any]], blocking_check_ids: tuple[str, ...] = ()) -> str:
    if not check_results:
        return "fail"
    passed_ids = {item["id"] for item in check_results if item["passed"]}
    if len(passed_ids) == len(check_results):
        return "pass"
    if blocking_check_ids and not all(check_id in passed_ids for check_id in blocking_check_ids):
        return "fail"
    if passed_ids:
        return "partial"
    return "fail"


def build_workbook_coverage_report(db_path: Path | str) -> dict[str, Any]:
    db_path = Path(db_path)
    objects_by_domain, domain_counts = _load_objects_by_domain(db_path)
    question_results: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()

    for spec in QUESTION_SPECS:
        override_status = spec.get("status_override")
        if override_status is not None:
            result = {
                "id": spec["id"],
                "title": spec["title"],
                "status": override_status,
                "passed_checks": 0,
                "failed_checks": 0,
                "checks": [],
            }
            question_results.append(result)
            status_counts[override_status] += 1
            continue

        check_results = [
            {"id": check["id"], "type": check["type"], "passed": _run_check(check, objects_by_domain)}
            for check in spec["checks"]
        ]
        status = _question_status(check_results=check_results, blocking_check_ids=tuple(spec.get("blocking_check_ids", ())))
        passed_checks = sum(1 for item in check_results if item["passed"])
        failed_checks = len(check_results) - passed_checks
        result = {
            "id": spec["id"],
            "title": spec["title"],
            "status": status,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "checks": check_results,
        }
        question_results.append(result)
        status_counts[status] += 1

    return {
        "db_path": str(db_path),
        "workbook_path": str(_default_workbook_path()),
        "domain_counts": domain_counts,
        "question_count": len(question_results),
        "status_counts": dict(status_counts),
        "questions": question_results,
    }


def _build_markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# Workbook Coverage Audit",
        "",
        "## Inputs",
        f"- DB: `{report['db_path']}`",
        f"- Workbook: `{report['workbook_path']}`",
        "",
        "## Domain Counts",
    ]
    for domain, count in sorted(report["domain_counts"].items()):
        lines.append(f"- `{domain}`: `{count}`")
    lines.extend(["", "## Status Counts"])
    for status, count in sorted(report["status_counts"].items()):
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Questions"])
    for question in report["questions"]:
        lines.append(
            f"- `{question['id']}` `{question['status']}` "
            f"(passed `{question['passed_checks']}`, failed `{question['failed_checks']}`): "
            f"{question['title']}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit workbook-driven coverage against released_objects.db.")
    parser.add_argument("--db-path", type=Path, default=_default_db_path())
    parser.add_argument("--output-dir", type=Path, default=_default_output_dir())
    args = parser.parse_args()

    if not args.db_path.exists():
        print(json.dumps({"error": f"db not found: {args.db_path}"}, ensure_ascii=False))
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = build_workbook_coverage_report(args.db_path)
    json_path = args.output_dir / "workbook_coverage_report.json"
    md_path = args.output_dir / "workbook_coverage_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown_summary(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    print(f"JSON summary saved to: {json_path}")
    print(f"Markdown summary saved to: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
