# Proposal: followup-subject-consistency

> **Backfill (AGENTS.md §9).** This change is written retroactively: every slice below is
> already implemented, reviewed, and deployed. Phase 1 shipped 2026-08-11/12 (commits
> `27d0231`, `a9b695b`, `50c4f3a`); phase 2 shipped 2026-08-12/13 (commits `7cad141`,
> `6fda6b6`, `9afe730`, `2686804`, `fdb3e26`, `d8b0da5`, `377f249`, `d3c8ff0`, `6af3715`;
> plan amendment `367fd96`). Production on `127.0.0.1:18188` serves worktree HEAD `6af3715`;
> production smoke PASS 2026-08-13. Evidence: `.agents/runs/followup-subject-consistency/`.
>
> Behavior-affecting: YES. Capability owning the behavior contract: `canonical-v2-chat`.

## Why

The canonical-v2 web lane answers questions about subjects that are not in the canonical
store (web-only institutions). Four compounding defects made those answers untrustworthy:

1. **Context loss on elaboration follow-ups.** After asking about a subject, a natural
   follow-up like `有没有更详细的信息` lost the conversation context and answered with the
   no-context fallback (`当前输入中未提供具体的主体信息或上下文…`). For web-only subjects there
   was no anchor at all: nothing bound turn 2 to turn 1's subject.
2. **Wrong-organization drift via Bocha lookalikes.** The dual-channel web lane returns
   off-entity results for exact-institution-name queries — Bocha's top results were
   uniformly a similarly named wrong institution (e.g. `南开国际先进研究院（深圳福田）`,
   `中国科学院深圳先进技术研究院` fragments for an `国际先进技术应用推进中心（深圳）` anchor,
   verified by direct provider probes). Neither the synthesis step nor the template
   fallback filtered for subject consistency with the anchor, so answers drifted to the
   lookalike. Recorded in `.agents/runs/followups/2026-08-11-web-lane-subject-consistency.md`.
3. **Refusal-shaped degradation.** Under sparse or noisy evidence the lane degraded into
   refusal-shaped output: the synthesis prompt invited the user to provide more clues, and
   degraded/template fallback texts read as refusals instead of answering from what was
   confirmed.
4. **Unanchored fresh-turn org queries** (surfaced by the phase-2 e2e, plan amendment
   2026-08-13). `soft_context_subject` was only injected for continuation follow-ups, so a
   fresh-turn web-only org-level query (`介绍一下国际先进技术应用推进中心`) got NO anchor — no
   gate binding, no authority-seeking views, no multi-branch guidance, no correction
   anchor — and the answer deterministically resolved to the most salient branch
   (合肥-only). Additionally, the qualified off-anchor check was a co-occurrence mention
   test, so an answer organized around a lookalike passed as long as it name-dropped the
   anchor stem once and mentioned the city.

Deeper phase-1 limitations that phase 2 addresses: the binary hit/miss gate could not
distinguish anchor-branch content from other-branch content of a multi-branch organization;
when the user names a city the answer must be pinned to that branch, and when the user
gives no city the system must answer fully and only then guide; authority sources
(encyclopedic/official pages) were reachable but never sought out.

## What Changes

### Phase 1 — shipped and DEPLOYED earlier (2026-08-11/12)

1. **Follow-up continuation semantics + web-only soft subject anchor** (DEPLOYED `27d0231`).
   Elaboration phrasings recognized as continuation intent; a `soft_subject_name` persisted
   on the session for web-only subjects and injected as
   `QueryPlanningRequest.soft_context_subject`, so web-lane views are prefixed with the
   subject, clarification yields, and the turn stays continuation (not topic_switch).
2. **Web results in the retrieval-process disclosure** (DEPLOYED `a9b695b`). The
   `retrieval_done` SSE event gained a backward-compatible `web_items` field so the
   chat UI '查看检索过程' disclosure lists web lane results (title + link + source host).
3. **Dual-provider corroboration + subject-consistency gate + off-anchor correction +
   never-refuse fallbacks** (DEPLOYED `50c4f3a`). Corroboration boost (results returned by
   both Bocha and Serper rank first); binary subject-consistency gate with FLOOR backfill;
   off-anchor detection with one corrective re-synthesis on the sync path (stream pinned
   as uncovered at the time); refusal-shaped degradation removed (prompt_version v14→v15,
   soft non-refusing fallbacks, refusal-rewrite).

### Phase 2 — shipped by this arc (2026-08-12/13)

4. **Identity-form split + relevance tier classifier** (Task 1, `7cad141`): full-name forms
   vs compact aliases; location-qualifier extraction; per-result relevance tiers
   T0 corroborated … T5 no match.
5. **Three-tier subject-consistency gate** (Task 2, `6fda6b6`): T0∪T1 kept first, then T2
   (same org), then T3 (other branch); T4 (loose alias) / T5 (no match) dropped when the
   kept set meets the FLOOR, tier-ordered backfill below it.
6. **Qualifier pinning on the sync answer path** (Task 3, `9afe730`): a qualified anchor
   requires the org stem AND the branch qualifier to co-occur in the answer; miss triggers
   the branch-focused correction.
7. **Stream final-answer off-anchor correction, fail-open** (Task 4, `2686804`): one
   bounded non-stream corrective retry replaces the final answer on drift; on failure the
   original streamed result stands (chunks are irrevocable; never raises for off-anchor).
8. **Prompt-driven multi-branch guidance** (Task 5, `fdb3e26`, prompt_version v15→v16):
   for an org-level anchor whose evidence carries other branches, the prompt instructs the
   model to answer fully, attribute branch facts, and naturally invite naming a city.
9. **Authority-seeking query views** (Task 6, `d8b0da5`): `{subject} 百度百科` /
   `{subject} 官网` views appended for org-level anchors, deduplicated.
10. **Correction-triggered tiered fetch** (Task 7, `377f249`): on the correction path only,
    at most one authority page is fetched through the existing tiered fetcher with an
    anti-echo guard, and carried into the correction message.
11. **Turn-1 soft-subject derivation at the chat layer** (Task 10, `d3c8ff0`, admin-console):
    fresh/explicit-subject turns with no continuation anchor and no canonical ids derive the
    soft subject from the current query, so the gate, authority views, guidance, and
    correction engage from turn 1; session-transition (topic_switch) semantics unchanged.
12. **Subject-organization off-anchor check** (Task 11, `6af3715`): the qualified
    off-anchor check becomes a subject test — the anchor must lead the answer (first
    sentence) or recur in it — not a mere mention test; the unqualified path is unchanged.

End-to-end verification (Task 8): local production-replica replay PASS (re-run, 3/3
sessions first attempt), full regressions green except the known baseline failure, deploy
to production `18188` and production smoke PASS. See `acceptance.md` and
`.agents/runs/followup-subject-consistency/verification.md`.

Non-goals (unchanged):
- Clarification/candidate (`entity_id_hint`) machinery untouched; branches are not
  canonical entities and do not enter that pipeline.
- No alias registry or hand-maintained entity knowledge base; branch detection is derived
  from evidence text.
- No headless-Chromium fetching on the hot path (confined to the correction retry).
- Referent clarification and A–G query classification semantics unchanged.

## Capabilities

### New Capabilities
- `canonical-v2-chat` — follow-up continuation semantics, soft subject anchoring, web-lane
  subject-consistency gating, branch pinning, multi-branch guidance, authority views,
  correction fetch, stream fail-open correction, and never-refuse fallbacks for the
  canonical-v2 chat web lane. (Baseline before this change: current code + the follow-up
  record `.agents/runs/followups/2026-08-11-web-lane-subject-consistency.md`; no prior
  OpenSpec capability spec exists for this lane.)

## Impact

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` (gate,
  identity forms, tier classifier, qualifier pinning, renderer correction sync+stream,
  multi-branch guidance, authority views, correction fetch),
  `apps/miroflow-agent/src/data_agents/canonical_v2/followup_referents.py`
  (continuation intent, `_search_view`),
  `apps/admin-console/backend/services/canonical_v2_chat.py` (soft-subject persistence,
  injection, turn-1 derivation), chat SSE `retrieval_done.web_items` + chat UI disclosure.
- Prompt version bumps: `canonical-v2-prose-v14 → v15` (phase 1, never-refuse) and
  `v15 → v16` (phase 2, multi-branch guidance).
- No schema/migration change; no A–G semantics change; `TurnRequest`/`ContextReceipt` carry
  `soft_context_subject` with pop-when-None serialization so `content_sha256` callers see a
  byte-identical shape; company-entity behavior preserved (legal-suffix truncations remain
  full-name forms, never compact aliases).
- Never-refuse invariant: no new refusal/interrogation channel; off-anchor retry exhaustion
  falls back to the deterministic evidence list rather than a wrong-entity synthesis.
