#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Generate professor retrieval query sets from Phase A audit manifests."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _default_output_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "logs" / "data_agents" / "professor_phase_a_query_set"


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("phase A payload must contain an 'items' list")
    return payload


def _machine_name(item: dict[str, Any]) -> str:
    machine = item.get("machine") or {}
    if isinstance(machine, dict):
        name = str(machine.get("name") or "").strip()
        if name:
            return name
    machine_audit = item.get("machine_audit") or {}
    if isinstance(machine_audit, dict):
        name = str(machine_audit.get("profile_name") or "").strip()
        if name:
            return name
    return ""


def _machine_institution(item: dict[str, Any]) -> str:
    institution = str(item.get("institution") or "").strip()
    if institution:
        return institution
    machine = item.get("machine") or {}
    if isinstance(machine, dict):
        institution = str(machine.get("resolved_institution") or "").strip()
        if institution:
            return institution
    machine_audit = item.get("machine_audit") or {}
    if isinstance(machine_audit, dict):
        institution = str(machine_audit.get("profile_institution") or "").strip()
        if institution:
            return institution
    return ""


def _build_query_item(item: dict[str, Any], *, topk: int) -> dict[str, Any] | None:
    name = _machine_name(item)
    institution = _machine_institution(item)
    if not name or not institution:
        return None

    query_id = str(item.get("audit_id") or item.get("rerun_id") or "").strip()
    if not query_id:
        index = item.get("index")
        if isinstance(index, int) and index > 0:
            query_id = f"q{index:03d}"
        else:
            query_id = name

    return {
        "query_id": query_id,
        "query": f"{institution} {name} 教授",
        "expected_name": name,
        "expected_institution": institution,
        "topk": topk,
    }


def _build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Professor Retrieval Query Set",
        "",
        "## Batch",
        f"- Source json: `{payload['source_json']}`",
        f"- Output dir: `{payload['output_dir']}`",
        f"- Query count: `{payload['query_count']}`",
        f"- Skipped items: `{payload['skipped_count']}`",
        f"- Topk: `{payload['topk']}`",
        "",
        "## Queries",
    ]
    for query in payload["queries"]:
        lines.extend(
            [
                "",
                f"### {query['query_id']}",
                f"- Query: `{query['query']}`",
                f"- Expected name: `{query['expected_name']}`",
                f"- Expected institution: `{query['expected_institution']}`",
                f"- Topk: `{query['topk']}`",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate professor retrieval query sets from Phase A audit manifests."
    )
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=_default_output_dir())
    parser.add_argument("--topk", type=int, default=5)
    args = parser.parse_args()

    if not args.input_json.exists():
        print(json.dumps({"error": f"input json not found: {args.input_json}"}, ensure_ascii=False))
        return 1

    payload = _load_payload(args.input_json)
    items = payload.get("items", [])
    queries = []
    skipped_count = 0
    for item in items:
        if not isinstance(item, dict):
            skipped_count += 1
            continue
        query_item = _build_query_item(item, topk=args.topk)
        if query_item is None:
            skipped_count += 1
            continue
        queries.append(query_item)

    report = {
        "source_json": str(args.input_json),
        "output_dir": str(args.output_dir),
        "query_count": len(queries),
        "skipped_count": skipped_count,
        "topk": args.topk,
        "queries": queries,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "query_set.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = args.output_dir / "query_set.md"
    markdown_path.write_text(_build_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nQuery set saved to: {json_path}")
    print(f"Markdown query set saved to: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
