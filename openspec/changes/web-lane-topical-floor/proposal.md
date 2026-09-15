# Proposal: web-lane topical floor

## Why

The web lane decides relevance by **identity**, not by the query. Its single
existing filter, `_apply_web_subject_consistency`
(`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py:854`),
keeps three permissive channels open:

- **H1** — no bound entity and no soft subject ⇒ `return results`, unfiltered;
- **H2** — fewer than `_WEB_SUBJECT_CONSISTENCY_FLOOR` (3) kept results ⇒ the
  suspect (T4) and missed (T5) channels backfill up to the floor, so pages the
  gate itself scored as "wrong organization" are re-admitted as filler;
- **H3** — `len(corroborating_provider_versions) >= 2` ⇒ relevance tier 0,
  unconditionally kept, whatever the page says.

Reported case (live 18188, session `bKkX9SSixSj6`, turn 3, query
`详细介绍一下 国先中心（深圳）`): the turn's web evidence was three items —
a Shenzhen weight-loss-camp listing (sohu.com), a municipal platform round-up
(sz.gov.cn) and a company-directory page (11467.com). The weight-loss page is
**tier 5 (wrong organization)** and entered purely through **H2**; the
sz.gov.cn page entered through **H3**. Nothing was dropped, so the turn trace
recorded no gate activity at all (`.agents/runs/web-lane-topical-floor/red-case.md`).

Recall-layer noise is tolerable; noise that survives into the evidence set is
not — it rides into the next turn's session carry-over and dilutes synthesis.

## What Changes

One new, web-lane-only gate, applied after the subject-consistency gate and
again to the enumeration refinement round:

```
_apply_web_topical_floor(results, request) -> tuple[_NormalizedWebResult, ...]
```

A result survives iff

1. it is **identity-exempt** — the same identity口径 as the subject gate
   (`_web_result_hits_bound_entity` name forms, plus the pinyin brand domain
   `_web_identity_domain_matches`, bound names ∪ `soft_context_subject`); or
2. it shares a **core query token** with the query, derived from
   `request.original_query`: CJK character bigrams and latin words, minus
   question scaffolding (`介绍一下`, `有哪些`, …) and minus location
   qualifiers (`_ANCHOR_LOCATION_LEXICON`), so `详细介绍一下 国先中心（深圳）`
   reduces to `{国先, 先中, 中心}`; or
3. nothing could be tested — no core token, or empty title+snippet (fail-open).

Everything else is dropped. The gate is deterministic, model-free, offline:
0.875 ms median for 64 results. Drops are reported as
`record_gate_drop("web_topical_floor", n)`; `record_lane_counts("web", …)`
already sits after it, so `filtered` keeps its "dropped by any gate" meaning.

Kill switch: `CANONICAL_V2_WEB_TOPICAL_FLOOR=0|false|off|no` (default on).

## Out of Scope

- Model-based rerank / cross-encoder scoring (a separate, later layer).
- Retrieval-side ranking, provider selection, quotas.
- `_apply_web_subject_consistency` semantics (H1/H2/H3 stay as they are).
- Local lanes (company/professor/paper/patent) — no code path is shared.
