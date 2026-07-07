"""True-accuracy eval via LLM-judge (semantic, not keyword-overlap).

For each head-turn case in the golden set, the local LLM (qwen3.6, free) judges whether
the system's answer correctly + comprehensively addresses the user's question — scoring
correctness/completeness/relevance (0-1 each), even if the wording differs from the standard.

Uses TestClient (in-process, no external backend needed — same as eval_recall_chat.py).

Usage (backend DOWN to avoid Milvus lock conflict):
  export DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real
  MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=on UV_OFFLINE=1
  uv run python scripts/eval_true_accuracy.py            # canonical: deterministic single run
  uv run python scripts/eval_true_accuracy.py --runs 3   # optional stochastic sanity median

Do NOT set LOCAL_LLM_MODEL — the default profile (deepseek-v4-pro, via
resolve_professor_llm_settings) is used for both synthesis and judge, consistent.
The judge runs at temperature=0, so --runs 1 is reproducible.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml
from openai import OpenAI

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "apps" / "admin-console" / "tests" / "fixtures" / "test_cases.yaml"

# Env defaults must precede app import (the existing eval pattern)
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real")
os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")
os.environ.setdefault("CHAT_LLM_SYNTHESIS", "on")
os.environ.setdefault("UV_OFFLINE", "1")

# --- LLM judge ---
def _get_judge_client() -> tuple[OpenAI, str, dict]:
    """Use the same LLM settings as the synthesis (resolve_professor_llm_settings).

    Returns (client, model, non_thinking_extra_body). The extra_body uses
    build_non_thinking_extra_body(model) — the same helper synthesis uses — so
    deepseek-v4-pro gets {"thinking": {"type": "disabled"}} (not the vLLM-style
    chat_template_kwargs, which deepseek ignores and may leave thinking on).
    """
    sys.path.insert(0, str(REPO / "apps" / "miroflow-agent"))
    from src.data_agents.professor.llm_profiles import (
        build_non_thinking_extra_body,
        resolve_professor_llm_settings,
    )

    settings = resolve_professor_llm_settings(None, include_profile=True)
    model = os.getenv("LOCAL_LLM_MODEL") or settings["local_llm_model"]
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        timeout=60.0,
    )
    return client, model, build_non_thinking_extra_body(model)


_JUDGE_SYSTEM = (
    "你是科创信息检索系统的评分员。先推理，再打分。\n"
    "第一步（推理，先输出）：简要列出 (a) 用户问题的核心信息需求是什么；"
    "(b) 系统答案实际覆盖了哪些、遗漏了哪些；(c) 系统答案中是否有事实错误或编造。\n"
    "第二步（打分，每项0-1分）：\n"
    "(1) 正确性(correctness): 事实是否正确？有编造或错误信息则扣分。\n"
    "(2) 完整性(completeness): 以【用户问题的核心信息需求】为锚点，"
    "而不是标准答案的逐字要点。只要系统答案正确且实质性地覆盖了问题的核心需求，"
    "完整性应 >= 0.7，即使措辞与标准答案不同、或遗漏了标准答案中的边缘要点。"
    "仅当核心需求被遗漏、或答非所问时才给低分。\n"
    "(3) 相关性(relevance): 是否切题。\n"
    "重要：不要因与标准答案措辞不同就扣分；也不要无原则给高分——答非所问、"
    "事实错误、或核心需求完全未覆盖的答案必须给低分。\n"
    "先输出推理，最后另起一行输出一行JSON：\n"
    "{\"correctness\": 0.0-1.0, \"completeness\": 0.0-1.0, \"relevance\": 0.0-1.0, "
    "\"overall\": 0.0-1.0, \"pass\": true/false}\n"
    "overall = (correctness + completeness + relevance) / 3。pass = overall >= 0.7。"
)


def _judge(
    client: OpenAI,
    model: str,
    extra_body: dict,
    question: str,
    standard: str,
    system_answer: str,
) -> dict:
    """Judge one case. Returns {correctness, completeness, relevance, overall, pass}.

    temperature=0 + the model-correct non-thinking extra_body make the judge
    deterministic (the system answer is already temp=0 post-Fix-3), so repeated
    runs yield identical scores — the canonical eval is a single deterministic run.
    """
    user_msg = (
        f"用户问题: {question}\n\n"
        f"标准答案:\n{standard[:2000]}\n\n"
        f"系统答案:\n{system_answer[:2000]}\n\n"
        f"请按系统提示先推理、再输出一行JSON评分。"
    )
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            extra_body=extra_body,
        )
        text = response.choices[0].message.content.strip()
        # Extract JSON from the response
        match = re.search(r"\{[^}]+\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as exc:
        print(f"  judge error: {exc}", file=sys.stderr)
    return {"correctness": 0, "completeness": 0, "relevance": 0, "overall": 0, "pass": False}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1, help="Judge runs per case (median for stability)")
    ap.add_argument("--out", default=str(REPO / ".agents" / "runs" / "retrieval-generation-alignment" / f"true-accuracy-latest.json"))
    args = ap.parse_args()

    cases = yaml.safe_load(FIXTURE.read_text())["cases"]
    head_cases = [c for c in cases if c.get("is_head_turn")]
    print(f"loaded {len(cases)} cases ({len(head_cases)} head-turn)")

    client, model, judge_extra_body = _get_judge_client()
    print(f"judge model: {model}")

    # Use TestClient (in-process, no external backend needed)
    from backend.main import app
    from fastapi.testclient import TestClient
    tc = TestClient(app)

    results = []
    total_pass = 0
    for c in head_cases:
        qid = c["qid"]
        query = c["query"]
        standard = c.get("answer") or ""
        try:
            r = tc.post("/api/chat", json={"query": query})
            system_answer = (r.json().get("answer_text") or "")[:2000]
        except Exception as exc:
            print(f"qid {qid}: error: {exc}")
            results.append({"qid": qid, "query": query, "error": str(exc)[:80]})
            continue

        # Judge (optionally multi-run) — OUTSIDE the try/except
        scores = []
        for _ in range(args.runs):
            score = _judge(client, model, judge_extra_body, query, standard, system_answer)
            scores.append(score)
        # Median
        import statistics
        overall = statistics.median([s.get("overall", 0) for s in scores])
        corr = statistics.median([s.get("correctness", 0) for s in scores])
        comp = statistics.median([s.get("completeness", 0) for s in scores])
        passed = overall >= 0.7

        if passed:
            total_pass += 1
        flag = "PASS" if passed else "FAIL"
        print(
            f"qid {qid:>3} {flag}  overall={overall:.2f}  "
            f"corr={corr:.1f} comp={comp:.1f}  {query[:34]}"
        )
        results.append({
            "qid": qid, "query": query, "overall": round(overall, 2),
                "correctness": round(corr, 1), "completeness": round(comp, 1),
                "pass": passed,
            })

    accuracy = total_pass / len(head_cases) if head_cases else 0
    summary = {
        "head_cases": len(head_cases),
        "true_accuracy": f"{total_pass}/{len(head_cases)} ({100*accuracy:.0f}%)",
        "for_comparison_keyword_overlap_was": "42%",
        "results": results,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n=== TRUE ACCURACY (LLM-judge) ===")
    print(f"  {total_pass}/{len(head_cases)} ({100*accuracy:.0f}%)  [keyword-overlap was 42%]")
    print(f"  written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
