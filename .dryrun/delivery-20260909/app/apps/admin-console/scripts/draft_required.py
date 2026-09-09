"""Draft required_entities for cases the parser couldn't auto-derive (labeling-pass helper).

For each case with required_entities == [] and not a refusal case, use the LLM to extract the
core entities the golden answer must contain (short forms, for substring matching) from
(query + key_point + golden answer). Output is a DRAFT for user review — NOT auto-applied.

Run (from apps/admin-console), env-truth first:
  source scripts/eval_env.sh
  UV_OFFLINE=1 uv run python scripts/draft_required.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml


def _extract_required_llm(case: dict) -> list[str]:
    """LLM extracts short matchable required entities from query + key_point + golden answer."""
    import anthropic
    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if not (base and key):
        return []
    # zenmux proxy serves real Claude models (env vars point to glm-5.2 = harness model, not valid here)
    model = "claude-haiku-4-5"
    client = anthropic.Anthropic(base_url=base, auth_token=key)
    prompt = (
        "你是测试集标注助手。给定查询、关键点、金标准答案,提取'答案里必须出现的核心实体/术语'"
        "(用于子串匹配,只要答案里出现就算命中)。要求:短形式(如'普渡'而非'深圳市普渡科技股份有限公司');"
        "只取实体/术语,不要整句;3-6 个。只返回 JSON 数组,如 [\"丁文伯\",\"无界智航\"],不要其他文字。\n\n"
        f"查询: {case['query']}\n关键点: {case['key_point']}\n金标准答案: {case['answer'][:600]}"
    )
    resp = client.messages.create(model=model, max_tokens=300,
                                  messages=[{"role": "user", "content": prompt}])
    content = resp.content[0].text.strip().strip("`").lstrip("json").strip()
    return json.loads(content)


def main() -> int:
    yaml_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "test_cases.yaml"
    with open(yaml_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    cases = data["cases"]
    print(f"{'qid':>3} {'now':>20} -> {'drafted':<30}  query")
    print("-" * 100)
    drafted = 0
    for c in cases:
        if c.get("required_entities") or c.get("refusal_expected"):
            # already has required, or F-refusal (no entities needed)
            print(f"{c['qid']:>3} {str(c.get('required_entities'))[:20]:>20}    {'(skip)':<30}  {c['query'][:24]}")
            continue
        draft = _extract_required_llm(c)
        if draft:
            c["required_entities"] = draft
            drafted += 1
            print(f"{c['qid']:>3} {'[]':>20} -> {str(draft)[:30]:<30}  {c['query'][:24]}")
        else:
            print(f"{c['qid']:>3} {'[]':>20} -> {'(LLM failed/flag for manual)':<30}  {c['query'][:24]}")
    print("-" * 100)
    print(f"drafted required_entities for {drafted} cases.")
    # write a DRAFT yaml (not overwriting the original yet — user reviews first)
    draft_path = yaml_path.with_suffix(".draft.yaml")
    with open(draft_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
    print(f"DRAFT written: {draft_path}")
    print("Review the draft; if OK, overwrite test_cases.yaml and re-run eval_answer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
