# Design: Web Answer Subject Consistency — Phase 2

Date: 2026-08-12
Status: Approved (brainstorming complete), pending spec review
Worktree: `codex/canonical-v2-s12a-ready`
Predecessors:
- `1b0ec2a` chat-ui iOS keyboard + retrieval-process fixes
- `27d0231` follow-up elaboration binding (continuation recognition + soft subject anchor)
- `a9b695b` web result listing in the retrieval-process disclosure
- `50c4f3a` dual-provider corroboration boost + subject-consistency gate (FLOOR) + off-anchor correction retry + never-refuse fallbacks
- Follow-up record: `.agents/runs/followups/2026-08-11-web-lane-subject-consistency.md`

## Background

Phase 1 (50c4f3a) fixed wrong-institution answers for web-only subjects via a
binary subject-consistency gate (hit / miss) and an off-anchor correction
retry. Production verification surfaced three deeper problems that phase 1
cannot express:

1. **Multi-branch organizations.** `国际先进技术应用推进中心` is a national
   institution with branches in Hefei (HQ, 2022), Guangzhou Nansha (2023) and
   Shenzhen (2025), abbreviated `国先中心`. Phase 1 treats the unqualified full
   name as a plain "hit", so content about *other branches* and content about
   the anchor branch are indistinguishable, while `南开国际先进研究院`
   (a genuinely different institution) still passes via the compact alias
   `国际先进`.
2. **Qualifier intent.** When the user explicitly says `深圳`, the answer must
   be pinned to the Shenzhen branch. When the user gives no city, other
   branches' content is *not wrong* — the system must answer fully and only
   then guide the user to specify a branch. No refusal in either case.
3. **Authority sources are reachable but unused.** Encyclopedic pages
   (Baidu Baike entry 62380109 covers all branches) carry the richest
   on-subject content, but (a) retrieval queries never seek them out, and
   (b) plain-HTTP fetching of Baike hits an anti-bot wall (verified
   2026-08-12: `百度安全验证` + HTTP 403, 0 body keywords), so only the
   tiered fetcher's headless-Chromium tier can read them.

## Goals

- G1: Rank web evidence by three relevance levels — anchor branch, same
  organization, wrong organization — instead of binary hit/miss.
- G2: When the anchor carries an explicit location qualifier, the final
  answer (sync and stream) must land on that branch; drift triggers the
  existing correction path.
- G3: When the anchor is an unqualified multi-branch organization name,
  answer fully (other-branch content is legitimate), correctly attribute
  branch facts, and naturally guide the user to name a city — never refuse,
  never interrogate.
- G4: Surface authority sources (Baike / official site) through deterministic
  query-view enrichment.
- G5: On the correction path only, fetch at most one authority page through
  the existing tiered fetcher to give the retry real material.

## Non-goals

- No changes to the clarification/candidate (`entity_id_hint`) machinery;
  branches are not canonical entities and do not enter that pipeline.
- No alias registry or hand-maintained entity knowledge base; all branch
  detection is derived from evidence text.
- No tier1 (headless Chromium) fetching on the hot path; it is confined to
  the correction path.
- No frontend changes. The final `answer` SSE event already triggers a full
  re-render when it differs from the streamed text (kept since `1b0ec2a`).
- No changes to deterministic referent clarification for genuinely ambiguous
  referents (existing feature, orthogonal).

## Design

### §1 Three-tier subject-consistency gate

Extend `_apply_web_subject_consistency` in
`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
to classify each web result into ordered tiers:

| Tier | Meaning | Rule |
|------|---------|------|
| T0 | Corroborated by both providers | existing `corroborating_provider_versions >= 2` |
| T1 | Anchor-branch hit | qualified form (`国际先进技术应用推进中心（深圳）`, `国先中心（深圳）`) or full org name co-occurring with the anchor's qualifier (`深圳`) |
| T2 | Same-organization hit | unqualified full name (`国际先进技术应用推进中心`) or generic short form (`国先中心`) with no other-branch qualifier |
| T3 | Other-branch content | org name attached to a *different* qualifier (`合肥`, `南沙`, `大湾区`) |
| T4 | Loose-alias hit only | compact generated aliases (`国际先进`, ≤6 chars) — the `南开国际先进研究院` leak channel |
| T5 | No match | — |

Gate rules:

- `kept = T0 ∪ T1`.
- When `len(kept) >= FLOOR (3)`: **drop T4 and T5 only**. T2/T3 are always
  retained (same-organization background is valuable) but ordered after
  T0/T1 and before T4/T5.
- When `len(kept) < FLOOR`: backfill in tier order T2 → T3 → T4 → T5 until
  FLOOR is reached (input never maps to empty; the lane-unavailable error
  branch stays unreachable, as in phase 1).
- `_web_identity_forms` output is split into **full-name forms** (complete
  normalized identity, parenthesized variants, and the existing
  company-legal-suffix truncations such as `深圳市普渡科技有限公司 → 普渡科技`)
  and **compact aliases** (generated short mention forms). Company entities
  keep current behavior: their truncations count as full-name forms, so the
  canonical-entity control path (e.g. 普渡科技) is unaffected.
- The anchor's own qualifier set is derived from the anchor name
  (parenthesized qualifier) or from qualifier co-occurrence in the user
  query (full name + `深圳` in the same query). Other-branch qualifiers are
  detected from evidence titles/snippets where the qualifier attaches to the
  org name, not from cities appearing anywhere in the text.

### §2 Qualifier pinning + stream final-answer correction

- **Detection upgrade (shared by sync and stream).** When the anchor has an
  explicit qualifier, the off-anchor check is strengthened: the answer must
  contain the org name co-occurring with the qualifier (T1 form). Answers
  that only cover the org generally or other branches count as off-anchor
  and trigger one corrective re-synthesis. Without a qualifier, T1/T2 forms
  pass; only wrong-organization drift triggers correction.
- **Correction message (qualified anchors).** "聚焦'{anchor}'（深圳分部）作答；深圳分部的公开信息不足时，基于已确认的信息概括作答，涉及其他分部的内容须明确归属，不得反问用户。"
- **Stream path.** Chunks continue to stream as today. After the stream
  completes, the accumulated text goes through the same detection; on drift,
  run one non-stream corrective re-synthesis (with §3 fetch when applicable)
  and emit the corrected text as the final `TurnResult.answer_text` /
  `answer` SSE event. The frontend's existing mismatch path re-renders, so
  the user may briefly see the streamed draft but the settled answer is the
  corrected one. On repeated failure, fall back to the deterministic path
  (existing). A free-form `limitations` marker (e.g.
  `stream_answer_anchor_corrected`) is added for observability.
- **Cost.** +1 LLM call only when detection triggers; no change on the
  happy path.

### §2b Prompt-driven multi-branch guidance (no qualifier given)

- **Deterministic detection, LLM expression.** When the anchor is an
  unqualified organization name AND evidence contains ≥1 other-branch
  qualifier attached to the org name (T3 classification, deterministic and
  unit-testable), inject a situational block into the synthesis messages
  (`_chat_request`, shared by sync and stream):
  - the detected branch list (extracted from evidence, never hardcoded);
  - the fact that the user's question is organization-level;
  - instructions: answer the question fully using organization- and
    branch-level material with correct branch attribution (never assign one
    branch's facts to another); do not refuse or interrogate; if the need
    may be branch-specific, naturally mention the cities where the
    organization has branches and invite the user to name one — woven into
    the answer, not as a boilerplate appendix; if conversation context
    already focuses on one branch, answer for that branch directly and skip
    the guidance.
- **No injection** when zero branches are detected: prompt is byte-identical
  to today (no over-guidance).
- Wrong-organization drift handling (§2) is unaffected and takes precedence.

### §2c Authority-seeking query-view enrichment

In `_serving_query_views`, when the anchor is an organization-level name
(canonical or soft subject), append up to 2 deterministic views:

- `{subject} 百度百科`
- `{subject} 官网`

These merge with the existing deterministic view / LLM rewrites / term view
(deduplicated) and run through the normal dual-provider lanes. Cost: ≤2
extra provider calls per qualifying turn. Effect: encyclopedic and official
entries enter the candidate pool, where §1 typically ranks them T0 (often
corroborated) or T1/T2.

### §3 Correction-triggered tiered fetch

- **Trigger:** immediately before the corrective re-synthesis (§2), low
  frequency by construction.
- **Candidate selection (≤1 URL):** prefer a URL whose domain matches the
  anchor (`_web_identity_domain_matches`, official site); otherwise the
  first result (in tier order from §1) whose title hits the anchor identity
  forms — in practice these are encyclopedia or government pages. No
  candidate → skip fetch.
- **Fetch:** reuse `providers/page_fetch.py` `create_tiered_page_fetcher`
  (tier0 httpx+BS4 → tier1 lazy headless Chromium). Overall hard timeout
  ~10s (configurable). PDF/non-HTML skipped. Tier1 cold start (5–10s) is
  accepted on this rare path only.
- **Anti-echo guard:** fetched body text must contain the anchor
  organization name; otherwise discard and retry without injection (the
  fetched page itself may be off-subject even when the domain matched).
- **Injection:** main text truncated to ~1200 chars (following
  `_enrich_with_page_text`) is attached to the correction message as
  reference material, instructing the model to prefer facts directly
  related to `{anchor}`. **Documented compromise:** injected text is outside
  the claims/evidence binding; it steers the retry, but the final answer
  must still select from existing claims.
- **Fail-open everywhere:** fetch error, timeout, guard failure → corrective
  re-synthesis proceeds without injected material.
- **Observability:** `limitations` markers for fetch hit / miss / guard-reject.

## Error handling summary

- Gate never returns empty for non-empty input (FLOOR backfill).
- Correction retry capped at 1; failure lands on the deterministic fallback
  (never a refusal; refusal-shaped texts are still rewritten by the
  adapter's phase-1 soft fallback).
- Fetch is fully fail-open.
- No new refusal channels are introduced; referent clarification for true
  ambiguity is unchanged.

## Testing matrix

Unit / integration (`apps/miroflow-agent/tests/canonical_v2/`,
`apps/admin-console/tests/`):

- §1: tier classification matrix (T0–T5 fixtures incl. 南开国际先进研究院 as
  T4, Hefei/Nansha content as T3, 国先中心 alias forms); kept/drop/backfill
  order; company-entity regression (普渡科技 path unchanged); soft-subject
  binding still feeds the gate.
- §2: qualified-anchor detection (org-only answer → off-anchor; T1 answer →
  pass); unqualified-anchor detection (T3-bearing answer → pass, SIAT answer
  → retry); stream path — drifted stream yields corrected final answer_text
  (chunks published unchanged), retry failure → deterministic fallback,
  on-anchor stream → single synthesis.
- §2b: injection condition (org-level anchor + ≥1 T3 branch → block present
  with correct branch list; zero branches → prompt unchanged; single-branch
  focus in context → no guidance); fake-LLM behavior test (multi-branch
  evidence → answer contains branch notes + guidance, correct attribution).
- §2c: views appended for org-level anchors, dedup against existing views,
  absent for non-qualifying anchors.
- §3: candidate selection rules; tier0 success injection; tier0 blocked →
  tier1 path used; timeout/failure fail-open; anti-echo guard rejects
  off-subject pages; grounding (final answer still claims-bound).
- Contract: `QueryPlanningRequest`/`TurnRequest`/`ContextReceipt` shapes
  unchanged (any new internal fields follow the pop-when-None serializer
  precedent).

End-to-end (local production replica, real LLM + real providers):

- Original badcase three turns (深圳 anchor): answer stays on the Shenzhen
  branch; SIAT/南开 excluded from top web_items.
- Unqualified query (`介绍一下国际先进技术应用推进中心`): full org-level
  answer, correct branch attribution, natural branch guidance present, no
  refusal.
- Control: 普渡科技 two turns, no regression.

Production smoke after deploy: repeat the badcase and the unqualified query
against `127.0.0.1:18188`.

## OpenSpec backfill plan

The repo process (AGENTS.md §9) requires OpenSpec artifacts for the
behavior-affecting work already deployed (`27d0231`, `a9b695b`, `50c4f3a`)
and for this phase. Backfill one change folder covering the follow-up /
subject-consistency arc (proposal, specs delta, tasks, acceptance,
verification contract + evidence), marking phase-1 slices as deployed, this
phase as the implementation target.

## Residual risks

- Tier1 fetch of Baike may still hit anti-bot verification under datacenter
  IPs; guard + fail-open keeps behavior safe (retry proceeds unfed).
- LLM-expressed guidance is nondeterministic by design; behavior is pinned
  at the detection/injection layer and via fake-LLM tests, expression quality
  is monitored via e2e, not unit-pinned.
- Prompt changes (guidance block, correction message) carry a prompt_version
  bump (v15 → v16) and snapshot updates.
- Alias forms are generated, so exotic abbreviations outside
  `_web_identity_forms` may still classify T4; acceptable while FLOOR
  backfill preserves recall.
