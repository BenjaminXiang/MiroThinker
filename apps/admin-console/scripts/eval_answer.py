"""Three-layer eval of /api/chat generated answers (synthesis ON) vs golden test_cases.yaml.

L1 required-entity coverage (deterministic); L2 forbidden-entity gate (deterministic);
L3 answer-vs-golden judge (异模型 LLM, six PRD dimensions) — added in Task 3.

Run (from apps/admin-console), env-truth first:
  source scripts/eval_env.sh
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 UV_OFFLINE=1 uv run python scripts/eval_answer.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

os.environ.setdefault("CHAT_LLM_SYNTHESIS", "on")


def _load_cases() -> list[dict]:
    p = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "test_cases.yaml"
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["cases"]


def score_l1_required(case: dict, answer: str) -> tuple[list[str], list[str]]:
    """L1: required_entities must appear in the generated answer. Returns (hit, miss)."""
    req = case.get("required_entities") or []
    hit = [e for e in req if e in answer]
    miss = [e for e in req if e not in answer]
    return hit, miss


def score_l2_forbidden(case: dict, answer: str) -> list[str]:
    """L2: forbidden_entities must NOT appear. Returns violations."""
    forb = case.get("forbidden_entities") or []
    return [e for e in forb if e in answer]


def _run_chat(query: str) -> dict:
    """Run /api/chat (synthesis ON) and return the response JSON."""
    from backend.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    return client.post("/api/chat", json={"query": query}).json()


# --- L3: answer-vs-golden judge (CORE) ---

DIMENSIONS = (
    "type_correct",          # 1. matches expected query-type behavior (A-G)
    "key_content_coverage",  # 2. golden's key facts/entities appear (= L1 fed in)
    "structure_apt",         # 3. profile fields / topic list / aggregate
    "provenance_correct",    # 4. web/fallback source+time marked (N/A for local-only)
    "f_g_handling",          # 5. F refuses / G default+hint (N/A for non-F/G)
    "multi_turn_coref",      # 6. pronouns resolve (N/A for single-turn)
)


def aggregate_l3_scores(scores: dict) -> float:
    """Average applicable dimensions (None = N/A, excluded from numerator+denominator)."""
    vals = [scores[d] for d in DIMENSIONS if scores.get(d) is not None]
    return sum(vals) / len(vals) if vals else 0.0


_L3_JUDGE_PROMPT = """你是检索增强系统的评估 judge。对照金标准答案,给系统生成的答案打分。

查询: {query}
期望类型: {expected_type}
金标准答案: {golden}
系统生成的答案: {system_answer}
必需实体(关键点): {required}
禁出实体: {forbidden}

按以下六个维度各打 0-1 分(不适用标 null),每维给一句理由。**null 表示不适用,不计入分母;不要把"适用但满分"或"本地答案"打成 0,该 null 就 null:**
1. type_correct: 答案类型是否符合期望(A 单实体profile / B 主题列表 / C 跨轮 / D 全景聚合 / E 知识+web / F 拒答 / G 默认+提示)
2. key_content_coverage: 金标准的关键事实/实体是否覆盖(必需实体必须出现)。**F拒答类查询标 null(拒答无内容可覆盖)**;非拒答才打分。
3. structure_apt: 结构是否得当(profile字段齐全 / 主题是列表 / 跨域是聚合)。F拒答标 null。
4. provenance_correct: **纯本地知识库答案(无web/fallback/实时补充)标 null,不打0**;只有当答案含web/fallback/时效性内容却没标来源+时间时才打低分。
5. f_g_handling: F是否礼貌拒答+引导 / G是否默认高置信+短提示(非F/G标 null)
6. multi_turn_coref: 代词(他/上述企业)是否解析对(单轮标 null)

只返回 JSON: {{"type_correct": <0-1或null>, "key_content_coverage": <...>, "structure_apt": <...>,
"provenance_correct": <...>, "f_g_handling": <...>, "multi_turn_coref": <...>,
"reasons": {{"type_correct": "...", ...}}}}
"""


def _call_judge(case: dict, system_answer: str, l1_hit: list[str]) -> dict:
    """Call the 异模型 LLM judge (Anthropic SDK via zenmux proxy, claude-sonnet-4-5 by default).

    Uses ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN (the same proxy the harness uses). Override
    model via EVAL_JUDGE_MODEL (default claude-sonnet-4-5). Returns all-N/A if the SDK/env is
    unavailable. 异模型: synthesis uses a different provider/model; the judge is Claude.
    """
    import anthropic
    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    model = os.environ.get("EVAL_JUDGE_MODEL", "claude-sonnet-4-5-20250929")
    if not (base and key):
        return {d: None for d in DIMENSIONS} | {"reasons": {"_": "judge not configured (ANTHROPIC_* unset)"}}
    prompt = _L3_JUDGE_PROMPT.format(
        query=case["query"], expected_type=case.get("expected_type", "?"),
        golden=case.get("answer", ""), system_answer=system_answer,
        required=case.get("required_entities", []), forbidden=case.get("forbidden_entities", []),
    )
    client = anthropic.Anthropic(base_url=base, auth_token=key)
    resp = client.messages.create(model=model, max_tokens=600,
                                  messages=[{"role": "user", "content": prompt}])
    content = resp.content[0].text
    content = content.strip().strip("`").lstrip("json").strip()
    return json.loads(content)


def main() -> int:
    cases = _load_cases()
    rows: list[dict] = []
    print(f"{'qid':>3} {'L1 hit/req':>10} {'L2 viol':>8}  query")
    print("-" * 80)
    for c in cases:
        try:
            j = _run_chat(c["query"])
        except Exception as e:  # noqa: BLE001
            rows.append({"qid": c["qid"], "error": str(e)})
            print(f"{c['qid']:>3} ERR {type(e).__name__}")
            continue
        answer = str(j.get("answer_text") or j.get("answer") or "")
        hit, miss = score_l1_required(c, answer)
        viol = score_l2_forbidden(c, answer)
        l3_raw = _call_judge(c, answer, hit)
        l3_scores = {d: l3_raw.get(d) for d in DIMENSIONS}
        l3_avg = aggregate_l3_scores(l3_scores)
        rows.append({
            "qid": c["qid"], "query": c["query"],
            "l1_hit": hit, "l1_miss": miss, "l2_violations": viol,
            "l3_scores": l3_scores, "l3_avg": l3_avg, "l3_reasons": l3_raw.get("reasons", {}),
        })
        print(f"{c['qid']:>3} {len(hit)}/{len(c.get('required_entities') or []):>3}    "
              f"{len(viol):>4}    L3={l3_avg:.2f}   {c['query'][:24]}")
    # scripts/ -> apps/ -> admin-console/ -> apps/ -> repo root (parents[3])
    out = Path(__file__).resolve().parents[3] / ".agents" / "runs" / "retrieval-eval" / "answer-eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"rows": rows}, fh, ensure_ascii=False, indent=2)
    print(f"WRITTEN: {out}")
    print("NOTE: if EVAL_JUDGE_* unset, L3 is all-N/A (judge skipped); L1/L2 still run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
