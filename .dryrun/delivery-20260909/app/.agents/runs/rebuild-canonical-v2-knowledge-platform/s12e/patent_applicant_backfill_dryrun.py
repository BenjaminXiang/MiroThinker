"""Dry-run of the patent applicant → release company backfill (s12e).

Context (s12c r8 candidate, container canonical-v2-s12c-pg-20260726-r8):

- ``landing.source_record`` holds 1931 patent released objects; only 76 have
  a non-empty ``core_facts.company_ids`` and therefore produced
  ``patent_has_applicant`` typed seeds.  The remaining 1855 patents carry
  applicant name strings that were never normalized to release companies.
- The relationship audit verified that 45 of those applicant names exactly
  match published company names (普渡科技、奇勃科技、盈合机器人、交浦科技 …),
  a zero-false-positive recovery of 76 → 121 links (+59%).
- ``apps/miroflow-agent/src/data_agents/canonical_v2/patent_applicant_linking.py``
  implements the matcher: exact display-name lane, normalized lane (city
  prefixes / company suffixes stripped on both sides), and a hard
  uniqueness-abstain guard on distinct canonical companies.

This script is strictly read-only.  It connects with
``default_transaction_read_only=on``, issues only SELECT statements, re-runs
the matcher over the candidate database landing rows, cross-checks that the
exact lane reproduces the audited 45 patents, and writes a markdown review
report next to this script.  No database row, index, repo file, or running
service is modified.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "apps" / "miroflow-agent" / "src"))

from src.data_agents.canonical_v2.patent_applicant_linking import (  # noqa: E402
    CompanyNameEntry,
    build_company_name_index,
    resolve_patent_applicant_links,
)

_DEFAULT_DSN = (
    "postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_s12c_20260726_r8"
)
_REPORT_PATH = Path(__file__).with_name("patent-applicant-backfill-dryrun.md")
_AUDIT_EXACT_PATENT_COUNT = 45
_EXPECTED_COMPANY_COUNT = 1037
_EXISTING_LINK_COUNT = 76

_NON_COMPANY_MARKERS = (
    "大学",
    "学院",
    "研究院",
    "研究所",
    "实验室",
    "医院",
    "协会",
    "学会",
)
_COMPANY_MARKERS = ("公司", "有限", "股份", "集团", "厂", "企业")


def _record(payload: dict[str, Any]) -> dict[str, Any]:
    payload_json = payload.get("payload_json")
    if isinstance(payload_json, str):
        return json.loads(payload_json)
    return payload


def _classify_unmatched(applicant_name: str) -> str:
    """Report-only bucket for abstained no-match applicants."""

    if any(marker in applicant_name for marker in _NON_COMPANY_MARKERS):
        return "abstained_non_company"
    stripped = applicant_name.strip()
    if len(stripped) <= 4 and not any(
        marker in stripped for marker in _COMPANY_MARKERS
    ):
        return "abstained_suspected_person"
    return "abstained_company_not_in_release"


def _load_rows(dsn: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    with (
        psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT payload FROM landing.source_record")
        payloads = [row[0] for row in cur.fetchall()]
        cur.execute(
            "SELECT source_identity_id, canonical_identity_id "
            "FROM knowledge.current_source_identity_assignment"
        )
        assignments = dict(cur.fetchall())
    return payloads, assignments


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=_DEFAULT_DSN)
    parser.add_argument("--output", type=Path, default=_REPORT_PATH)
    args = parser.parse_args()

    payloads, assignments = _load_rows(args.dsn)

    company_entries: list[CompanyNameEntry] = []
    unresolved_patents: list[tuple[str, str, list[str]]] = []
    for payload in payloads:
        record = _record(payload)
        core = record.get("core_facts")
        if not isinstance(core, dict):
            continue
        object_type = record.get("object_type")
        object_id = record.get("id")
        if not isinstance(object_id, str):
            continue
        if object_type == "company":
            canonical_id = assignments.get(f"source-released-object:{object_id}")
            if canonical_id is None:
                continue
            names = tuple(
                name
                for name in (core.get("name"), core.get("normalized_name"))
                if isinstance(name, str) and name.strip()
            )
            company_entries.append(
                CompanyNameEntry(
                    object_id=object_id,
                    canonical_identity_id=canonical_id,
                    names=names,
                )
            )
        elif object_type == "patent":
            company_ids = core.get("company_ids")
            if isinstance(company_ids, list) and company_ids:
                continue
            applicants = [
                name.strip()
                for name in (core.get("applicants") or [])
                if isinstance(name, str) and name.strip()
            ]
            display_name = record.get("display_name")
            unresolved_patents.append(
                (
                    object_id,
                    display_name if isinstance(display_name, str) else "",
                    applicants,
                )
            )

    index = build_company_name_index(company_entries)
    company_names = {
        entry.object_id: entry.names[0] for entry in company_entries if entry.names
    }

    accepted: list[dict[str, str]] = []
    abstained_ambiguous: list[tuple[str, str, tuple[str, ...]]] = []
    unmatched: Counter[str] = Counter()
    unmatched_examples: dict[str, list[tuple[str, str]]] = {}
    seen_links: set[tuple[str, str]] = set()
    for object_id, display_name, applicants in sorted(unresolved_patents):
        patent_canonical_id = assignments.get(f"source-released-object:{object_id}", "")
        for resolution in resolve_patent_applicant_links(
            applicant_names=applicants, index=index
        ):
            if resolution.status == "accepted":
                link = (object_id, resolution.company_canonical_identity_id or "")
                if link in seen_links:
                    continue
                seen_links.add(link)
                accepted.append(
                    {
                        "patent_object_id": object_id,
                        "patent_canonical_id": patent_canonical_id,
                        "patent_title": display_name,
                        "applicant_name": resolution.applicant_name,
                        "company_object_id": resolution.company_object_id or "",
                        "company_canonical_id": (
                            resolution.company_canonical_identity_id or ""
                        ),
                        "company_name": company_names.get(
                            resolution.company_object_id or "", ""
                        ),
                        "match_kind": resolution.match_kind or "",
                    }
                )
            elif resolution.status == "abstained_ambiguous":
                abstained_ambiguous.append(
                    (
                        object_id,
                        resolution.applicant_name,
                        resolution.candidate_canonical_identity_ids,
                    )
                )
            else:
                bucket = _classify_unmatched(resolution.applicant_name)
                unmatched[bucket] += 1
                unmatched_examples.setdefault(bucket, []).append(
                    (object_id, resolution.applicant_name)
                )

    exact_patents = {
        item["patent_object_id"] for item in accepted if item["match_kind"] == "exact"
    }
    normalized_patents = {
        item["patent_object_id"]
        for item in accepted
        if item["match_kind"] == "normalized"
    }
    accepted_patents = {item["patent_object_id"] for item in accepted}
    total_applicants = sum(len(applicants) for _, _, applicants in unresolved_patents)

    checks = [
        (
            "released companies indexed",
            len(company_entries) == _EXPECTED_COMPANY_COUNT,
            str(len(company_entries)),
        ),
        (
            "unresolved patents scanned",
            len(unresolved_patents) == 1855,
            str(len(unresolved_patents)),
        ),
        (
            "exact-lane patents reproduce the audited 45",
            len(exact_patents) == _AUDIT_EXACT_PATENT_COUNT,
            str(len(exact_patents)),
        ),
        (
            "every accepted link resolves to one known canonical company",
            all(
                item["company_canonical_id"]
                and item["company_canonical_id"]
                in {entry.canonical_identity_id for entry in company_entries}
                for item in accepted
            ),
            str(len({item["company_canonical_id"] for item in accepted})),
        ),
        (
            "zero ambiguous abstains",
            not abstained_ambiguous,
            str(len(abstained_ambiguous)),
        ),
    ]

    lines: list[str] = []
    lines.append("# 专利申请人→发布公司回填 dry-run（s12e）")
    lines.append("")
    lines.append(
        "- Release: `candidate-s12c-20260726-r8`（DB `miroflow_candidate_s12c_20260726_r8`，容器 `canonical-v2-s12c-pg-20260726-r8`，只读 SELECT，`default_transaction_read_only=on`）"
    )
    lines.append(
        "- Matcher: `apps/miroflow-agent/src/data_agents/canonical_v2/patent_applicant_linking.py`（exact + normalized 双通道，canonical 唯一性不足即 abstain）"
    )
    lines.append(
        "- 目标：1855 条 `core_facts.company_ids` 为空的专利（全部 1931 条中 76 条已有链接）"
    )
    lines.append("")
    lines.append("## 结果汇总")
    lines.append("")
    lines.append("| 指标 | 数量 |")
    lines.append("|---|---|")
    lines.append(f"| 扫描未解析专利 | {len(unresolved_patents)} |")
    lines.append(f"| 申请人名总数 | {total_applicants} |")
    lines.append(f"| 索引发布公司 | {len(company_entries)} |")
    lines.append(f"| **接受的新链接（patent×company 去重）** | **{len(accepted)}** |")
    lines.append(
        f"| 其中 exact 通道 | {sum(1 for item in accepted if item['match_kind'] == 'exact')} |"
    )
    lines.append(
        f"| 其中 normalized 通道 | {sum(1 for item in accepted if item['match_kind'] == 'normalized')} |"
    )
    lines.append(
        f"| 覆盖专利数 | {len(accepted_patents)}（exact {len(exact_patents)} / normalized-only {len(normalized_patents - exact_patents)}） |"
    )
    lines.append(
        f"| 覆盖公司数 | {len({item['company_canonical_id'] for item in accepted})} |"
    )
    lines.append(f"| abstain-ambiguous | {len(abstained_ambiguous)} |")
    for bucket in (
        "abstained_non_company",
        "abstained_suspected_person",
        "abstained_company_not_in_release",
    ):
        lines.append(f"| abstain：{bucket} | {unmatched.get(bucket, 0)} |")
    lines.append(
        f"| 投影后 patent_has_applicant | {_EXISTING_LINK_COUNT} → {_EXISTING_LINK_COUNT + len(accepted)} |"
    )
    lines.append("")
    lines.append("## 一致性校验")
    lines.append("")
    for label, ok, detail in checks:
        lines.append(f"- [{'x' if ok else ' '}] {label}（{detail}）")
    lines.append("")
    lines.append("## 接受链接全量清单")
    lines.append("")
    lines.append("| 专利 | 专利标题 | 申请人名 | 命中公司 | 公司 canonical | 通道 |")
    lines.append("|---|---|---|---|---|---|")
    for item in sorted(accepted, key=lambda entry: entry["patent_object_id"]):
        lines.append(
            f"| {item['patent_object_id']} | {item['patent_title']} | {item['applicant_name']} "
            f"| {item['company_name']} | {item['company_canonical_id']} | {item['match_kind']} |"
        )
    lines.append("")
    lines.append("## abstain-ambiguous（唯一性不足，全部放弃）")
    lines.append("")
    if abstained_ambiguous:
        for object_id, name, candidates in abstained_ambiguous:
            lines.append(f"- {object_id} 「{name}」候选：{', '.join(candidates)}")
    else:
        lines.append("无。")
    lines.append("")
    lines.append("## abstain 分类示例（每类至多 10 例）")
    lines.append("")
    bucket_labels = {
        "abstained_non_company": "非公司实体（高校/研究院/医院/协会等）",
        "abstained_suspected_person": "疑似个人",
        "abstained_company_not_in_release": "公司但不在发布集",
    }
    for bucket, label in bucket_labels.items():
        lines.append(f"### {label}（{unmatched.get(bucket, 0)}）")
        lines.append("")
        examples = unmatched_examples.get(bucket, [])[:10]
        if not examples:
            lines.append("无。")
        for object_id, name in examples:
            lines.append(f"- {object_id} 「{name}」")
        lines.append("")
    lines.append("---")
    lines.append(
        "声明：本脚本全部操作为只读 SELECT；未修改任何 DB、索引、仓库文件或运行中进程；未触碰 18188 服务。"
    )
    lines.append("")

    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"patents scanned: {len(unresolved_patents)}")
    print(f"applicant names: {total_applicants}")
    print(
        f"accepted new links: {len(accepted)} "
        f"(exact {sum(1 for item in accepted if item['match_kind'] == 'exact')}, "
        f"normalized {sum(1 for item in accepted if item['match_kind'] == 'normalized')})"
    )
    print(f"accepted patents: {len(accepted_patents)}")
    print(f"abstained ambiguous: {len(abstained_ambiguous)}")
    print(f"unmatched: {dict(unmatched)}")
    print(
        f"projection: {_EXISTING_LINK_COUNT} -> {_EXISTING_LINK_COUNT + len(accepted)}"
    )
    failed = [label for label, ok, _ in checks if not ok]
    if failed:
        print(f"FAILED CHECKS: {failed}")
        raise SystemExit(1)
    print(f"report: {args.output}")


if __name__ == "__main__":
    main()
