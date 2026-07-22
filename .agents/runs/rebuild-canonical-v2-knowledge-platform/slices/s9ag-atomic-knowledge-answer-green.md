# Slice Contract: s9ag-atomic-knowledge-answer-green

## Status

Accepted at `2026-07-16T03:36:43Z`. Baseline evidence on `2026-07-16` was exactly
12 strict xfails and 12 forced failures;
11 forced failures are exact `_MissingKnowledgeAnswerModule` sentinels and S3A is the one broad
`ModuleNotFoundError` wrapper to exactify before the atomic RED is added. This is one atomic
synthetic-mechanics predecessor for the complete absent-module boundary of
`src.data_agents.canonical_v2.knowledge_answer`. It does not check Tasks 9.2, 9.4, 9.6, 9.7, or
9.8, run the reviewed claim-level oracle, call real providers, or claim aggregate S9 acceptance.
The OpenSpec ledger remains 54/80.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec tasks: `9.2`, `9.4`, `9.6`, and `9.7` (synthetic mechanics predecessor only; all remain
  unchecked)
- Depends on: Accepted S3A KnowledgeAnswer interface RED, Accepted S6R auxiliary semantics,
  Accepted aggregate S7, re-Accepted S8RG typed `EvidenceSet`, and Accepted S9A/S9G/S9M RED owners
- Atomicity authority: adding any importable `knowledge_answer.py` awakens all 12 existing strict
  absent-module groups; no subset may become Candidate or Accepted independently

## Goal

Introduce one deep answer/session module behind only these public seams:

```python
answer = create_ephemeral_knowledge_answer(
    answer_selector=...,
    assessment_selector=...,
    prose_renderer=...,
)
result = answer.answer(TurnRequest(...))
```

Before GREEN, add exactly one strict atomic trust-boundary group through the same absent target. It
must prove that:

1. `TurnRequest` content-binds the query, release, and complete validated `EvidenceSet`; a query or
   release mismatch fails before answer selection.
2. Same-class selector output, including `model_construct` output, is dumped and revalidated at the
   boundary. The proposal schema and `selection_input_sha256` bind the exact request.
3. Wrong-input-hash, wrong-schema, schema-invalid, or forged unsupported output creates no material
   claim and records a named deterministic limitation rather than trusting model-authored evidence,
   handle, coverage, conflict, status, session, or continuation state.

Then atomically implement the 13-group synthetic contract:

- S3A basic `KnowledgeAnswer.answer` request/result and distinct local/Web evidence mapping;
- S9G exact claim/evidence/citation binding, proportional conflict and inference disclosure, direct
  Product-capability evidence/status, scoped/as-of Industry Brief and coverage honesty, and
  deterministic prose-failure fallback;
- S9A user-prescribed assessment criteria, per-turn selector-proposed dimensions, and grounded
  supported/conflicting/missing assessment results without a global registry or score;
- S9M Canonical/Web anchors, displayed result sets, protected constraints, typed traversal,
  unresolved Web-handle traversal refusal, ambiguity interpretation/selection, six conditional
  continuation reasons with at most three executable options, and topic-switch state replacement;
- the one pre-GREEN trust-boundary group above.

## Non-goals

- Do not check or claim complete Tasks 9.2/9.4/9.6/9.7/9.8 or aggregate S9. Reviewed claim-level
  replay, answer completeness calibration, safety-guidance rendering, real provider/LLM latency,
  TTFT/progress, and full response-contract acceptance remain downstream.
- Do not redo S8 planning, retrieval, fusion, sufficiency, Web snapshot, or Web-handle execution.
- Do not add HTTP/chat/admin consumers, a public or durable SessionManager, persistence/TTL,
  cross-process state, database/index/source writes, or release/cutover behavior.
- Do not call `KnowledgeGapFeedback`; S10 integration may consume accepted answer/query traces later.
- Do not create a canonical Product-capability relation or persist an Industry Brief, assessment
  frame, Web fact, continuation offer, or model-selected dimension.
- Do not add a global assessment dimension/policy registry, canonical score, prompt framework,
  provider adapter hierarchy, or generalized workflow engine.

## Allowed scope

- One production deep module:
  `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_answer.py`.
- One new one-group atomic RED/GREEN owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_atomic_green_contract.py`.
- Existing KnowledgeAnswer owner tests only for:
  - mechanically replacing S3A's broad `ModuleNotFoundError` xfail with the same exact-target
    `_MissingKnowledgeAnswerModule` sentinel used by the other owners before RED proof; and
  - removing all 13 strict xfail wrappers and now-unused sentinel imports/reasons only after the
    complete owner bundle is GREEN.
- This Slice Contract and, after Candidate review, existing verification/change-log/agent-links,
  portfolio, and mainline-plan evidence. `tasks.md` remains unchanged.

## Interface and compatibility constraints

- Export `KnowledgeAnswer`, `create_ephemeral_knowledge_answer`, `TurnRequest`, `TurnResult`,
  `MaterialClaim`, `MaterialClaimProposal`, `AnswerSelectionProposal`, `AssessmentIntent`,
  `AssessmentDimensionProposal`, `AssessmentSelectionProposal`, `AssessmentFrame`, and
  `ContinuationSelection`.
- Re-export or directly expose the Accepted read-side shapes consumed by S9 owners without defining
  incompatible duplicates: Canonical/Web handles, ambiguity records, evidence records/set,
  enumeration coverage, traversal request, continuation candidate, evidence conflict, Industry
  Brief intent, material question parts, and protected slots.
- `TurnResult` remains compatible with the Accepted S3A minimal constructor; later fields have safe
  immutable defaults. `MaterialClaim` supports both the minimal claim and the accepted grounded S9
  subject/predicate/value/status/outcome fields.
- Selectors propose only. Final evidence membership, claim status, citations, conflicts, handle and
  anchor state, traversal eligibility, coverage, assessment grounding, ambiguity outcome, session
  transitions, and continuation availability remain server-owned.
- Same-class Pydantic `model_construct` values are revalidated. Schema-invalid selector output and
  the Accepted prose-timeout case degrade deterministically; other provider runtime failures remain
  downstream Task 9.8, and unexpected programmer defects propagate.
- Session context is private to one ephemeral `KnowledgeAnswer` instance and isolated by
  `session_id + release_id`. Do not add a public session service or durable lifecycle policy.
- Blocking ambiguity suppresses factual answer claims. Unresolved Web handles may corefer within
  their accepted snapshot context but never become Canonical traversal anchors.
- A continuation offer appears only for the accepted trigger reasons, contains no unsupported fact,
  exposes at most three available executable options, and binds an accepted next-turn selection.

## Forbidden changes

- Any other production/shared-contract/migration/database/index/provider/admin/chat/gap/source file
  or existing Accepted assertion/fixture value.
- Partial module/stub introduction, partial xfail removal, assertion weakening, test-local
  implementation, hand-built final return bypass, broad exception masking, `importorskip`, runtime
  `pytest.xfail`, live network/credentials, or reference prose/model memory as truth.
- Model/caller-authored evidence IDs, accepted handles, coverage/exhaustiveness, conflict/status,
  final session state, or unsupported continuation operations surviving server validation.

## Expected unchanged behavior

- S1-S8/S10 and all Accepted S9 RED semantics remain unchanged. S8RG's optional continuation
  coverage shape remains GREEN.
- Before adding the atomic RED, complete no-external Canonical V2 is
  `315 passed, 141 skipped, 12 xfailed`; all xfails are the current KnowledgeAnswer owners.
- After exactifying S3A and adding the atomic RED, normal owner execution is exactly 13 strict
  xfails and forced execution is exactly 13 exact `_MissingKnowledgeAnswerModule` failures. Complete
  no-external Canonical V2 is `315 passed, 141 skipped, 13 xfailed`.
- After atomic GREEN, the new owner is `1 passed`, the complete KnowledgeAnswer owner matrix is
  `13 passed`, and complete no-external Canonical V2 is `328 passed, 141 skipped, 0 xfailed`.
- Original PostgreSQL/Milvus/forensic sources, recovery lab, candidate/index state, active pointers,
  and the formal 54/80 OpenSpec ledger remain unchanged.

## Required checks

- Pre-GREEN focused normal execution is exactly one strict xfail and forced execution is one exact
  absent-target `_MissingKnowledgeAnswerModule` sentinel. The combined owner bundle is exactly 13
  strict xfails/13 exact forced sentinels with no nested import, fixture-construction, or validation
  failure.
- After removing all and only the 13 wrappers, the new group and complete owner matrix are exactly
  `1 passed` and `13 passed`, with no xfail/XPASS/skip.
- Complete no-external Canonical V2 is exactly `328 passed, 141 skipped, 0 xfailed`, absent unrelated
  concurrent work; any count drift must be reconciled rather than normalized away.
- Ruff check/format, `py_compile`, and complete Canonical V2 Pyright pass for changed/applicable
  scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, fresh wheel/package-content,
  and frozen-source checks pass.
- At least one independent implementation/test-integrity review reports zero open Critical/
  Important findings. Minor/YAGNI findings are recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `change-log.md` and `agent-links.md` after Candidate acceptance; Tasks 9.2/9.4/9.6/9.7/
  9.8 and `tasks.md` remain unchanged.
- `.agents/portfolio.md` and the current code-grounded mainline plan after acceptance.

## Stop conditions

- Any one of the 13 owner groups remains xfail/XPASS/failing, or implementation requires a shared
  contract/public API outside `knowledge_answer.py`.
- Correct behavior requires missing S8 answer handoff fields, reviewed S2C labels, calibrated product
  policy, real provider/runtime truth, durable session state, or persistence rather than the
  accepted recorded fixtures.
- An unsupported claim or selector-authored protected/final state survives, a blocking ambiguity
  produces factual claims, an unresolved Web handle traverses as Canonical, or a continuation option
  cannot bind the next turn exactly.
- Work broadens into full Task 9.6 safety/cross-session semantics, S9 acceptance, S10/S11 integration,
  or unresolved Critical/Important findings.

## Done means

- The missing trust-boundary RED is proven, then all 13 KnowledgeAnswer groups turn GREEN through
  one module without assertion weakening or partial sentinels.
- Owner/full no-external/static/strict/package/source checks and independent review pass with zero
  open Critical/Important findings.
- S9AG is Accepted as atomic synthetic mechanics only; Tasks 9.2/9.4/9.6/9.7/9.8 and aggregate S9
  remain open, and the global ledger remains 54/80.

## Plan

1. Exactify S3A's absent-target sentinel, add the single trust-boundary RED, and capture focused and
   combined normal/forced RED evidence.
2. Remove all and only the 13 wrappers; capture exact unmasked missing-module RED.
3. Implement the immutable request/result records, selector validation, grounded claim/assessment
   selection, deterministic rendering, and private ephemeral context in one `knowledge_answer.py`,
   keeping the complete owner bundle visible after every behavior cluster.
4. Run complete no-external/static/strict/package/source checks and independent read-only review.
5. Persist atomic mechanics acceptance without checking OpenSpec tasks or starting provider/
   claim-level acceptance.

## Rollback note

Remove `knowledge_answer.py` and the atomic owner, restore all 13 strict xfail wrappers and S3A's
original absent-module sentinel form, and remove this contract/evidence. No external state exists to
roll back.

## Acceptance evidence

- RED was proven before implementation: the new owner was exactly `1 xfailed` normally and one
  exact `_MissingKnowledgeAnswerModule` forced sentinel; the five-owner bundle was exactly
  `13 xfailed` normally and 13 exact forced sentinels. Removing only those wrappers exposed exactly
  13 target-module failures before GREEN.
- Final owner execution is `13 passed, 0 failed, 0 skipped, 0 xfailed`. The three emitted warnings
  are the atomic owner's intentional hostile `model_construct` payloads and do not relax validation.
- Complete no-external Canonical V2 is exactly `328 passed, 141 skipped, 0 xfailed`; complete
  Canonical V2 Pyright is `0 errors, 0 warnings, 0 informations`.
- Scoped Ruff check/format, `py_compile`, strict OpenSpec, `git diff --check`, high-confidence secret,
  generated-cache, and scope checks pass.
- Fresh offline wheel SHA-256 is
  `e1fc009a49d57307834ab97fb34621cdfe859124dcd98294cb3e67f1c92e4419`; it contains 275 entries,
  includes `knowledge_answer.py`, `knowledge_read.py`, and `knowledge_gap_feedback.py`, and excludes
  tests and `.agents` artifacts.
- Frozen-source checks show original `pgtest` still paused on volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`, recovery lab still
  network-none/no-port, and original Milvus SHA-256 still
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Accepted implementation SHA-256 is
  `4847de614c0f9fb6b080b1dad763d7e6f5300d91d1b2742b3d7426e4aee444b6`; owner SHA-256 values are
  `c881c7cf...90048`, `6d5921ab...356fc`, `01e73f5a...6704`, `e913604e...3eff`, and
  `4b252f85...ac13e` in atomic/interface/assessment/grounding/multi-turn order.
- The one merged independent review initially found three Important cross-path fail-closed defects:
  unsupported output could establish session state, claim-suppressed responses could still synthesize
  Product insufficiency, and a current-turn unresolved Web source could traverse. Three regression
  paths first failed exactly, then passed after session rollback, suppression-aware Product handling,
  and source-first unresolved-Web refusal. The targeted exact-hash re-review returned `ACCEPTED`
  with zero Critical/Important/Minor/YAGNI findings.
- The formal OpenSpec ledger remains `54/80`. Tasks 9.2/9.4/9.6/9.7/9.8 and aggregate S9 remain
  open. S9AG is Accepted only as the atomic synthetic-mechanics predecessor.
