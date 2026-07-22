# Slice Contract: s8rg-atomic-knowledge-read-green

## Status

Accepted at `2026-07-16T02:12:44Z` after a narrow successor-shape compatibility correction discovered
by the S9 readiness audit: non-`partial_coverage` continuation candidates legitimately carry no
coverage state. The original acceptance at `2026-07-15T16:17:31Z` remains historical evidence. This
atomic synthetic GREEN predecessor closes the complete
future-module sentinel boundary for `src.data_agents.canonical_v2.knowledge_read`. Its two fixture
groups plus all 14 Accepted KnowledgeRead owner groups are GREEN through one deep module. It does
not check Tasks 8.1-8.3/8.5/8.7-8.8, consume reviewed S2C cases, call real providers, or claim
aggregate S8/runtime acceptance. The global ledger remains 54/80.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec tasks: `8.2`, `8.3`, `8.5`, and `8.7` (synthetic mechanics predecessor only; all remain
  unchecked)
- Depends on: Accepted S6R auxiliary semantics, Accepted S7 release/index substrate, Accepted S8Q1
  planner RED, Accepted S8W Universal-Web RED, Accepted S8S sufficiency RED, and Accepted S8RF
  retrieval/fusion/Web-handle RED
- Atomicity authority: adding any partial `knowledge_read.py` awakens every strict absent-module
  sentinel; no subset may become Candidate or Accepted independently

## Goal

Introduce one deep module with only these behavior seams:

```python
planner = create_ephemeral_query_planner(...)
plan = planner.plan(QueryPlanningRequest(...))

read = create_ephemeral_knowledge_read(...)
evidence = read.execute(plan)
```

Before GREEN, add exactly two strict RED groups through the same absent target:

1. `RetrievalPlan.ambiguity_decision` is handed to `EvidenceSet` content-bound and unchanged.
   Blocking ambiguity executes no lane and returns no primary evidence; non-blocking ambiguity keeps
   the selected Canonical identity, viable alternatives, policy/candidate trace, and exact decision
   identity through fusion/rerank so model confidence or candidate order cannot rewrite it.
2. An injected synthetic `WebSnapshotPolicy(max_bytes=...)` validates real recorded initial-snapshot
   bytes. The module recomputes content hash and byte length, accepts only content-bound in-budget Web
   evidence, and records missing-payload/oversize/hash-mismatch refusal without creating a handle,
   replacing a snapshot, or freezing a product-wide numeric limit. Claimed metadata cannot substitute
   for or override the observed payload bytes.

Then atomically implement the 16-group synthetic contract:

- S3A basic `KnowledgeRead.execute` typed plan/evidence interface;
- S8Q1 typed query planning, deterministic protected slots/institutions/enumeration/safety,
  synthetic ambiguity mechanics, and internal Person/Technology plans;
- S8W server-owned Universal Web and failure degradation;
- S8S structured sufficiency, enumeration accounting, and bounded targeted supplemental retrieval;
- S8RF seven-lane execution/full candidate trace, identity/evidence-late fusion, hard constraints,
  structured rerank degradation, and Web-handle lifecycle/read-only resolution;
- the two pre-GREEN handoff/bounded-snapshot groups above.
- construction/round-trip compatibility for the already-Accepted KnowledgeAnswer successor inputs:
  Canonical handles and the S9 minimal Web-handle shape (without execution-only session/expiry),
  S9-shaped ambiguity candidates/decision, enumeration coverage, typed
  traversal, continuation candidates, evidence conflicts, Industry Brief intent, and the expanded
  `EvidenceSet`; the 12 answer xfails must not hide a partial read-result contract.

## Non-goals

- Do not check or claim complete Tasks 8.1-8.3/8.5/8.7/8.8 or aggregate S8. Reviewed ambiguity
  calibration, claim-level case replay, real lane thresholds, provider quality, latency, cost, and
  acceptance remain downstream.
- Do not implement S9 answers/sessions, cross-session handle enforcement, ContinuationOffer,
  consumer/API/admin wiring, persistence, durable cache, database/index/source writes, or release
  publication/cutover.
- Do not add a second public planner/read/fusion/rerank/sufficiency/Web-handle service, public Person/
  Technology domain, canonical Product-capability relation, universal rank/fusion matrix, or
  provider-specific production threshold.
- Do not broaden bounded-snapshot RED into MIME policy, content cleaning, storage, cache eviction,
  production TTL/size selection, or every provider/schema exception permutation.

## Allowed scope

- One production deep module:
  `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`.
- One new two-group RED/GREEN owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_atomic_green_contract.py`.
- Existing KnowledgeRead owner tests only for mechanical removal of the 14 strict xfail wrappers and
  now-unused imports/reasons after exact RED proof:
  - `test_knowledge_read_interface.py`
  - `test_knowledge_query_planning_contract.py`
  - `test_knowledge_read_universal_web_contract.py`
  - `test_knowledge_read_sufficiency_retry_contract.py`
  - `test_knowledge_read_retrieval_fusion_contract.py`
- This Slice Contract and, after Candidate review, existing change-log/agent-link, portfolio,
  mainline-plan, and verification evidence. `tasks.md` remains unchanged.

## Interface and compatibility constraints

- `RetrievalPlan`, `EnumerationPolicy`, `EvidenceItem`, `EvidenceSet`, and related records accept the
  already-frozen minimal and expanded fixture shapes through optional/default fields and normalized
  immutable values; one owner generation must not break another.
- `AmbiguityCandidate` and `AmbiguityDecision` support both the S8 planning/handoff field family and
  the already-Accepted S9 display/selection field family without conflating their validation.
  `CanonicalEntityHandle`, `WebEntityHandle`, `EnumerationCoverage`, `TypedTraversalRequest`,
  `ContinuationCandidate`, `EvidenceConflict`, and `IndustryBriefIntent` are exported and round-trip
  through the expanded `EvidenceSet` before `KnowledgeAnswer` exists.
- Current-Web `EvidenceItem` construction remains compatible with S3/S9 fixtures that omit snapshots.
  `KnowledgeRead.execute`—not a global model validator—rejects accepted Web adapter output lacking the
  required snapshot/payload under the applicable execution policy.
- `create_ephemeral_knowledge_read` accepts both the Accepted `local_search`/`web_search` composition
  and S8RF `lane_adapters`, plus optional identity, rerank, sufficiency, supplemental, handle,
  accepted-identity, clock, and snapshot-policy ports. All normalize into hidden execution stages.
- Independent recorded lanes overlap through bounded internal concurrency; no worker count, executor
  type, private call order, or wall-clock performance threshold is public.
- Recorded planner/fusion/rerank/sufficiency/resolution output is schema/content-binding revalidated.
  Deterministic protected facts, accepted IDs, hard constraints, budgets, lifecycle, and mutation
  refusal remain server-owned.
- Same-class Pydantic `model_construct` values are dumped and revalidated at trust boundaries. Only
  named timeout/connection/schema failures degrade; unexpected programmer defects propagate.

## Forbidden changes

- Any other production/shared-contract/migration/database/index/provider/admin/chat/answer/source
  file or existing Accepted assertion/fixture value.
- Partial module/stub introduction, partial xfail removal, test-local implementation, hand-built
  final return bypass, broad exception masking, `importorskip`, runtime `pytest.xfail`, live network/
  credential access, or reference prose/model memory as truth.
- Query-time canonical/source-map/index writes, URL-derived entity IDs, caller/model-authored
  protected facts/final lifecycle, unsupported public domains/relations, or relaxed content identity.

## Expected unchanged behavior

- S1-S7/S9/S10 and all Accepted S8 RED contracts remain semantically unchanged; only their strict
  KnowledgeRead xfail wrappers are removed after the complete owner bundle is GREEN.
- Before module implementation, the two additions move complete no-external Canonical V2 from
  `299 passed, 141 skipped, 26 xfailed` to `299 passed, 141 skipped, 28 xfailed`.
- After atomic GREEN, the exact 16-group KnowledgeRead owner matrix is `16 passed`, and complete no-
  external Canonical V2 is `315 passed, 141 skipped, 12 xfailed`; the 12 remaining xfails are only
  the untouched KnowledgeAnswer interface/S9A/S9G/S9M owners.
- Original PostgreSQL/Milvus/forensic sources, recovery lab, candidate/index state, and active
  pointers remain unchanged.

## Required checks

- New focused pre-GREEN normal execution is exactly two strict xfails; forced execution is exactly
  two absent-target `_MissingKnowledgeReadModule` sentinel failures. The ambiguity group also
  constructs and round-trips every already-Accepted S9 successor read-result shape, including the
  minimal Web handle. The bounded-snapshot group proves missing payload rejection and recomputation
  from bytes by understating the claimed byte length of an actually oversize payload.
- Pre-GREEN combined owner normal execution is exactly 16 xfails; forced execution is 16 exact
  absent-target failures with no nested failure.
- After removing all and only the 16 wrappers, the two new groups and complete owner matrix are
  exactly `2 passed` and `16 passed`, with no xfail/XPASS.
- Complete no-external Canonical V2 is exactly `315 passed, 141 skipped, 12 xfailed` with no real
  failure.
- Ruff check/format, `py_compile`, and complete Canonical V2 Pyright pass for changed/applicable
  scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, package-content, and frozen-
  source checks pass.
- At least one independent implementation/test-integrity review reports zero open Critical/
  Important findings. Minor/YAGNI findings are recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `change-log.md` and `agent-links.md` after Candidate acceptance; Tasks 8.1-8.3/8.5/
  8.7-8.8 and `tasks.md` stay unchanged.
- `.agents/portfolio.md` and the current code-grounded mainline plan after acceptance.

## Stop conditions

- Any one of the 16 owner groups remains xfail/XPASS/failing, or correct implementation requires a
  shared-contract/public-API change outside `knowledge_read.py`.
- An Accepted assertion must be weakened; a model/provider output can author protected/accepted/
  final state; a hard-rejected/unresolved/expired/tampered candidate becomes selected; or a partial
  module is needed.
- Correct mechanics require reviewed S2C labels, calibrated numeric product policy, real provider/
  database/index truth, persistence, or active release mutation rather than recorded fixtures.
- Work broadens into S9/S11, real-provider acceptance, production thresholds, or unresolved Critical/
  Important findings.

## Done means

- The two missing boundary REDs are proven, then all 16 KnowledgeRead owner groups turn GREEN through
  one module without assertion weakening or partial sentinels.
- Owner/full no-external/static/strict/package/source checks and independent review pass with zero
  open Critical/Important findings.
- S8RG is Accepted as atomic synthetic mechanics only; Tasks 8.1-8.3/8.5/8.7-8.8 and aggregate S8
  remain open, and the global ledger remains 54/80.

## Plan

1. Add the two strict exact-target RED groups and capture focused/combined normal and forced RED.
2. Remove all and only the 16 wrappers; capture exact unmasked missing-module RED.
3. Implement compatible immutable records, planner, execution stages, validation, and conservative
   degradation in one `knowledge_read.py`, running the narrowest owner test after each behavior
   cluster while keeping the whole owner bundle visible.
4. Run complete no-external/static/strict/package/source checks and independent read-only review.
5. Persist atomic mechanics acceptance without checking OpenSpec tasks or starting real-provider/
   claim-level acceptance.

## Rollback note

Revert `knowledge_read.py`, restore all 16 strict xfail wrappers/imports, and remove the new test plus
this contract/evidence. No external state exists to roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256 is
  `b9bc293b8c254f48f17ab548adfc0e2abdaee3e7b9e797b57686f7be25692479`; final production/atomic-
  test SHA-256 values are `0e9029942ea0d20ebe049e4000df283b871dcea2d1d3b711a7b90e2f391213b7`
  and `53787a215536ff9032ac16182e6d9055b9597b007ad4cc5ca589f38a87e810b0`.
- Before GREEN, the two new groups were exactly two strict xfails/two forced exact-target sentinels;
  the combined owner bundle was 16 strict xfails/16 forced exact-target sentinels. Final focused and
  exact owner executions are `2 passed` and `16 passed`, with no xfail, XPASS, skip, or assertion
  weakening. Existing owner edits are mechanical wrapper/import removal only; hostile regressions
  stay in the two-group atomic owner.
- One public `KnowledgeRead.execute` seam now content-binds planning, seven-lane retrieval, server-
  owned Universal Web, initial snapshot admission, identity/evidence-late fusion, protected hard
  constraints, structured rerank degradation, sufficiency/enumeration, bounded supplemental search,
  and Web-handle replay/read-only resolution. Candidate primary identity remains distinct from
  relationship evidence; accepted multi-member fusion may retain evidence-subject aliases without
  allowing unresolved or cross-wired identities to satisfy canonical filters.
- Machine regressions close direct/candidate parity for displayed sets, geography, exact identifiers,
  negation, maximum result count, supplemental constraint reuse, official-only raw trace retention,
  empty/missing-context handle replay, source/snapshot/content identity, ambiguity handoff, provider
  failure, duplicate IDs, and successor-shape validation. Supplemental negative/non-finite budgets,
  negative elapsed time, and non-supplemental lane output fail closed; universal and official-only
  max-result drops retain complete raw-candidate trace as `result_limit_rejected` without entering
  fusion or selection. Legal Company-to-Patent relationship and enumeration evidence remains
  available; `plan.domains` is not misused as an output-domain whitelist.
- Complete no-external Canonical V2 is exactly `315 passed, 141 skipped, 12 xfailed`; all 12 expected
  xfails are the untouched KnowledgeAnswer/S9 RED owners. Complete Canonical V2 Pyright reports zero
  findings; complete Ruff check, changed-file Ruff format, `py_compile`, strict OpenSpec,
  `git diff --check`, scope/secret/cache, and package gates pass. A broader format inventory reports
  only the untouched pre-existing `test_knowledge_answer_interface.py`, outside this slice, as
  reformatable; it was not modified.
- Fresh wheel SHA-256 is
  `b5ed895f43f1a43476198b32af6af8887adcdc29454bc337bdbc016045d4994f`; its 274 entries include
  `knowledge_read.py` and the prior Accepted `knowledge_gap_feedback.py`, and exclude tests and
  `.agents` artifacts.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241` with restart disabled;
  recovery remains network-none/no-port/restart-no; original Milvus SHA-256 remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Comprehensive review plus exact-SHA delta re-review leave zero open Critical/Important findings;
  the final delta review reports zero Critical/Important/Minor/YAGNI. Nonblocking earlier Minor:
  negation uses conservative substring exclusion and may lose recall for prose that explicitly
  denies the forbidden term, but it cannot create a false selected result. Real-provider
  cancellation/latency calibration, cross-session equality, multi-snapshot live reconciliation,
  and broader provider/schema failures remain explicit downstream/YAGNI rather than S8RG blockers.
- Tasks 8.1-8.3/8.5/8.7-8.8 and aggregate S8 remain unchecked/open; the OpenSpec ledger remains
  54/80. No persistence, provider, database/index/source, active pointer, Commit, Push, PR, archive,
  or Cutover changed.

## Successor-shape compatibility correction — 2026-07-16T02:12:44Z

- Reproduced the Accepted S9M successor mismatch before production repair: an explicit `None`
  `coverage_state` on a non-`partial_coverage` `ContinuationCandidate` failed Pydantic validation.
  `coverage_state` is now optional with a `None` default; existing explicit coverage values remain
  unchanged.
- The atomic successor-shape owner now carries both the prior `"open_world"` candidate and the
  no-coverage candidate through a complete JSON `EvidenceSet` round trip, explicitly proving that
  `None` survives. No S9 implementation, task checkbox, provider, persistence, or public service was
  added.
- Focused atomic and complete KnowledgeRead owner results are `2 passed` and `16 passed`. Complete
  no-external Canonical V2 remains `315 passed, 141 skipped, 12 xfailed`; all xfails remain only the
  untouched KnowledgeAnswer/S9 owners. Ruff check/format, `py_compile`, targeted Pyright, strict
  OpenSpec, `git diff --check`, wheel content, secret/cache, and frozen-source checks pass.
- Corrected production/test SHA-256 values are
  `37420ec2075d4ed3527ad73c7960c5158f54057e5287d4cdc8cc0eb430a3bad0` and
  `d8e753331a55938ff7f894ddb397fea6cedaa9a0d6f6d05d1649fd7fd1979699`. The fresh 274-entry wheel is
  `53e56339ecaf107f6fc1c915f2261f27b8373078bbeb30fef30f9e0225446bba`; it contains the corrected
  module and excludes tests/`.agents`.
- Independent review first identified the missing complete-result round-trip assertion; the targeted
  repair and re-review leave zero open Critical/Important/Minor/YAGNI. Original `pgtest` remains
  paused on exact volume `d81c6381...d241`, recovery remains network-none/no-port/restart-no, and
  original Milvus remains `43ef203e...67cc`. S8RG is re-Accepted without changing the 54/80 ledger.
