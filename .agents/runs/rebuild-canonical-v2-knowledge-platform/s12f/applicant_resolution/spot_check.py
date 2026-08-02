#!/usr/bin/env python
"""质量抽查：从 applicant_name_resolution.jsonl 的 resolved 结果随机抽 N 条，
用 serper 重新搜索申请人名，LLM 独立判定规范中文公司名，与 resolved_company
做归一化比较，统计准确率。

Usage:
  python spot_check.py --n 20 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

WORKTREE = Path("/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation")
MIROFLOW_AGENT_ROOT = WORKTREE / "apps/miroflow-agent"
if str(MIROFLOW_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(MIROFLOW_AGENT_ROOT))

from openai import OpenAI  # noqa: E402
from src.data_agents.professor.llm_profiles import (  # noqa: E402
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)
from src.data_agents.providers.web_search import WebSearchProvider  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
DEFAULT_JSONL = OUT_DIR / "applicant_name_resolution.jsonl"

SYSTEM_PROMPT = """你是专利申请人名称解析专家。给定一个专利申请人名称及其 web 搜索结果（标题/摘要/链接），
判定该申请人对应的规范中文公司全称。

规则：
1. canonical_name：该公司最规范的现行中文全称（例如"深圳市优必选科技股份有限公司"）。若申请人本身就是规范全称，原样返回；若申请人是对应的英文名/简称/旧称，返回规范中文全称。
2. 若申请人不是公司，或无法确定，canonical_name 必须为空字符串 ""。
3. confidence：high=搜索结果明确；medium=较明确；low=模糊/无法判定。
4. note：简短中文说明依据。

输出格式：只输出一个 JSON 对象，不要任何其他文字：
{"canonical_name":"...","confidence":"high|medium|low","note":"..."}"""


def normalize_key(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def truncate(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[: limit - 1] + "…"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--llm-profile", default=None)
    parser.add_argument("--out", type=Path, default=OUT_DIR / "spot_check_results.jsonl")
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.jsonl.open(encoding="utf-8")]
    resolved = [r for r in rows if r["status"] == "resolved"]
    print(f"resolved 总数: {len(resolved)}，抽取 {args.n} 条（seed={args.seed}）")
    sample = random.Random(args.seed).sample(resolved, min(args.n, len(resolved)))

    settings = resolve_professor_llm_settings(
        profile_name=args.llm_profile, apply_endpoint_env_overrides=False
    )
    extra_body = build_non_thinking_extra_body(settings["local_llm_model"])
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"],
        timeout=120,
    )
    provider = WebSearchProvider(timeout=8)

    results = []
    for i, row in enumerate(sample, start=1):
        name = row["applicant_name"]
        expected = row["resolved_company"]
        try:
            result = provider.search(f'"{name}"')
        except Exception as exc:  # noqa: BLE001
            print(f"[{i}/{len(sample)}] serper 失败 {name!r}: {exc}")
            results.append(
                {"applicant": name, "expected": expected, "fresh": "", "match": None,
                 "note": f"serper 失败: {exc}"}
            )
            continue
        organic = (result.get("organic") or [])[:5]
        lines = []
        for j, item in enumerate(organic, start=1):
            lines.append(
                f"[{j}] 标题: {truncate(str(item.get('title') or ''), 200)} | "
                f"摘要: {truncate(str(item.get('snippet') or ''), 300)} | "
                f"链接: {item.get('link')}"
            )
        user_msg = (
            f"申请人: {name}\n"
            "搜索结果:\n" + "\n".join(lines) if lines else "搜索结果: （无有效结果）"
        )
        fresh_name = ""
        confidence = "low"
        note = ""
        try:
            response = client.chat.completions.create(
                model=settings["local_llm_model"],
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                max_tokens=2000,
                extra_body=extra_body,
            )
            text = (response.choices[0].message.content or "").strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end > start:
                parsed = json.loads(text[start : end + 1])
                fresh_name = str(parsed.get("canonical_name") or "").strip()
                confidence = str(parsed.get("confidence") or "low")
                note = str(parsed.get("note") or "")
        except Exception as exc:  # noqa: BLE001
            note = f"LLM 判定失败: {exc}"

        match = (
            bool(fresh_name and expected)
            and normalize_key(fresh_name) == normalize_key(expected)
        )
        results.append(
            {"applicant": name, "expected": expected, "fresh": fresh_name,
             "confidence": confidence, "match": match, "note": note}
        )
        flag = "OK " if match else "MISMATCH" if fresh_name else "EMPTY"
        print(f"[{i}/{len(sample)}] {flag} {name} -> 期望={expected} | 独立判定={fresh_name or '(空)'}")
        time.sleep(0.3)

    with args.out.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    judged = [r for r in results if r["match"] is not None]
    correct = sum(1 for r in judged if r["match"])
    print(f"\n判定样本 {len(judged)} 条，一致 {correct} 条，准确率 {correct / len(judged):.1%}")
    for r in judged:
        if not r["match"]:
            print(f"  MISMATCH: {r['applicant']} | 期望={r['expected']} | 独立判定={r['fresh']!r} | {r['note']}")
    print(f"明细 -> {args.out}")


if __name__ == "__main__":
    main()
