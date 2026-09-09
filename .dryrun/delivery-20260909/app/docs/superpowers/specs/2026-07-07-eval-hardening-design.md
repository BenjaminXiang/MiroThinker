# Eval Hardening — Design (Workstream 4)

> Make the true-accuracy eval reproducible and fair, so accuracy-raising work is measured
> against signal, not ±3 noise. Status: design — pending review.
> Contract: doc-as-contract (`openspec/` absent on this branch).

## Problem

`eval_true_accuracy.py` (LLM-judge true accuracy) is **variance-dominated and systematically harsh**:
- Run-to-run pass count fluctuates **7-10** (±3) on identical code/data.
- Genuinely good synthesis answers score FAIL: qid14 (华力创, detailed correct answer) → comp=0.3 → 0.67 FAIL; qid24 (优必选, 10 patents + summary) → comp=0.1 → 0.40 FAIL.

Without fixing this, every accuracy-raising change is measured against noise — the 47%→37%
this iteration was consistent with pure variance on top of a real +qid9 gain.

## Root causes (verified in `eval_true_accuracy.py`)

1. **The judge call has no `temperature`** (`_judge`, line 76 `create(...)`) → deepseek default
   (~0.7) → non-deterministic judgments. Post-Fix-3, synthesis is `temperature=0` (deterministic),
   so the system answer is stable across runs — **judge stochasticity is the dominant variance source.**
2. **Completeness is anchored on the standard's exact points** — the rubric says "覆盖了标准答案中的
   关键信息点", so a correct answer covering the question's needs but differing from the standard's
   wording/points is penalized.
3. **Wrong `extra_body`** — `_judge` hardcodes `{"chat_template_kwargs": {"enable_thinking": False}}`.
   For deepseek-v4-pro the correct form is `{"thinking": {"type": "disabled"}}` (see
   `build_non_thinking_extra_body`). Thinking may be on, adding noise.

## Design

### A — Rubric overhaul (`_JUDGE_SYSTEM` + `_judge` user message)

Rewrite to a **rationale-first, question-anchored** rubric:
- **Step 1 — reason before scoring**: the judge first lists (a) the question's core information
  needs, (b) what the system answer actually covers, (c) any factual errors. Emit this reasoning.
- **Step 2 — score**: completeness is anchored on the **question's** information needs, not the
  standard's points. Explicit rule: "若系统答案正确且实质性地覆盖了用户问题的核心信息需求，
  完整性应 ≥ 0.7，即使措辞不同、或遗漏了标准答案中的边缘要点。" Relevance stays as-is.
- **Keep anti-hallucination**: fabricated/wrong facts → correctness penalty (this is what keeps
  the judge from becoming a rubber-stamp).
- JSON schema unchanged (`correctness`/`completeness`/`relevance`/`overall`/`pass`,
  `overall = mean`, `pass = overall ≥ 0.7`), but the rationale must precede the JSON so the
  parser still finds the JSON via the existing `re.search(r"\{[^}]+\}", ...)`.

### B' — Judge determinism (supersedes the "5-run median" choice)

Add `temperature=0` to the judge's `create(...)` call. With a deterministic judge, repeated runs
yield **identical** scores → the canonical eval is a single deterministic run (`--runs 1`),
reproducible and fast. Keep `--runs N` as an option (median of N stochastic draws) for sanity
checks, but it is no longer needed for stability.

> **Deviation from the approved "A+B" note:** B was "5-run median". Verification showed the
> variance source is the non-deterministic judge (no `temperature`), not insufficient runs.
> B' (judge `temperature=0`) fixes the root cause and is cheaper + more reproducible than
> 5-run median. Flagged here for the record.

### C — Correct non-thinking `extra_body`

Replace the hardcoded `{"chat_template_kwargs": {"enable_thinking": False}}` with
`build_non_thinking_extra_body(model)` (the same helper `_call_gemma_synthesis` uses) →
`{"thinking": {"type": "disabled"}}` for deepseek. Import it from `llm_profiles`.

## Verification — calibration gate

After implementing, run the eval and confirm ALL of:
- **Fairness (was false-fail)**: qid14 → PASS; qid24 → PASS or ≥0.65 (was 0.40).
- **Not a rubber-stamp**: qid11 (clarification), qid19/20 (multi-turn/wrong-domain) → still FAIL.
- **Determinism**: two consecutive `--runs 1` evals produce **identical** per-case overall scores.
- **No accuracy inflation beyond fairness**: the overall pass count moves by roughly the
  false-fail count (qid14/24), not by +5+ (which would signal over-leniency).

Record results in `docs/solutions/2026-07-07-eval-hardening-results.md`.

## Non-goals

- E-route synthesis determinism (`_answer_knowledge_qa` uses `temperature=0.3`, chat.py:1223) —
  separate slice; affects only E-route answers' stability, not the judge.
- Broader held-out eval set (population measurement) — separate.
- Multi-turn session context for qid19/20 — Workstream 2.

## Files

- Modify: `apps/admin-console/scripts/eval_true_accuracy.py` (rubric constant, `_judge` call,
  default runs docstring).
- No production code change; eval-only.
