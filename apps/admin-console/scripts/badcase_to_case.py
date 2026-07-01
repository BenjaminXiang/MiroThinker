"""Badcase → golden case pipeline.

For a reported badcase query, generate the expected answer (GT) + required/forbidden entities via
Serper web recall + LLM, THEN prompt the user to review/edit before appending to test_cases.yaml.
The golden trust comes from the USER REVIEW, not the LLM.

Run (from apps/admin-console), env-truth first:
  source scripts/eval_env.sh
  UV_OFFLINE=1 uv run python scripts/badcase_to_case.py --query "深圳法本信息科技有限公司的产品特点以及团队介绍"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_testset import _derive_required, _derive_forbidden  # reuse heuristics


def next_qid(cases: list[dict]) -> int:
    return (max((c["qid"] for c in cases), default=0)) + 1


def build_case(*, qid: int, query: str, answer: str, key_point: str,
               turn_group: str | None, is_head_turn: bool) -> dict:
    return {
        "qid": qid,
        "turn_group": turn_group,
        "is_head_turn": is_head_turn,
        "query": query,
        "answer": answer,
        "key_point": key_point,
        "required_entities": _derive_required(key_point),
        "forbidden_entities": _derive_forbidden(key_point),
        "coref_needs_label": False,
        "refusal_expected": "不能回答" in key_point,
        "disambiguation_expected": "会搜索出" in key_point,
        "source": "badcase+web+llm+user-reviewed",
    }


def _serper_recall(query: str, top_n: int = 5) -> list[dict]:
    key = os.environ.get("SERPER_API_KEY", "")
    if not key:
        return []
    body = json.dumps({"q": query, "num": top_n}).encode("utf-8")
    req = urllib.request.Request("https://google.serper.dev/search", data=body,
                                 headers={"X-API-KEY": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read()).get("organic", [])


def _llm_generate_gt(query: str, web: list[dict]) -> tuple[str, str]:
    """LLM generates (answer, key_point) from query + web recall. Returns draft for user review."""
    base = os.environ.get("EVAL_JUDGE_BASE_URL", "")
    model = os.environ.get("EVAL_JUDGE_MODEL", "")
    key = os.environ.get("EVAL_JUDGE_API_KEY", "")
    web_ctx = "\n".join(f"- {w.get('title','')}: {w.get('snippet','')}" for w in web[:5])
    prompt = (f"为以下查询生成一个金标准答案 + 关键点(必需实体,用'需要在回答中'标记)。\n"
              f"查询: {query}\n网络召回:\n{web_ctx}\n"
              f"返回 JSON: {{\"answer\": \"...\", \"key_point\": \"...\"}}")
    if not (base and model and key):
        return ("[DRAFT — fill in]", "[DRAFT — fill in required entities]")
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0}).encode("utf-8")
    req = urllib.request.Request(f"{base}/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = json.loads(resp.read())["choices"][0]["message"]["content"]
    parsed = json.loads(content.strip().strip("`").lstrip("json").strip())
    return parsed["answer"], parsed["key_point"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--turn-group", default=None)
    args = ap.parse_args()
    yaml_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "test_cases.yaml"
    with open(yaml_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    cases = data["cases"]
    web = _serper_recall(args.query)
    answer, kp = _llm_generate_gt(args.query, web)
    print("=== DRAFT GT (review before saving) ===")
    print(f"query: {args.query}")
    print(f"web recall: {len(web)} results")
    print(f"draft answer: {answer[:200]}...")
    print(f"draft key_point: {kp}")
    print("=======================================")
    confirm = input("Append this case to test_cases.yaml? [y/N/edit]: ").strip().lower()
    if confirm != "y":
        print("not appended — edit the draft manually then re-run, or hand-add to the yaml.")
        return 1
    qid = next_qid(cases)
    case = build_case(qid=qid, query=args.query, answer=answer, key_point=kp,
                      turn_group=args.turn_group, is_head_turn=True)
    cases.append(case)
    with open(yaml_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
    print(f"appended qid={qid}; re-derive golden baseline: uv run python scripts/eval_regression.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
