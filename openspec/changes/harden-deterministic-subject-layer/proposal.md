# Proposal: harden-deterministic-subject-layer

> Phase 3 of Epic `fix-round-1-serving-pipeline` (opened 2026-08-18,
> agent-governed per AGENTS.md §3). Human docs:
> plan `docs/plans/2026-08-17-systematic-fix-round-1.md` ·
> log `docs/plans/2026-08-17-systematic-fix-round-1-log.md`.
> Behavior-affecting: YES. Capability: `canonical-v2-chat`.

## Why

Four traced failure forms share one root: the deterministic subject layer
(the session anchor + referent machinery) binds the WRONG subject or refuses
to bind any.

- **P1/G1+G3 (anchor lift-up)**: a news-headline page title
  ("河套深圳园区打造深港科技创新聚集地 - 香港中联办") becomes the session's
  active anchor on a web-only turn — `_sanitize_soft_turn_anchor` explicitly
  never drops web handles — and every later turn answers ABOUT the headline.
  V2 replay also caught the drift variant (G2 T2 answered about
  中国科学院深圳先进技术研究院 — a wrong entity).
- **P3 (bare-name paralysis)**: the anti-echo guard misfires on bare
  institution-name openings, forcing a "指谁" clarification loop.
- **P4 (title-as-institution)**: person-referent turns ("他有哪些论文") over a
  poisoned session lack a type-aware clarification gate and a synthesis-side
  referent type check.
- **P6/G5 (expansion base drift)**: "还有哪些类似的公司" answers from a base
  the user never named (微众银行) — expansion must lock to the session
  subject.

## What Changes

1. **News-headline anchor guard (3.4)**: headline-shaped names (source-suffix
   " - X" pattern, event-verb markers 打造/推进/揭牌/成立…, sentence-length)
   never become the session anchor. On a soft-anchored turn whose receipt
   anchor is headline-shaped: keep the previous session anchor when present,
   else fall back to the soft subject; never bind the headline.
2. **Expansion base = session subject (3.3)**: expansion-family turns
   ("还有哪些类似的…") carry the session subject/anchor into their retrieval
   views; no silent base substitution. Assertion: G5 answer set derives from
   the session subject's domain peers.
3. **Echo-guard relaxation (3.1)**: a bare entity-name query is a subject
   statement, not an echo — no clarification loop on bare institution names.
4. **Type-aware clarification + synthesis referent-type check (3.2)**:
   person-referent turns over org-anchored sessions (and vice versa) trigger
   the clarification gate BEFORE synthesis; synthesis re-checks that the
   answer subject type matches the referent type.
5. **Session-reset semantics verification (3.5)**: P7 already adjudicated
   (product contract, cookie carryover) — record the verification note only.

Out of scope: LLM contextual understanding (Phase 6), data coverage
(Phase 4), answer wording contracts (Phase 2, done).

## Impact

- `apps/admin-console/backend/services/canonical_v2_chat.py` — anchor
  sanitize (headline guard), clarification gate (echo + type-aware),
  expansion planning inputs.
- `apps/miroflow-agent/src/data_agents/canonical_v2/followup_referents.py` —
  bare-name/echo classification, referent typing.
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
  — expansion query-view binding (if view construction lives serving-side).
