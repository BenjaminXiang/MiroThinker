# Proposal: layer-d-multi-turn-context

> **Behavior-affecting:** YES — multi-turn chat routing, coreference resolution, and answer
> semantics change. The behavior contract is owned by the new capability
> `chat-multi-turn-context` (this change creates its spec). Decision record:
> `docs/architecture-decisions/ADR-011-layer-d-displayed-set-coreference-anchor-semantics.md`
> (grilling-validated 2026-07-09). Ubiquitous language: root `CONTEXT.md`.

## Why

Multi-turn follow-ups over result sets are broken end-to-end: 上述/这些/他们 resolve to
nothing (only single-entity pronouns are mapped), cross-domain follow-ups over a set
silently degrade to *one arbitrary member's* relations, and the product's own suggested
follow-up chips (看看这些教授的论文 / 上述哪些在深圳 / 这些公司有哪些专利) are not matched by
any routing layer — the UI promises follow-ups the backend cannot honor. This is Layer D of
the retrieval-generation rebuild (`docs/superpowers/specs/2026-07-07-retrieval-generation-rebuild-design.md`,
Slice 4): the context-coherence factor of end-to-end accuracy.

## What Changes

- **Set coreference**: 上述/这些/他们 (and domain-worded forms 上述教授/这些公司) resolve to
  the prior turn's displayed result set (`last_result_set`), per-domain.
- **Result-set semantics narrowed (displayed-only)**: the session result set captures only
  entities the user actually saw (answer list + citations), no longer all retrieval
  evidence. **BREAKING** (internal session semantics, not a public API).
- **Anchor semantics**: list answers no longer push single-entity anchors; a singular
  pronoun (他) after a bare list triggers deterministic clarification instead of silently
  resolving to an arbitrary member.
- **Hybrid routing, A-G unchanged**: a thin rule layer deterministically routes every chip
  text and explicit set-word; the LLM classifier gains an orthogonal `referent: set|entity`
  output for paraphrases. No new top-level query class.
- **Set cross-domain traversal**: batch traversal over the set via per-member
  `get_related_objects` (retrieval-service variant), rendered target-centric by default
  (member-centric when the query says 分别), with a mandatory coverage statement,
  `role_type` surfaced, and candidate links labeled.
- **Narrowing gains three mechanisms by predicate type**: deterministic chip predicates
  (region/recency/grant-status/applicant-type), LLM per-member structured verdicts for open
  predicates (audited), existing topic narrowing unchanged.
- **Chained follow-ups**: traversal/narrowing answers update the result set, so
  教授→上述教授的企业→这些公司的专利 works.
- **Degradation defined**: with classifier or synthesis env-switched off, the deterministic
  base (chips routing, traversal, chip predicates, clarification, deterministic rendering)
  remains fully functional; open predicates degrade to labeled topic-intersection.
- **Multi-turn eval**: a session-sticky eval runner activates the 8 existing follow-up
  golden cases (currently skipped by `is_head_turn`) plus ~6 synthesized dialogs; RED
  baseline archived before implementation.

Out of scope (deferred, per ADR-011): R3 constraint re-query (那广东的呢), R4 answer-text
deixis (第二个是谁), new domains, schema changes.

## Capabilities

### New Capabilities

- `chat-multi-turn-context`: multi-turn session context for chat — result-set memory
  (displayed-set semantics), set coreference, single-entity anchors and clarification,
  set narrowing (three predicate mechanisms), set cross-domain traversal with
  member-target mapping answers, follow-up routing (rules + classifier referent), context
  lifecycle (update/clear), and degradation behavior under env kill-switches.

### Modified Capabilities

<!-- none — no existing openspec/specs/ capability covers chat behavior; A-G classification
     semantics are explicitly unchanged (CLAUDE.md §5 invariant) -->

## Impact

- **Code**: `apps/admin-console/backend/api/chat.py` (routing, session model,
  `_handle_d_narrowing`, C-type path, chips), `apps/admin-console/backend/services/chat_context.py`
  (set-word detection, narrowing helpers), classifier prompt/output schema; new batch
  traversal helper over `apps/miroflow-agent/src/data_agents/service/retrieval.py::get_related_objects`
  (read-only reuse — the HTTP endpoint variant in `domains.py` is NOT used).
- **Tests/eval**: new multi-turn eval runner (session-sticky HTTP, proxy vars unset per
  project memory); `apps/admin-console/tests/fixtures/test_cases.yaml` follow-up cases
  activated; new unit tests for routing matrix, predicates, projection rendering; existing
  single-turn 19-case set is the non-regression guard.
- **Contracts**: `.agents/runs/layer-d-multi-turn-context/verification-contract.md`
  (RED = archived multi-turn baseline; GREEN = ≥12/14 multi-turn pass AND zero single-turn
  regression AND chip routing matrix green).
- **Invariants preserved**: A-G semantics, deterministic/auditable retrieval (LLM never
  selects retrieval), evidence traceability (§5), no schema/migration changes.
- **Dependencies**: none new; uses existing classifier and synthesis LLM lanes and their
  env kill-switches (`CHAT_QUERY_CLASSIFIER`, `CHAT_LLM_SYNTHESIS`).
