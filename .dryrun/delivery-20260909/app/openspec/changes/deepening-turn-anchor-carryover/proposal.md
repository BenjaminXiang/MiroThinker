# Proposal: deepening-turn-anchor-carryover

> Behavior-affecting: YES. Capability owning the behavior contract: `canonical-v2-chat`.
> Registered from follow-up residual
> `.agents/runs/followups/2026-08-13-subject-consistency-phase2-residuals.md` §1
> (highest-priority residual of the phase-2 subject-consistency arc, HEAD `45d39dd`).

## Why

A deepening turn — a follow-up that keeps the conversation's subject and asks about a
new aspect of it — still loses the subject upstream of every phase-1/phase-2
subject-consistency mechanism. Two production-evidenced triggers (both reproduced on
pre-fix production, `phase2_prefix_prod_probe1_r2_t3.sse` / `phase2_prefix_prod_probe3_t2.sse`):

- **Trigger A.** `介绍一下 国际先进技术应用推进中心（深圳）` → `有没有更详细的信息` →
  `它有哪些布局和进展`: the turn-3 views came back fully unpinned
  (`具身智能布局进展`, `具身智能产业链布局`, …), all 10 web results were off-topic, and the
  answer subject became an unrelated vector-lane professor record (张天尧, HIT-SZ).
- **Trigger B.** `国际先进技术应用推进中心（深圳）` → `这个中心的企业培育情况怎么样`:
  views unpinned (`企业培育中心 运营模式`, …), 8/8 web results junk (漕河泾/广州/新湖南),
  answer subject became 深圳前海微众银行 with mid-sentence truncation.

Root causes (three, compounding):

1. **Deepening turns carry no subject at plan level.** A referential deepening wording
   is neither continuation intent (which requires 更/再 + 详细/具体/深入/展开) nor a recognized
   singular/set referent (generic institution nouns — 该中心/这个中心/该机构 — are absent from
   `SINGULAR_REFERENT_MARKERS`). The fresh-turn soft-subject derivation rejects the
   referential phrase (whole-query echo guard), so no `soft_context_subject` reaches the
   planner: views are unpinned, the web lane retrieves generic junk, and the vector lane
   captures the answer subject.
2. **The soft subject is destroyed at commit time.** The commit-path keep condition is
   continuation-only; on a deepening turn it re-derives the subject from the referential
   query (garbage guards reject it → None), so the stored `soft_subject_name` is lost for
   every later turn.
3. **Vector-lane records can capture the session anchor.** When a leaked canonical record
   enters a web-only answer (the register's 李成睿/张天尧 observations), the answer commit
   (`knowledge_answer.py` `_commit_prose_scope`) lets that single selected handle take over
   `active_anchor`, and the chat adapter commits the receipt as-is. Later referential turns
   then bind the junk canonical anchor, and the canonical binding outranks the soft subject
   (the soft-injection leg requires `not displayed_ids`).

## What Changes

1. **Anchored-deepening recognition** (`followup_referents.py`): a new
   `has_anaphoric_subject_reference` predicate for generic referential institution nouns
   (该/这个/此 + 中心/机构/组织/平台/单位/项目/实验室/研究院/研究所/基地/联合体), and a
   `is_subject_carryover_reference` predicate that classifies a turn as a subject-carryover
   deepening when it is a continuation intent, an anaphoric subject reference, or a
   domain-unconstrained singular referent — and the query names no explicit subject of its
   own.
2. **Carry-over at the chat layer** (`canonical_v2_chat.py`): on subject-carryover turns the
   stored soft subject is injected as `soft_context_subject` (same leg as continuations),
   kept on the committed session, exempted from referent clarification, and — when a
   canonical anchor is active — bound into planning exactly like a typed singular referent.
   Person-typed pronouns over an organization-level soft subject stay a clarification, and
   explicit named subjects still win over any carried anchor.
3. **Anchor-capture guard** (`canonical_v2_chat.py` commit): on a soft-anchored turn that
   planned no canonical displayed ids, a canonical `active_anchor` returned by the answer
   survives only when its display name plausibly matches the turn's subject; a
   name-mismatched canonical handle (the vector-lane leak shape) is dropped from the
   committed receipt so it cannot poison later referential turns. Web handles are never
   dropped.
4. **View-pin observability** (`knowledge_serving_isolated.py`): when the soft-subject
   protected-slot append re-pins rewrite views that dropped the subject, a journal marker
   (`view repin`) is logged, making the tripwire observable in production logs. The
   pinning itself already exists (protected-slot missing-append); this change pins it as a
   plan-level invariant with tests.

Non-goals (unchanged from the phase-2 arc):

- No change to A–G semantics, clarification/candidate machinery, or the never-refuse
  invariant; a subject-carryover deepening turn answers about the carried subject.
- No alias registry; subject-name matching for the anchor-capture guard is a conservative
  containment/overlap heuristic, dropping anchors is fail-safe toward the soft subject.
- Prose truncation reaching the client (register §2) and web-lane `unavailable` telemetry
  (register §3) remain out of scope.

## Capabilities

### Modified Capabilities
- `canonical-v2-chat` — adds the deepening-turn subject-carryover contract, the
  anchor-capture guard, and the view-pin invariant on top of the requirements introduced by
  `followup-subject-consistency` (that change is deployed but not yet archived; this delta
  extends, and does not relax, its requirements).

## Impact

- `apps/miroflow-agent/src/data_agents/canonical_v2/followup_referents.py` (new predicates),
  `apps/admin-console/backend/services/canonical_v2_chat.py` (injection/keep/exemption/
  binding legs, commit-time anchor sanitize), `apps/miroflow-agent/src/data_agents/canonical_v2/
  knowledge_serving_isolated.py` (journal marker only).
- No schema/migration change; no SSE contract change; `TurnRequest`/`QueryPlanningRequest`
  shapes unchanged (soft_context_subject already exists).
- Deployment: production restart required after acceptance (not part of this slice).
