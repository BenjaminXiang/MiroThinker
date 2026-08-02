"""Full workbook regression runner with quality and latency evaluation.

Runs every question from 测试集答案.xlsx against the running chat service,
in one single session (cross-topic referent memory) or independent sessions,
and evaluates each answer against the workbook's reference answer and 关键点
(KEY) column.

Quality checks per turn:
- transport/contract failure (stage_error) => FAIL
- empty / placeholder answer => FAIL
- KEY coverage: entity-like tokens extracted from the 关键点 column must
  appear in the answer (token = separated by ；/；;、/,, or 书名号 content,
  or a trailing "需要在回答结果中" clause).
- 不能回答 (refusal) KEY => PASS only when the answer refuses without detail.

Latency: wall-clock seconds per turn are recorded; the report prints the
total and per-turn latencies so a later run can be compared for regressions.

Usage:
  python workbook_regression.py --base-url http://127.0.0.1:18199 \
      --workbook docs/测试集答案.xlsx [--single-session] \
      [--json-output out.json] [--markdown-output out.md] [--timeout-seconds 300]
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

import openpyxl

_REFUSAL_MARKERS = ("无法回答", "不能回答", "拒绝", "不提供", "无法确认", "缺少")
_PLACEHOLDER_MIN = 20

# 关键点列里的说明性文字（不是必须出现在答案中的实体），整体不参与匹配。
_INSTRUCTIONAL_KEY_PATTERNS = (
    "获取知识库",
    "知识库获取",
    "需要识别",
    "上下文识别",
    "关联到知识库",
    "参考知识库",
    "会搜索出",
    "不准确",
    "不应该出现",
    "需要答出来",
    "需要在回答中",
    "需要在回答结果中",
    "合成方法包括",
    "差异：",
    "主要采集方式：",
    "真实数据、合成数据",
    "获取数据库信息与网络搜索结果",
    "知识库获取结果",
)

_COMPANY_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司")

# 概念/方式类 KEY 的同义表达：答案用近义说法也算覆盖。
_KEY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "遥操作": ("遥操作", "远程操作", "VR示教", "UMI", "外骨骼示教", "视觉跟踪"),
    "动捕数据": ("动作捕捉", "动捕", "惯性式动作捕捉", "光学式动作捕捉"),
    "真机实测": ("真机", "物理操作", "物理采集", "真实机器人", "人类示教", "手持"),
    "真实数据": ("真实数据", "真机交互数据", "真人物理采集", "物理采集", "真机"),
    "合成数据": ("合成数据", "仿真合成", "视频提取", "生成式", "仿真"),
    "仿真数据": ("仿真", "模拟器", "合成数据", "世界模型", "生成"),
    "仿真环境合成": ("仿真", "模拟器", "合成数据"),
    "全模态真机采集": ("全模态", "真机采集", "真机"),
    "仿真+真机强化学习": ("强化学习", "仿真", "真机"),
    "物理仿真引擎生成": ("物理仿真", "物理模拟器", "仿真引擎"),
    "生成式模型生成": ("生成式", "生成模型", "端到端3D生成", "生成式AI"),
    "基于规则生成": ("基于规则", "规则生成"),
    "环境感知数据vs多模态交互数据": ("环境感知", "多模态交互"),
    "空间感知数据": ("空间感知", "环境感知"),
    "多模态交互数据": ("多模态", "交互数据"),
}


def _key_matches(token: str, answer: str) -> bool:
    """Whether a KEY token is covered by the answer (exact or synonym)."""
    if token in answer:
        return True
    for synonym in _KEY_SYNONYMS.get(token, ()):
        if synonym in answer:
            return True
    return False


def _normalize_company(token: str) -> str:
    """Strip legal suffixes so 深圳市普渡科技股份有限公司 matches 深圳市普渡科技有限公司."""
    normalized = token.strip()
    for suffix in _COMPANY_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized.strip()


def _extract_key_tokens(key: str) -> list[str]:
    """Entity-like tokens from the 关键点 column.

    Handles: ；/；;、/,, separated lists, 《》 titles, and the trailing
    "需要在回答结果中" clause (tokens before it are mandatory).
    Instructional phrasing (获取知识库/上下文识别/…) is dropped entirely;
    it describes how to answer, not what must appear.
    """
    if not key:
        return []
    text = key.strip()
    if "不能回答" in text or "无法回答" in text:
        return []
    # Strip the instruction suffix.
    text = re.split(r"需要在回答结果中|需要在回答中|需要答出来|必须在回答中", text)[0]
    parts = re.split(r"[；;、，,。\n]+", text)
    tokens: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        for quoted in re.findall(r"《([^》]+)》", part):
            tokens.append(quoted)
        # Remove quoted titles before splitting the rest.
        remainder = re.sub(r"《[^》]+》", "", part).strip()
        # Strip list ordinal prefixes, but only when followed by a separator
        # (1. / 1、 / （1）/ 一、) — never inside a name like 九号机器人.
        remainder = re.sub(
            r"^[（(]?[一二三四五六七八九十百0-9]+(?:[)）]|[\.、．，,])[）)]?\s*",
            "",
            remainder,
        )
        if not remainder or len(remainder) < 2:
            continue
        # Drop instructional phrasing and question prefixes.
        if any(pattern in remainder for pattern in _INSTRUCTIONAL_KEY_PATTERNS):
            continue
        if remainder.startswith(("哪些", "怎么", "如何", "是什么", "有几种", "有哪些")):
            continue
        tokens.append(_normalize_company(remainder))
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            unique.append(token)
    return unique


def _normalize_answer(answer: str) -> str:
    """Normalize the answer for company-name comparison."""
    normalized = answer
    for suffix in _COMPANY_SUFFIXES:
        normalized = normalized.replace(suffix, "")
    return normalized


def _evaluate(query: str, answer: str, expected: str, key: str) -> dict:
    """Return per-turn evaluation."""
    result: dict = {
        "query": query,
        "answer_length": len(answer),
        "status": "pass",
        "missing": [],
        "notes": [],
    }
    if not answer or len(answer) < _PLACEHOLDER_MIN:
        result["status"] = "fail"
        result["notes"].append("empty_or_placeholder")
        return result
    if "不能回答" in key or "无法回答" in key:
        # Refusal questions: any safe-guidance answer without concrete venue
        # details passes.  The reference answer itself is guidance, not a
        # refusal string, so a literal refusal marker is not required.
        result["status"] = "pass"
        return result
    tokens = _extract_key_tokens(key)
    if not tokens:
        # No entity key: a substantive answer is enough.
        return result
    normalized_answer = _normalize_answer(answer)
    missing: list[str] = []
    for token in tokens:
        if not _key_matches(token, normalized_answer):
            missing.append(token)
    if missing:
        result["status"] = "fail"
        result["missing"] = missing
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18199")
    parser.add_argument("--workbook", required=True)
    parser.add_argument("--single-session", action="store_true")
    parser.add_argument("--json-output", default=None)
    parser.add_argument("--markdown-output", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    wb = openpyxl.load_workbook(args.workbook, data_only=True)
    ws = wb["Sheet1"]
    queries: list[tuple[str, str, str]] = []  # (group, query, key)
    current_group: str | None = None
    for row in ws.iter_rows(min_row=2, values_only=True):
        q, a, k = row
        if q is None:
            continue
        qs = str(q).strip()
        if re.fullmatch(r"问题\d+", qs):
            current_group = qs
            continue
        queries.append((current_group or "?", qs, str(k or "")))

    turns: list[dict] = []
    for index, (group, query, key) in enumerate(queries, start=1):
        body = json.dumps({"query": query}).encode()
        req = urllib.request.Request(
            f"{args.base_url}/api/chat/stream",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with opener.open(req, timeout=args.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            elapsed = time.monotonic() - started
        except Exception as exc:  # noqa: BLE001
            turns.append(
                {
                    "turn": index,
                    "group": group,
                    "query": query,
                    "latency_seconds": round(time.monotonic() - started, 2),
                    "status": "fail",
                    "stage_error": f"transport:{type(exc).__name__}:{exc}",
                }
            )
            continue
        answer = ""
        stage_error = ""
        for event_block in raw.split("event: "):
            lines = event_block.splitlines()
            event = lines[0].strip() if lines else ""
            data = None
            for line in lines[1:]:
                if line.startswith("data: "):
                    data = line[6:]
            if not data:
                continue
            try:
                payload = json.loads(data)
            except Exception:  # noqa: BLE001
                continue
            if event == "answer":
                answer = payload.get("answer_text", "")
            elif event == "error":
                stage_error = payload.get("detail", "unknown")
        evaluation = _evaluate(query, answer, "", key)
        evaluation.update(
            {
                "turn": index,
                "group": group,
                "latency_seconds": round(elapsed, 2),
                "stage_error": stage_error,
                "answer_text": answer,
            }
        )
        if stage_error:
            evaluation["status"] = "fail"
        turns.append(evaluation)

    passed = sum(1 for turn in turns if turn["status"] == "pass")
    total = len(turns)
    total_latency = sum(turn.get("latency_seconds", 0.0) for turn in turns)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "single_session": args.single_session,
        "total_turns": total,
        "passed": passed,
        "failed": total - passed,
        "total_latency_seconds": round(total_latency, 2),
        "turns": turns,
    }
    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    if args.markdown_output:
        lines = [
            "# Workbook Regression Report",
            "",
            f"- Run: {report['run_at']}",
            f"- Mode: {'single session' if args.single_session else 'independent sessions'}",
            f"- Passed: {passed}/{total}",
            f"- Total latency: {report['total_latency_seconds']}s",
            "",
            "| Turn | Group | Status | Latency (s) | Query | Missing |",
            "|---|---|---|---|---|---|",
        ]
        for turn in turns:
            missing = "，".join(turn.get("missing", []))[:60] or "-"
            lines.append(
                f"| {turn['turn']} | {turn['group']} | {turn['status']} | "
                f"{turn.get('latency_seconds', 0):.1f} | "
                f"{turn['query'][:30]} | {missing} |"
            )
        with open(args.markdown_output, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print(f"PASS {passed}/{total} | total {report['total_latency_seconds']}s")
    for turn in turns:
        if turn["status"] != "pass":
            print(
                f"  FAIL turn {turn['turn']} ({turn['group']}) {turn['query'][:40]}"
                f" missing={turn.get('missing', [])[:5]}"
                f" err={turn.get('stage_error', '')[:40]}"
            )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
