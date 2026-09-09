# Verification Contract — followup-subject-consistency

> Written retroactively (OpenSpec backfill, plan Task 9). The change shipped under the
> Superpowers SDD workflow, which carried the RED/GREEN definitions per task in
> `docs/superpowers/plans/2026-08-12-web-answer-subject-consistency-phase2.md`; this
> contract records that verification intent in OpenSpec terms. Behavior contract:
> `openspec/changes/followup-subject-consistency/` (capability `canonical-v2-chat`).
> Design: `docs/superpowers/specs/2026-08-12-web-answer-subject-consistency-phase2-design.md`.

## Change

- **change-id:** `followup-subject-consistency` (OpenSpec backfill; behavior-affecting:
  web-lane follow-up continuation, soft subject anchoring, subject-consistency gating,
  branch pinning, multi-branch guidance, authority views, correction fetch, stream
  fail-open correction, never-refuse fallbacks).

## Classification

- **Deterministic units** (identity-form split, tier classifier, gate ordering/backfill,
  qualifier extraction/pinning, guidance and authority-view builders, anti-echo guard,
  continuation predicates, soft-subject derivation guards, subject-organization check):
  unit/contract tests allowed as RED for those units (Superpowers TDD, executed per plan
  task Steps 1-2), but they do NOT constitute acceptance.
- **End-to-end behavior** (multi-turn subject consistency, multi-branch guidance effect,
  stream correction in a live SSE flow, turn-1 anchoring): LLM-branched and
  session-stateful → **scenario eval**: production-replica replay of three fixed sessions
  against `/api/chat/stream` with per-turn PASS criteria, then production smoke. Unit
  tests alone are not sufficient GREEN for these slices.

## RED

- **Per task (deterministic):** the plan-mandated failing tests, written before each
  implementation step (per-task Step 1/2; expected failure shapes recorded per task in the
  plan). Test names per task: `verification.md` §RED→GREEN mapping.
- **End-to-end:** the first Task-8 production-replica run (commits `7cad141..377f249`)
  served as the behavioral RED for the two amendment slices: unqualified session **FAIL**
  (deterministic 合肥-only answer — no anchor on fresh turns) and badcase T3 **FAIL** on
  first attempt (SIAT-organized answer passed the mention test). Evidence:
  `evidence/phase2_badcase_t1..t3.sse`, `evidence/phase2_unqualified_t1.sse`.
  Phase-1 RED: production badcase recorded in
  `.agents/runs/followups/2026-08-11-web-lane-subject-consistency.md` (wrong-institution
  answers + refusal-shaped degradation, 2026-08-11 smoke).

## GREEN

- **Per task:** the same tests passing after implementation, plus the per-task regression
  command from the plan (file-level suite + ruff) green at each commit. Unit GREEN alone
  does not close the behavior slices.
- **End-to-end (acceptance oracle):** the Task-8 re-run after Tasks 10/11 (HEAD
  `6af3715`) — **3/3 sessions PASS, first attempt, no retries** — against the verbatim
  PASS criteria in `openspec/changes/followup-subject-consistency/acceptance.md` §1;
  followed by production deploy to 18188 and production smoke PASS (§3).
- **Regression:** full `tests/canonical_v2/` suite green except the known baseline
  `test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers` (fails on HEAD
  before this work); admin-console chat suites 140/140; chat UI node tests 87/87.
- **Invariants:** never-refuse (no new refusal/interrogation channel); company-entity
  behavior (legal-suffix truncations stay full-name forms); session-transition
  (topic_switch) semantics byte-identical; `content_sha256` callers see a byte-identical
  `TurnRequest`/`ContextReceipt` shape (pop-when-None serialization).

## Environment invariants (e2e)

- Production-replica on a separate port (39878) with a bind-mounted copy of the Milvus
  index (single-process lock); production 18188 untouched during verification.
- Sessions use per-session cookie jars against `/api/chat/stream` (`curl -N`, 150s+
  timeout); one retry allowed per borderline turn before calling a failure.
- The retest instance shares the production Postgres `web_search_cache` (24 h TTL,
  query-keyed) — identical queries on a warm cache return byte-identical SSE (temp=0);
  retries must account for this.

## Honest scope (not claimed)

- Official-site fetch injection on the hot path (original R3) remains deferred.
- E2E verdicts rest on single-sample sessions per turn; cold-cache retrieval variance can
  still shift web tops. The re-run unqualified answer enumerated only the 合肥 branch; the
  explicit city invitation covered the criterion.
- First-run control-session SSE dumps were not preserved (verdict recorded in the SDD
  ledger; re-run control dumps are the committed evidence).
