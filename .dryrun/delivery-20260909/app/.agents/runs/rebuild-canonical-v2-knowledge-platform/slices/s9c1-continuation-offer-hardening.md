# Slice Contract: s9c1-continuation-offer-hardening

## Status

Accepted at `2026-07-16T04:08:02Z`. S9M and S9AG already freeze and implement all six conditional
continuation reasons, the three-option cap, exact current-handle/current-result-set binding, next-turn selection,
and no-offer behavior. This final Task 9.7 slice closes one concrete remaining trust gap: a typed
candidate can currently pair a supported reason with an arbitrary operation/target and can expose
caller-authored factual prose as its option label.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `9.7`
- Depends on: Accepted S8RG `ContinuationCandidate`/`EvidenceSet`, Accepted S9M continuation RED,
  and Accepted S9AG atomic KnowledgeAnswer mechanics GREEN
- Independent-start authority: the mapping is mechanically decidable from the six Accepted S9M
  fixtures and requires no reviewed S2C case, real provider, safety policy, or durable session

## Goal

Make `ContinuationOffer` executable options server-owned at the final answer boundary:

1. Accept only these already-frozen reason/operation/target combinations:
   - `broad_scope / narrow_scope / current_result_set`
   - `ambiguity / switch_candidate / current_handle`
   - `partial_coverage / continue_coverage / current_result_set`
   - `evidence_gap / targeted_evidence_search / current_handle`
   - `budget_exhausted / resume_bounded_search / current_result_set`
   - `eligible_next_hop / traverse_relationship / current_handle`
2. Replace caller-authored option labels with deterministic neutral server labels. Candidate labels
   remain non-authoritative metadata and never appear in the returned offer.
3. Require a non-empty relationship type only for `eligible_next_hop`; reject a relationship type
   on every non-traversal option.
4. Preserve the already-Accepted candidate order, at-most-three cap, handle/result-set, constraints,
   evidence, relationship type, source-candidate identity, and next-turn selection binding.
5. Return no offer when every selected candidate has an invalid combination.

## Non-goals

- Do not add a global continuation registry, prompt framework, relationship catalog dependency,
  localization layer, scoring/ranking policy, new trigger reason, or new operation.
- Do not change blocking-ambiguity clarification options; `_ambiguity_offer` is separately
  server-generated and already Accepted.
- Do not implement safety guidance, provider/runtime behavior, durable session state, HTTP/admin,
  reviewed claim-level replay, or Tasks 9.2/9.4/9.6/9.8.
- Do not change `knowledge_read.py`, shared contracts, persistence, database/index/source state, or
  active pointers.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`.
- `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py` for exactly
  one new public-behavior test group; existing assertions/fixtures remain unchanged.
- This Slice Contract and, after Candidate review, existing verification/change-log/agent-links,
  portfolio, mainline-plan, `tasks.md`, and the matching continuation acceptance checkbox.

## Interface and compatibility constraints

- No public model, factory, method signature, or serialized field changes.
- Validation stays hidden in the existing `KnowledgeAnswer` deep module. The returned
  `ContinuationOption` remains byte-compatible except that its label becomes server-owned.
- Exact valid S9M options and selections remain unchanged on operation, target, result-set,
  constraints, evidence, relation type, and transition receipt.
- Invalid candidates are omitted rather than repaired into a different operation or target.

## Forbidden changes

- Any production file other than `knowledge_answer.py`, any existing Accepted assertion value,
  assertion weakening, xfail/skip/import masking, test-local implementation, provider/network call,
  or second continuation service.
- Trusting `ContinuationCandidate.label`, accepting an unlisted reason/operation/target combination,
  or emitting an offer with no validated option.
- Commit, Push, PR, archive, Cutover, or external-state mutation.

## Expected unchanged behavior

- The existing 13 KnowledgeAnswer owner groups remain GREEN before the new RED.
- The new focused group makes the owner matrix exactly one real failure before production repair;
  no xfail or absent-module sentinel is introduced.
- After GREEN, the KnowledgeAnswer owner matrix is exactly `14 passed`; complete no-external
  Canonical V2 is exactly `329 passed, 141 skipped, 0 xfailed`, absent concurrent work.
- S1-S8, S9 claim/assessment/session behavior, S10, original PostgreSQL/Milvus/forensic sources,
  release/index state, and active pointers remain unchanged.

## Required checks

- RED: the new focused group fails only because invalid combinations and caller factual labels
  survive the current offer.
- GREEN: the new group passes; existing S9M file and all KnowledgeAnswer owners pass with no
  xfail/XPASS/skip.
- Complete no-external Canonical V2 is `329 passed, 141 skipped, 0 xfailed`.
- Scoped Ruff check/format, `py_compile`, and complete Canonical V2 Pyright pass.
- Strict OpenSpec, `git diff --check`, scope, high-confidence secret, generated-cache, fresh offline
  wheel/package-content, and frozen-source checks pass.
- One merged independent implementation/test-integrity review reports zero open Critical/Important
  findings. Minor/YAGNI findings are recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `acceptance.md`, `change-log.md`, and `agent-links.md` after Candidate review.
- `.agents/portfolio.md` and the current code-grounded mainline plan after acceptance.

## Stop conditions

- Correct validation requires a new shared/public contract, relationship registry, provider,
  persistence, consumer, or S2C reviewed case rather than the Accepted six-pair contract.
- Any currently valid S9M option or selection stops working, candidate order/binding changes, a
  factual caller label survives, or an invalid operation becomes executable.
- The slice expands into a global policy/localization framework, another S9 task, or retains an open
  Critical/Important finding.

## Done means

- One focused RED proves invalid combination and factual-label leakage, then turns GREEN through the
  existing deep module with all Accepted continuation bindings intact.
- Owner/full/static/strict/package/source checks and one independent review pass with zero open
  Critical/Important findings.
- Task 9.7 and its matching acceptance criterion are checked, moving the formal ledger from 54/80
  to 55/80. Aggregate S9 and Tasks 9.2/9.4/9.6/9.8 remain open.

## Plan

1. Add one focused public-behavior test to the existing multi-turn owner and capture exact RED.
2. Add one private immutable allowlist plus neutral-label mapping in `knowledge_answer.py` and filter
   candidates before option construction.
3. Run focused/owner/full/static/strict/package/source checks and one independent read-only review.
4. Persist Task 9.7 acceptance and the 55/80 ledger without starting another S9 task.

## Rollback note

Remove the new focused test and private mapping/filter, then remove this Slice Contract/evidence and
restore the Task 9.7/acceptance checkboxes. No public schema or external state exists to roll back.

## Acceptance evidence

- The new focused group first failed exactly once because `delete_data` and the wrong target
  combination survived and displaced the later valid candidate; there was no import, fixture,
  xfail, skip, or unrelated failure. It now passes with only the sanitized and valid candidates.
- Focused and complete multi-turn results are `1 passed` and `5 passed`. All KnowledgeAnswer owners
  are exactly `14 passed`; complete no-external Canonical V2 is exactly `329 passed, 141 skipped,
  0 xfailed`. The three warnings remain the S9AG atomic owner's intentional hostile
  `model_construct` serializer warnings.
- Complete Canonical V2 Pyright reports zero findings. Scoped Ruff check/format and `py_compile`,
  strict OpenSpec, `git diff --check`, scope, high-confidence secret, generated-cache, and package
  checks pass.
- Accepted production/test SHA-256 values are
  `43207a6b2aa5619d6c7780af15ee06326c691f316f9b8b8c701b9f6fa37c8f41` and
  `faeba7a23db63143f39f3a5b090c1002607a3d717e3a5cef83064c1cb8aa077d`.
- The fresh 275-entry offline wheel SHA-256 is
  `17d82aa5ce6e0410904b7462d7337603320b1ed3766d00b4052a8312bbe90914`; it includes
  `knowledge_answer.py`, `knowledge_read.py`, and `knowledge_gap_feedback.py`, and excludes tests/
  `.agents` artifacts.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; recovery remains network-
  none/no-port/restart-no; original Milvus SHA-256 remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- The merged review found one Important executable-option gap: missing traversal relation types and
  stray non-traversal relation types survived. The same focused group first failed exactly, then
  passed after a five-line fail-closed repair. Targeted exact-hash re-review returned `ACCEPTED`
  with zero Critical/Important/Minor/YAGNI findings.
- Task 9.7 and its matching continuation acceptance item are checked. The formal ledger is 55/80;
  aggregate S9 and Tasks 9.2/9.4/9.6/9.8 remain open.
