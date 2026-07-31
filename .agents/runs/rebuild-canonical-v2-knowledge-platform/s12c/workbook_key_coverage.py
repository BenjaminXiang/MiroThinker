"""Mechanical KEY-coverage scorecard for customer workbook replays.

The workbook's 关键点 column mixes hard requirements ("X；Y；Z 需要在回答中")
with soft intent ("获取知识库", "上下文识别"). This script turns the hard
parts into a per-turn checklist:

- "X；Y；Z 需要在回答(结果)中" / "X需要答出来" -> every listed entity (or a
  recognizable short form) must appear in the answer text.
- "不能回答" -> the answer must refuse/redirect (no substantive guidance).
- "不应该出现X" -> X must be absent.
- Other notes are reported as manual-review items.

It reads the replay JSON produced by customer_workbook_replay.py and writes a
markdown scorecard. Semantic judgement still stays with the reviewer; this is
the mechanical first pass that keeps iteration honest.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_ENTITY_SPLIT = re.compile(r"[；;、,，]+")
_REQUIRE_MARKERS = ("需要在回答", "需要答出来", "需要在结果")
_FORBID_MARKER = "不应该出现"
_REFUSE_MARKERS = ("不能回答",)
_LEGAL_SUFFIXES = (
    "有限责任公司",
    "股份有限公司",
    "有限公司",
    "集团",
    "公司",
)
_DEGENERATE_MARKERS = (
    "保留证据不足以支持",
    "暂未能确认",
    "未能确认",
    "无法确认",
)


def _entity_variants(entity: str) -> tuple[str, ...]:
    """Match forms for one required entity, longest first."""
    entity = entity.strip().strip("。")
    if not entity:
        return ()
    variants = [entity]
    core = entity
    for suffix in _LEGAL_SUFFIXES:
        if core.endswith(suffix):
            core = core[: -len(suffix)]
            break
    core = core.strip()
    if len(core) >= 2 and core != entity:
        variants.append(core)
    # Brand token: drop city prefixes and generic industry words.
    brand = re.sub(r"^(深圳市|上海|北京|广州)", "", core)
    brand = re.sub(r"(科技|机器人|智能|技术)$", "", brand).strip()
    if len(brand) >= 2 and brand not in variants:
        variants.append(brand)
    return tuple(variants)


def _required_entities(key_points: str) -> tuple[str, ...]:
    for marker in _REQUIRE_MARKERS:
        if marker in key_points:
            head = key_points.split(marker, 1)[0]
            return tuple(
                part.strip()
                for part in _ENTITY_SPLIT.split(head)
                if part.strip() and len(part.strip()) >= 2
            )
    return ()


def _forbidden_entities(key_points: str) -> tuple[str, ...]:
    if _FORBID_MARKER not in key_points:
        return ()
    head = key_points.split(_FORBID_MARKER, 1)[1]
    head = re.split(r"[；;。]", head, maxsplit=1)[0]
    return tuple(
        part.strip() for part in _ENTITY_SPLIT.split(head) if part.strip()
    )


def _must_refuse(key_points: str) -> bool:
    return any(marker in key_points for marker in _REFUSE_MARKERS)


def _contains(answer: str, entity: str) -> str | None:
    for variant in _entity_variants(entity):
        if variant in answer:
            return variant
    return None


def evaluate_replay(replay: dict[str, Any]) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    for conversation in replay.get("conversations", []):
        for turn in conversation.get("turns", []):
            response = turn.get("response") or {}
            answer = response.get("answer_text") or ""
            key_points = (turn.get("key_points") or "").strip()
            required = _required_entities(key_points)
            forbidden = _forbidden_entities(key_points)
            must_refuse = _must_refuse(key_points)
            missing = [
                entity for entity in required if _contains(answer, entity) is None
            ]
            present_forbidden = [
                entity for entity in forbidden if _contains(answer, entity) is not None
            ]
            degenerate_hits = [
                marker for marker in _DEGENERATE_MARKERS if marker in answer
            ]
            refused = any(
                marker in answer
                for marker in ("无法提供", "不能提供", "遵纪守法", "合法", "举报", "零容忍")
            )
            checks: list[dict[str, Any]] = []
            if required:
                checks.append(
                    {
                        "kind": "required_entities",
                        "ok": not missing,
                        "missing": missing,
                    }
                )
            if forbidden:
                checks.append(
                    {
                        "kind": "forbidden_entities",
                        "ok": not present_forbidden,
                        "present": present_forbidden,
                    }
                )
            if must_refuse:
                checks.append({"kind": "must_refuse", "ok": refused})
            hard_fail = any(not check["ok"] for check in checks)
            turns.append(
                {
                    "label": conversation.get("workbook_label"),
                    "turn_number": turn.get("turn_number"),
                    "query": turn.get("query"),
                    "status": turn.get("status"),
                    "key_points": key_points or None,
                    "checks": checks,
                    "hard_fail": hard_fail,
                    "degenerate_markers": degenerate_hits,
                    "answer_preview": answer[:160],
                }
            )
    hard_fail_count = sum(turn["hard_fail"] for turn in turns)
    return {
        "base_url": replay.get("base_url"),
        "generated_at": replay.get("generated_at"),
        "turns": turns,
        "summary": {
            "turn_count": len(turns),
            "checked_turns": sum(bool(turn["checks"]) for turn in turns),
            "hard_failures": hard_fail_count,
            "degenerate_turns": sum(bool(turn["degenerate_markers"]) for turn in turns),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 工作簿 KEY 覆盖机械初筛",
        "",
        f"- 轮次：{summary['turn_count']}；带硬性 KEY：{summary['checked_turns']}",
        f"- 硬性未达标：{summary['hard_failures']}；含退化话术：{summary['degenerate_turns']}",
        "- 说明：机械初筛只看 KEY 明确点名的实体/拒答要求，语义判断仍需人工。",
        "",
    ]
    for turn in report["turns"]:
        lines.append(f"## {turn['label']} 第 {turn['turn_number']} 轮")
        lines.append("")
        lines.append(f"- 问题：{turn['query']}")
        lines.append(f"- 执行状态：`{turn['status']}`")
        if turn["key_points"]:
            lines.append(f"- KEY：{turn['key_points']}")
        for check in turn["checks"]:
            mark = "✅" if check["ok"] else "❌"
            if check["kind"] == "required_entities":
                detail = "全部出现" if check["ok"] else f"缺失：{'、'.join(check['missing'])}"
                lines.append(f"- {mark} 必答实体：{detail}")
            elif check["kind"] == "forbidden_entities":
                detail = "未出现" if check["ok"] else f"误出现：{'、'.join(check['present'])}"
                lines.append(f"- {mark} 禁止实体：{detail}")
            elif check["kind"] == "must_refuse":
                lines.append(f"- {mark} 拒答要求")
        if turn["degenerate_markers"]:
            lines.append(f"- ⚠️ 退化话术：{'、'.join(turn['degenerate_markers'])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-json", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, default=None)
    return parser


def main() -> int:
    args = _parser().parse_args()
    replay = json.loads(args.replay_json.read_text(encoding="utf-8"))
    report = evaluate_replay(replay)
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    if args.json_output is not None:
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
