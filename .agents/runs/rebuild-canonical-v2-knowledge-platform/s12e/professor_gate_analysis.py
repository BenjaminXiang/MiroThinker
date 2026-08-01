"""Dry-run analysis of the Canonical V2 professor required-field gate downgrade.

Context (s12c r8 candidate, container canonical-v2-s12c-pg-20260726-r8):

- ``landing.source_record`` holds 1439 professor released objects, but only
  557 professor source identities / 554 current projections exist.  The old
  gate in ``knowledge_build_isolated._selected_fields`` rejected any
  professor missing one of department/email/homepage/title/profile_summary,
  which dropped exactly 882 records (e.g. 王学谦, missing department).
- The gate is now downgraded: name+institution are the only hard
  requirements; the other historically required fields degrade to quality
  signals with explicit fallbacks.

This script is strictly read-only.  It re-runs both rules over the candidate
database landing rows, cross-checks the replicated old rule against the
actual source-identity diff (must reproduce the 882 exactly), classifies
every record under the new rule, and writes a markdown review report next to
this script.  ``--dry-run`` is accepted for symmetry with the backfill
script; the analysis is always a dry run.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import psycopg

_DEFAULT_DSN = (
    "postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_s12c_20260726_r8"
)
_DEFAULT_SOURCE_BATCH_ID = "s12a-released-objects-full-v1"
_DEGRADABLE_FIELDS = ("department", "email", "homepage", "profile_summary", "title")
_WANG_XUEQIAN = "王学谦"


def _blank(value: Any) -> bool:
    return not isinstance(value, str) or not value.strip()


def _department_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, dict):
        return _blank(value.get("name"))
    return False  # malformed non-str container stays a hard rejection, not a signal


def _core_facts(payload: dict[str, Any]) -> dict[str, Any]:
    payload_json = payload.get("payload_json")
    row = json.loads(payload_json) if isinstance(payload_json, str) else payload
    core = row.get("core_facts")
    summary = row.get("summary_fields")
    return {
        "core": core if isinstance(core, dict) else {},
        "summary": summary if isinstance(summary, dict) else {},
    }


def _field_present(parts: dict[str, dict[str, Any]], field: str) -> bool:
    if field == "profile_summary":
        return not _blank(parts["summary"].get("profile_summary"))
    if field == "department":
        return not _department_missing(parts["core"].get("department"))
    return not _blank(parts["core"].get(field))


def _old_gate_rejected(parts: dict[str, dict[str, Any]]) -> bool:
    """Replicate the pre-downgrade required-field gate for verification."""
    core = parts["core"]
    name = core.get("name") or core.get("canonical_name_zh")
    if _blank(name) or _blank(core.get("institution")):
        return True
    department = core.get("department")
    if _department_missing(department) or (
        department is not None and not isinstance(department, (str, dict))
    ):
        return True
    return any(
        not _field_present(parts, field)
        for field in ("email", "homepage", "profile_summary", "title")
    )


def _new_gate_decision(
    parts: dict[str, dict[str, Any]],
) -> tuple[bool, tuple[str, ...], str | None]:
    """Return (admitted, quality_signals, rejection_reason) under the new rule."""
    core = parts["core"]
    name = core.get("name") or core.get("canonical_name_zh")
    if _blank(name):
        return False, (), "missing name/canonical_name_zh"
    if _blank(core.get("institution")):
        return False, (), "missing institution"
    department = core.get("department")
    if department is not None and not isinstance(department, (str, dict)):
        return False, (), "malformed core_facts.department"
    signals = tuple(
        f"missing_{field}"
        for field in _DEGRADABLE_FIELDS
        if not _field_present(parts, field)
    )
    return True, signals, None


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=_DEFAULT_DSN)
    parser.add_argument("--source-batch-id", default=_DEFAULT_SOURCE_BATCH_ID)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(__file__).resolve().with_name("professor-gate-report.md"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No-op; the analysis is always read-only.",
    )
    options = parser.parse_args(args)

    with psycopg.connect(options.dsn) as connection:
        connection.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        landing_rows = connection.execute(
            "SELECT record_id, payload FROM landing.source_record "
            "WHERE source_batch_id = %s AND payload->>'object_type' = 'professor'",
            (options.source_batch_id,),
        ).fetchall()
        admitted_object_ids = {
            row[0]
            for row in connection.execute(
                "SELECT normalized_keys->>'historical_source_id' "
                "FROM knowledge.source_identity WHERE entity_type = 'professor'"
            ).fetchall()
        }
        funnel = {
            "source_identity": connection.execute(
                "SELECT count(*) FROM knowledge.source_identity "
                "WHERE entity_type = 'professor'"
            ).fetchone()[0],
            "canonical_identity": connection.execute(
                "SELECT count(*) FROM knowledge.canonical_identity "
                "WHERE entity_type = 'professor'"
            ).fetchone()[0],
            "inclusion_decision": connection.execute(
                "SELECT count(*) FROM knowledge.domain_inclusion_decision "
                "WHERE entity_type = 'professor'"
            ).fetchone()[0],
            "current_projection": connection.execute(
                "SELECT count(*) FROM professor.current_projection"
            ).fetchone()[0],
        }

    records: list[dict[str, Any]] = []
    for record_id, payload in landing_rows:
        parts = _core_facts(payload)
        core = parts["core"]
        citation_count = core.get("citation_count")
        records.append(
            {
                "record_id": record_id,
                "object_id": payload.get("id"),
                "name": core.get("name") or core.get("canonical_name_zh"),
                "institution": core.get("institution"),
                "parts": parts,
                "citation_count": citation_count
                if isinstance(citation_count, int)
                and not isinstance(citation_count, bool)
                else None,
            }
        )

    # Old-rule replication must exactly reproduce the source-identity diff.
    old_rejected = {r["object_id"] for r in records if _old_gate_rejected(r["parts"])}
    db_rejected = {r["object_id"] for r in records} - admitted_object_ids
    replication_matches_db = old_rejected == db_rejected

    admitted_clean: list[dict[str, Any]] = []
    admitted_with_signals: list[dict[str, Any]] = []
    still_rejected: list[dict[str, Any]] = []
    signal_counter: Counter[str] = Counter()
    wang_xueqian: list[dict[str, Any]] = []
    for record in records:
        admitted, signals, reason = _new_gate_decision(record["parts"])
        record["admitted"] = admitted
        record["signals"] = signals
        record["rejection_reason"] = reason
        if not admitted:
            still_rejected.append(record)
        elif signals:
            admitted_with_signals.append(record)
            signal_counter.update(signals)
        else:
            admitted_clean.append(record)
        if record["name"] and _WANG_XUEQIAN in str(record["name"]):
            wang_xueqian.append(record)

    previously_rejected_admitted = [
        r for r in admitted_with_signals if r["object_id"] in db_rejected
    ]
    backfill_candidates = sorted(
        admitted_with_signals,
        key=lambda r: (r["citation_count"] is not None, r["citation_count"] or 0),
        reverse=True,
    )[:20]

    def _row(record: dict[str, Any]) -> str:
        missing = ", ".join(record["signals"]) or "-"
        return (
            f"| {record['object_id']} | {record['name']} | {record['institution']} "
            f"| {missing} | {record['citation_count'] if record['citation_count'] is not None else '-'} |"
        )

    lines = [
        "# Professor gate 降级 dry-run 复核报告（s12e）",
        "",
        f"- 数据库: `{options.dsn}`（只读事务）",
        f"- 源批次: `{options.source_batch_id}`",
        "",
        "## 现场漏斗（DB 实测）",
        "",
        "| 阶段 | 记录数 |",
        "| --- | ---: |",
        f"| landing.source_record (professor) | {len(records)} |",
        f"| knowledge.source_identity | {funnel['source_identity']} |",
        f"| knowledge.canonical_identity | {funnel['canonical_identity']} |",
        f"| knowledge.domain_inclusion_decision | {funnel['inclusion_decision']} |",
        f"| professor.current_projection | {funnel['current_projection']} |",
        "",
        f"旧 gate 拒掉（1439 - source_identity 差集）: **{len(db_rejected)}** 条。",
        f"脚本复现旧规则拒掉: **{len(old_rejected)}** 条；与 DB 差集完全一致: "
        f"**{'是' if replication_matches_db else '否（需人工复核）'}**。",
        "",
        "## 新规则 dry-run 分类（硬条件 = name + institution）",
        "",
        "| 分类 | 记录数 |",
        "| --- | ---: |",
        f"| 放行（无质量信号） | {len(admitted_clean)} |",
        f"| 放行（带质量信号，需回填候选） | {len(admitted_with_signals)} |",
        f"| 仍拒（缺 name/institution 或字段格式错） | {len(still_rejected)} |",
        "",
        f"旧被拒 882 条中按新规则放行: **{len(previously_rejected_admitted)}** 条。",
        "",
        "## 质量信号分布（放行但缺字段）",
        "",
        "| 信号 | 记录数 |",
        "| --- | ---: |",
        *(
            f"| `{signal}` | {count} |"
            for signal, count in signal_counter.most_common()
        ),
        "",
        "注：同一记录可命中多个信号（如同时缺 department 与 title）。",
        "",
        "## 回填候选（按 citation_count 降序，前 20）",
        "",
        "| object_id | 姓名 | 机构 | 缺失字段 | citation_count |",
        "| --- | --- | --- | --- | ---: |",
        *(_row(record) for record in backfill_candidates),
        "",
        "## 王学谦 核验",
        "",
    ]
    if wang_xueqian:
        for record in wang_xueqian:
            lines.append(
                f"- `{record['object_id']}`（{record['name']}，"
                f"{record['institution']}）：新规则"
                f"{'**放行**' if record['admitted'] else '**仍拒**'}"
                + (
                    f"，信号: {', '.join(record['signals'])}"
                    if record["signals"]
                    else "，无质量信号"
                )
                + (
                    f"；此前被旧 gate 拒掉: {'是' if record['object_id'] in db_rejected else '否'}"
                )
            )
    else:
        lines.append("- 未在教授源记录中找到王学谦（需人工复核）。")
    lines += [
        "",
        "## 仍拒样例与理由（前 10）",
        "",
        "| object_id | 姓名 | 机构 | 理由 |",
        "| --- | --- | --- | --- |",
        *(
            f"| {r['object_id']} | {r['name']} | {r['institution']} "
            f"| {r['rejection_reason']} |"
            for r in still_rejected[:10]
        ),
        "",
        "## 实现备注",
        "",
        "- gate 位于 `knowledge_build_isolated._selected_fields` 教授分支（非"
        " legacy `data_agents/professor/release.py`）。",
        "- 放行占位值（`Not supplied by the historical source.`）不参与身份键"
        "（name/institution/department/email/homepage keys）与论文作者归因"
        "签名，避免同名不同人错误合并。",
        "- 缺字段记录同时写入 ops.knowledge_gap（`quality_signals` +"
        " affected_paths），供 Task 7 回填队列使用。",
        "",
    ]
    options.report.write_text("\n".join(lines), encoding="utf-8")

    print(f"professor landing records: {len(records)}")
    print(f"old-gate rejected (DB diff): {len(db_rejected)}")
    print(
        f"old-rule replication matches DB diff: {replication_matches_db} "
        f"({len(old_rejected)} replicated)"
    )
    print(f"new-rule admitted clean: {len(admitted_clean)}")
    print(f"new-rule admitted with signals: {len(admitted_with_signals)}")
    print(f"new-rule still rejected: {len(still_rejected)}")
    print(
        f"王学谦: {[(r['object_id'], r['admitted'], r['signals']) for r in wang_xueqian]}"
    )
    print(f"report written: {options.report}")
    if not replication_matches_db:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
