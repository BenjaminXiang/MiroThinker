# Retrieval-Generation Eval System Design — 丰富 case + 三层评估指标与标准

> Status: design (requirements confirmed with user). Next: user reviews → writing-plans.
> Owner: Claude (design/review). Implementation: Codex.
> Date: 2026-07-01.

## 0. Problem and first principles

The retrieval-generation stack iterates (FM4/FM5/web fixes, etc.) but has no trustworthy
truth-base to judge whether an iteration improved or regressed. We already hit this: an eval
run without `SERPER_API_KEY` measured 58% recall and declared "Serper 403 dead" — both false
(the deployed backend has the key; Serper is alive; real recall is higher). **Without a
trustworthy eval, every fix is guesswork and can be validated against wrong numbers.**

First principle: **the eval is the truth-base for iteration.** It needs (a) ground truth and
(b) metrics+standards that turn GT into red/green judgements. The good news: the GT already
exists — `docs/测试集答案.xlsx` (42 rows: 问题 / 答案 / 关键点) is a human golden set, problem +
answer + grading notes. It is not "typical questions only"; it is golden and stays unchanged.

So the core is NOT "design a GT source" or "build a RAGAS full-stack". The core is two things:
1. **Extend the case set** — supplement xlsx with new problem+answer cases (web+LLM generated,
   user-reviewed) to cover paths xlsx misses (法本 name-variant, 教授 cross-domain, F refusal,
   multi-turn coref).
2. **Define evaluation metrics + standards** — how to judge the current system's generated
   results against GT, per case, with red/green thresholds + a regression gate.

Lean by design (per user "不要过度设计"): the three deterministic/judge layers below, not a
6-oracle RAGAS clone. Judge thresholds are NOT pre-set — first run establishes a baseline, the
judge is calibrated against a human-reviewed sample, then thresholds are set.

## 1. Extend the case set

### 1.1 xlsx is frozen golden
`docs/测试集答案.xlsx` (42 rows, 3 cols: 问题 / 答案 / 关键点) is the human golden set. It is
**not modified**. A parser reads it into `test_cases.yaml` (the living case store). xlsx is the
v1 seed; `test_cases.yaml` is the source of truth going forward.

### 1.2 Parse xlsx → test_cases.yaml (foundation)
`apps/admin-console/scripts/parse_testset.py` reads the xlsx, skips `问题N` header rows
(`问题` col matches `/^问题\d+$/`), and emits one case per real row. Per case fields:
`qid`, `turn_group`, `is_head_turn`, `query`, `answer` (full 答案 = GT), `key_point` (raw),
and auto-derived: `required_entities` (from 关键点 "X需要...在回答中"), `forbidden_entities`
(from 关键点 "不应出现X"), `expected_routing` (one-time labeled from A–G semantics),
`coref_target` (multi-turn "他/上述企业" → prior entity, labeled once), `refusal_expected`
(关键点 "不能回答"). Multi-turn followups are grouped with their head turn; cross-group
anaphora (rows 31/33 → row 29's 数据路线) flagged for the labeling pass.

### 1.3 New cases (extend, cover blind spots)
New problem+answer cases, **same column structure as xlsx** (query / answer / key_point),
generated for paths xlsx does not cover:
- **FM5 name-variant** (法本信息科技有限公司 → 法本信息技术) — company-profile by variant name.
- **FM4 cross-domain** (具身智能教授) — topic query that should recall professors via their papers.
- **F refusal** (黄赌毒/illegal) — must be refused; xlsx row 9 is the only F case and the
  classifier's F-regex (chat.py:174) misses 黄赌毒.
- **Multi-turn coref** — "他/上述企业/这论文" followups (xlsx has some; extend coverage).
- Any other real badcase surfaced (e.g., via /chat/feedback).

**Generation = web (Serper, alive) + LLM**, **user-reviewed**:
1. For a target path, generate a natural query + the expected answer (GT) + required/forbidden
   entities via Serper recall + LLM.
2. **User reviews** the generated GT (correctness, completeness) before it enters the golden set.
3. Reviewed case appended to `test_cases.yaml` with the same fields as xlsx-parsed cases.

The golden set's trust comes from the human review anchor, NOT from trusting the LLM. web+LLM
scale generation; the review keeps it golden.

## 2. Three-layer evaluation metrics + standards (the core)

**First principle (user view):** a user asks a question and expects a *good answer*. The xlsx
`答案` is the golden example of such a good answer — not just an entity list, but a well-written,
complete, correctly-typed, properly-sourced answer. The system's answer need not match verbatim,
but it should be "as good as the golden answer" (cover the same key points + correct type/
structure/provenance per the PRD). The eval judges whether the system's generated answer is as
good as the golden answer.

So **Layer 3 (answer vs golden) is the core** — it asks "is the system answer as good as golden?".
Layers 1/2 are deterministic sub-checks that *support* L3 (key-point coverage + forbidden
absence). Routing/type/structure/provenance/F-G/multi-turn fold INTO L3's judge rubric (per PRD),
not a separate fourth layer (user confirmed three layers).

Eval object: the system's generated `answer_text` (synthesis ON). Per case, three layers:

### Layer 1 — Required-entity/coverage (deterministic, supports L3)
- **What**: each `required_entities` (from 关键点) must appear in the **generated answer_text**.
  Catches both retrieval misses (entity never found) and generation drops (retrieved but omitted).
- **Standard**: per-case hit/miss (which required entities appeared in the answer). Overall = hit/total.
- **Red/green**: GREEN if all required entities appear; RED if any missed. **No judge** — deterministic.
- Multi-turn: required set = head-turn entities filtered by the followup constraint (e.g.
  "上述企业总部深圳" → the 深圳 suppliers from the head-turn answer).
- **Retrieval-isolation variant** (optional): same check over candidates/evidence (synthesis OFF)
  isolates whether a miss is retrieval or generation.

### Layer 2 — Forbidden-entity negative gate (deterministic, supports L3)
- **What**: each `forbidden_entities` (from 关键点 "不应出现X") must NOT appear in the
  **generated answer_text**.
- **Standard**: per-case violation count = 0.
- **Red/green**: GREEN if 0 forbidden entities appear; RED if any appears. **No judge**.

### Layer 3 — Answer vs golden answer (CORE, judge)
- **What**: the synthesized `answer_text` vs the xlsx `答案` golden answer — "is the system
  answer as good as golden?" An LLM-judge (异模型, different from synthesis) scores 0–1.
- **Tolerance**: verbatim match NOT required; the judge assesses "as good as golden" semantically.
- **Judge rubric — six PRD dimensions, each scored independently 0–1, equal-weight average:**
  1. **Type correct** — matches the expected query-type behavior (A single-entity profile /
     B topic list / C cross-turn / D panoramic aggregate / E knowledge+web / F refusal /
     G default-high-confidence + hint). Topic asked as profile = wrong; F not refused = wrong;
     G missing hint = wrong.
  2. **Key-content coverage** — the key facts/entities of the golden answer appear (= L1, fed in
     as a deterministic sub-score).
  3. **Structure apt** — profile has the right fields (H-index/Top papers per PRD §模块一); topic
     is a list; cross-domain is an aggregate.
  4. **Provenance correct** — web/fallback/time-sensitive answers explicitly mark source + time
     (PRD §2 step 4); local high-confidence need not show source in-body.
  5. **F/G handling** — F politely refuses + redirects; G defaults to the most-relevant candidate
     with a short switch hint.
  6. **Multi-turn coref** — pronouns ("他/上述企业") resolve to the correct prior entity.
- **Red/green**: GREEN if the six-dimension average ≥ threshold; RED if below. **Threshold NOT
  pre-set** — first run establishes a baseline; the judge is calibrated on a human-reviewed sample
  (~5 cases across A/B/multi-turn); then the threshold is set. Per-dimension scores let an
  iteration see WHICH dimension regressed (direction), not just the aggregate.

### Layer notes
- Layers 1/2 are deterministic (no judge) — cheap, reliable regression anchors; a layer-1/2 red
  forces a layer-3 red (coverage/forbidden is a floor).
- Layer 3's judge catches what L1/L2 miss: "all entities present but the answer is poorly written
  / wrong type / unsourced / no hint" — the answer-quality dimensions the PRD cares about.
- faithfulness/context-precision (RAGAS label-free) are **out of scope for v1** (lean) — L3's
  provenance dimension + L1/2 cover the core; faithfulness/precision can be a v2 add.

## 3. Env truth (the lesson learned)

The eval process env MUST match the deployed backend env, or it measures a broken system:
- **`SERPER_API_KEY`** must be set (the deployed backend has it; the eval shell does not by
  default). Read it from the running backend's env, or document it in an eval env file.
- **No proxy vars** (`unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
  no_proxy NO_PROXY`) — the backend runs without proxy and reaches external APIs direct; the
  eval must match (unsetting avoids localhost hijack; the backend's direct path works).
- **`CHAT_LLM_SYNTHESIS=on`** for the three-layer eval (the eval judges the generated answer:
  layer 1/2 check `answer_text`, layer 3 compares to the reference). A synthesis-OFF variant of
  layer 1/2 (check candidates/evidence) isolates retrieval but is not the primary eval.

The first run that produced "58% / Serper dead" was an env-broken run (no key). The corrected
run (with key) is the baseline. This constraint is non-negotiable for trustworthy eval.

## 4. Regression gate (lean)

`apps/admin-console/scripts/eval_regression.py` orchestrates the three layers over
`test_cases.yaml`:
- Compares each layer's per-case result to a committed golden baseline JSON
  (`.agents/runs/retrieval-eval/golden-baseline.json`).
- **Exit 1** if: any layer-1 case regressed (a previously-green required entity now missed) OR
  any layer-2 case regressed (a forbidden entity now appears) OR layer-3 overall score dropped
  below its calibrated threshold.
- **Exit 0** if no regression.
- Runnable locally (needs DB+Milvus+Serper key); CI wiring is a later add (lean — local first).

Badcase → case: a reported badcase (法本, 教授) → generate GT via web+LLM → user review → append
to `test_cases.yaml` → re-derive golden baseline. Every real failure becomes a permanent
regression case.

## 5. Scope (lean, not over-designed)

In v1:
- parse_testset.py + test_cases.yaml (foundation).
- three layers (layer 1/2 deterministic, layer 3 single judge).
- regression gate (exit code, golden baseline).
- env-truth constraint enforced.

Explicitly NOT in v1 (deferred):
- faithfulness / context-precision / answer-relevancy (RAGAS label-free) — v2, once the
  three-layer base is trusted.
- CI wiring — local runnable first.
- multi-judge ensemble — single 异模型 judge only.
- LLM-judge threshold pre-set — first baseline + calibration, then set.

## 6. Open risks (honest)
- The LLM-judge (layer 3) has bias/quality risk → mitigated by 异模型 (different from synthesis)
  + human-calibration on a sample. If the judge proves unreliable on calibration, layer 3 is
  downgraded to required-entity-coverage-only (layer 1) until a better judge is available.
- web+LLM-generated cases can have wrong GT → mitigated by mandatory user review before golden.
- The xlsx multi-turn coref labeling (coref_target) is a one-time human pass; until done,
  multi-turn cases run with coref_target = null (layer 1 runs on the head-turn entities only).
- This eval measures the CURRENT system; it does not itself fix FM4/FM5/web — it gives the
  truth-base to judge those fixes when they land.
