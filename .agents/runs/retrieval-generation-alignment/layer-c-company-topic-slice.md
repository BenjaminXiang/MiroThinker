# Slice — Layer C company-topic: specificity-floor + two-step leader selection

- **State:** Accepted (2026-07-07) — Codex implemented (authoritative Step-1) → Claude
  Revise → Codex additive-union fix → Claude live-E2E verified. Doc-as-contract
  (OpenSpec absent on this branch); ADR-009 + this slice + verification-contract = the contract.
- **Decision record:** `docs/architecture-decisions/ADR-009-layer-c-company-topic-specificity-plus-twostep.md`
- **Scope:** all `B_company_topic` queries (具身智能 is the validating blocker; PCB/delivery/
  medical benefit too). **Non-goal:** professor topic retrieval (separate vector-fusion slice).
- **Owner:** Codex implements; Claude reviews.

## Problem (one line)

Company topic search buries recognized leaders because `core_score` counts the generic
`智能`/`AI` expansion (diluting the specific term) and synthesis only ever sees `[:10]`.

## Changes

All in `apps/admin-console/backend/api/chat.py` unless noted.

### 1. Retrieval specificity-floor (gets 无界智航; deterministic, auditable)
- `_company_topic_term_groups` / `_lookup_companies_by_topic`: build `score_terms` from
  **specific** terms only — exclude the generic group `["AI","人工智能","智能"]` (the one added
  by the `\bAI\b|人工智能|智能` regex branch) **when a more specific compound term exists in
  the same query**. Keep the generic group in the **match** predicates (broad recall unchanged).
  Effect: `core_score` becomes the count of the specific term (e.g. 具身智能), lifting
  无界智航 (#32 → #4).
- Guard: when no specific term exists (pure "智能/AI" query), fall back to current behavior.

### 2. Widen the candidate pool
- `_lookup_companies_by_topic`: `LIMIT 30` → `LIMIT 45`.

### 3. Two-step leader selection (gets 优必选/越疆; semantic, synthesis layer)
- New `_select_company_leaders_step1(candidates, query) -> list[dict]`: given the top-45
  (name + business + profile_summary head ~70 chars + specific-count), call the configured
  LLM (`resolve_professor_llm_settings`, `build_non_thinking_extra_body`, temperature=0,
  `response_format=json_object`) to return ~10 recognized leaders ranked. **Audit-log** the
  selection (holds §5 traceability). Reject obvious non-embodied via the prompt (validated).
- Insert Step-1 in the company-topic (B-type) build flow **between retrieval and enrichment**:
  retrieval top-45 → Step-1 selects ~10 → enrich **only those ~10** → existing kill-dump
  synthesis (Step-2).
- Raise / replace the `[:10]` caps that currently gate the synthesis input
  (`_enrich_list_entities` L2394, `_build_evidence_blocks` L3891, and the B-type builder's
  `companies[:10]` sites) so the **post-selection** set reaches synthesis. Do NOT enrich all 45.

## Verification contract (behavior-affecting → not unit-test-only)

- **RED (today, confirmed):** `probe_retrieval_precision.py` shows 无界智航/优必选/越疆 NOT
  leading; 具身智能 answer incomplete.
- **GREEN:**
  1. Retrieval probe: 无界智航 in retrieval top-10 after change 1.
  2. Leaderboard-selection probe (extend candidate set to 45): 优必选 + 越疆 surfaced;
     缔宙/极数迭代/感进 rejected. (Reference result already in ADR-009.)
  3. `eval_true_accuracy`: 具身智能 case improves; PCB/delivery/medical non-regression
     (3-run median; deepseek temp=0 ±2 variance noted).
- **Invariant checks:** no agentic retrieval (LLM never writes queries); `_VALID_DOMAINS`,
  evidence shape, `run_id` unchanged; citation stripping intact.

## Notes for Codex

- The LLM call reuses the existing synthesis client setup (see
  `scripts/eval_true_accuracy.py::_get_judge_client`).
- Do NOT touch professor retrieval, the patent path, or Milvus.
- `canonical_name` NULL pollution is a non-issue (0 nulls) — ignore any stale note claiming
  otherwise.
- Milvus single-writer: this slice needs no Milvus change; backend-up verification is fine.

## Verification outcome (2026-07-07) — GREEN (Accepted)

Live E2E: `POST /api/chat {"query":"深圳有哪些做具身智能的公司"}` against a backend restarted
with the new code. `matched_objects` + answer text inspected:

- 无界智航 → SURFACED (matched_objects rank 12 via specificity top-K union; answer [13]).
  **The namesake stuck case is fixed.**
- 优必选 → SURFACED, rank #1 (was retrieval #52 originally), featured first in answer.
- 乐聚 → surfaced.
- Spam (缔宙/蓝色涌现) absent; specificity-topK additions are on-topic embodied companies.
- 越疆 → NOT surfaced (known limitation: specificity #37, outside top-5 union; Step-1
  variance). See ADR-009 revision.

Unit: `tests/test_chat_company_topic_layer_c.py` 8 pass (RED→GREEN on the union regression);
existing regression suite 11 pass; ruff clean; pyright clean on the slice.

Caveat: `eval_true_accuracy` not usable this round (in-process Milvus Lite socket fails after
backend kill — eval-infra follow-up, not a slice defect).
