# Synthesis-Depth Fixes — Design

> Workstream 1 (合成层 L3+L4) of the path-to-90% plan.
> Status: design — pending user review. Target: 47% → ~60-70% on the 19-case golden set.
> Chosen as first investment in the 2026-07-07 brainstorm (synthesis-first).

## Context & first-principles framing

A RAG system's accuracy is bounded by five layers; any gap is a hard ceiling:

| Layer | Meaning | Current gap |
|---|---|---|
| L1 recall | Is the data in the corpus? | ~41% notable companies absent (data-pipeline, Workstream 3) |
| L2 retrieval | Can we find it? | cross-domain + professor-topic (Workstream 2) |
| **L3 presentation** | Does it reach the synthesis prompt? | **list entities: rich facts never surfaced** |
| **L4 generation** | Does the LLM produce a correct, complete answer? | **temperature non-determinism + shallow evidence** |
| L5 eval | Are we measuring accurately? | single-run judge variance (Workstream 4) |

This slice attacks **L3 + L4 only** — the cheap, reversible, code-level fixes. All three
root causes below were verified against `apps/admin-console/backend/api/chat.py` on 2026-07-07.
L1 (data-pipeline) and L2 (retrieval architecture) are separate workstreams.

## Root causes (all three verified in code)

### RC1 — List entities return name+snippet only (largest cluster, ~6/19)
`_build_chat_response` enriches **single entities only** (chat.py:3958-3972 — guarded on
`professor_id` / `company_id` / `paper_id`). List queries populate `matched_professors` /
`matched_objects` (lists), never the single-id keys, so the rich-fact fetchers
(`_prof_rich_profile_facts`, `_company_rich_facts`) are **never called** for list paths.

**Refinement found during verification:** even if the fetchers were called, the list
renderer `_build_evidence_blocks` (chat.py:3633-3650) renders each list entity as
`name, institution, matched_topics` only. Rich facts would not reach `evidence_text`.
So RC1 requires **two** edits: fetch + render.

Affects: qid3, qid9, qid21, qid27 (and depth for qid7).

### RC2 — Knowledge queries web-search the raw, over-contextualized query (~3/19)
chat.py:3982 calls `web_provider.search(query)` with the raw user query. Sub-questions like
"在真实数据采集路线中，有哪些具体方式" are context fragments Bocha cannot match → 0 results
→ no web evidence → synthesis has nothing to say.

Affects: qid19, qid20, qid22. (Note: these are `is_head_turn=True` standalone knowledge
questions, NOT multi-turn follow-ups — the earlier "multi-turn" diagnosis was wrong.)

### RC3 — Synthesis LLM call has no temperature → non-determinism (~1+ cases)
`_call_gemma_synthesis` (chat.py:3840) calls `client.chat.completions.create(...)` with no
`temperature`. The LLM default (~0.7) makes identical queries produce different answers.
qid11's answer is verified correct (821 chars, real summary) but eval flaps 0.00 ↔ 1.00.

Affects: qid11 + inflates cross-run variance on every edge case.

## Design

### Fix 1 — List-entity enrichment (fetch + render)

**Fetch** — in `_build_chat_response`, after the single-entity block (chat.py:3972):
```text
for prof in matched_professors[:3]:
    pid = prof["professor_id"]
    rich = _prof_rich_profile_facts(conn, pid)   # awards / education / work / summary
    prof["rich_facts"] = _compact_prof_rich(rich)  # pick top-2 facts, ~150 chars
for obj in matched_objects[:3]:
    if obj is a company:
        rich = _company_rich_facts(conn, obj["company_id"])  # products / team / news
        obj["rich_facts"] = _compact_company_rich(rich)
```
- `matched_objects` may be companies OR papers; gate on presence of `company_id`.
- `_compact_*` helpers pick the 1-2 highest-signal facts (top award; flagship product; one-line
  research summary) and cap length — avoids token bloat from dumping every award/product.

**Render** — extend the list renderers in `_build_evidence_blocks`:
- matched_professors (chat.py:3633-3650): append `；亮点：{rich_facts}` to each summary.
- matched_objects path: same pattern for company rich facts.

**Token discipline:** top-3 entities × ~2 facts × ~150 chars ≈ 6 extra evidence blocks
(~900 chars). Bounded; does not regress profile queries.

### Fix 2 — LLM query reformulation for web search (local qwen3.6)

**New helper** `_reformulate_query_for_search(query) -> str`:
- LLM: `resolve_professor_llm_settings(None)` → local qwen3.6 (the free, locally-deployed
  model — NOT deepseek-v4-pro, which is an external API). temperature=0, short timeout.
- Prompt (system): "将用户问题改写为适合网络搜索的关键词组合：保留核心意图，去除上下文
  引用，补充相关领域术语。只输出关键词，不要解释。" Output is keywords only.
- Used **only** as the search query; synthesis still receives the raw user query (so the
  answer responds to what the user actually asked).

**Trigger discipline** (cost + correctness):
- Only when `intent == "qa"` AND the first `web_provider.search(query)` returned 0 organic.
- Retry once: `web_provider.search(reformulated)`. If still 0, fall through (no infinite loop).
- Guarded in try/except — a reformulation failure must never break the response
  (best-effort web-augment contract, CLAUDE.md §5).

### Fix 3 — temperature=0

Add `temperature=0` to the `create(...)` call at chat.py:3840. One line. Applies to all
synthesis calls uniformly (profile/list/qa/paper/patent) — deterministic, reproducible eval.

## Verification

- Command: `eval_true_accuracy.py --runs 3` (3-run median, proxy unset, backend DOWN to
  avoid the Milvus single-writer lock — env-proxy-bypass + milvus-single-writer memories).
- Target: 9/19 → ~12-13/19 (~60-70%). Gates:
  - No regression on stable-pass retrieval cases (qid1/3/14/16/17/18/23/24/26).
  - qid19/20/22 rise from 0.00 to substantive (Bocha now matches reformulated keywords).
  - qid11 stabilizes (no more 0.00↔1.00 flapping).
- Evidence is fresh-pipeline (not cached artifacts) — validation-methodology memory.

## Rollback

Each fix is one localized edit, one git commit. `git revert <sha>` per fix. No schema,
no migration, no data, no public-API change. Order of commits: Fix3 (1 line, zero risk)
→ Fix1 → Fix2, so a partial revert is meaningful.

## Non-goals (explicit, to prevent scope creep)

- Multi-turn dialogue session context — qid19/20 are standalone; multi-turn is a future
  capability, not a current accuracy blocker.
- Cross-domain graph search (qid13) — Workstream 2.
- Professor-topic recall quality (qid27 retrieval) — partially helped by Fix1 depth, but the
  recall bug is Workstream 2.
- Rejection-template completeness (qid6) — separate tiny slice, not here.
- Data population pipeline (companies/papers/professors at scale) — Workstream 3.
- Eval methodology redesign (semantic similarity, held-out set) — Workstream 4.

## OpenSpec consideration (decision needed at review)

These fixes are behavior-affecting (they change answer/citation output), so CLAUDE.md §8
technically requires an OpenSpec change. Options:
- (a) Fold into the existing `openspec/changes/intent-aware-synthesis/` as a continuation
  (it already exists and is implemented; these are a depth refinement on top). ← recommended
- (b) New small change `openspec/changes/synthesis-depth-enrichment/`.
- (c) Treat as continuation; this design doc + the change log is the contract.

Recommendation: **(a)** — these fixes are the natural depth follow-on to intent-aware
synthesis, and (c)'s "design doc as contract" under-weights the behavior-contract rule.
Flag for user decision before implementation.
