# Slice Contract: s9m-multiturn-red

## Status

Accepted at `2026-07-15T04:19:34Z`. This synthetic fixture-only RED slice completes OpenSpec Task
9.5. Exact RED, complete no-external regression, static/strict/package/source checks, and two
independent targeted reviews pass with zero Critical/Important findings. It does not consume the
pending S2C corpus, execute a claim-level acceptance oracle, call a real provider, or implement
session/continuation production behavior.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `9.5`
- Depends on: Accepted S3A `KnowledgeAnswer.answer(TurnRequest) -> TurnResult` interface contract,
  Accepted S7 release/index substrate, and typed synthetic evidence/result metadata consistent with
  the Accepted S8W/S8S RED contracts
- Parallel-start authority: `agent-links.md` permits S9 answer/session RED contracts against typed
  synthetic evidence; S2C3C2/S2C3C3 still gate only claim-level acceptance-oracle execution

## Goal

Freeze four strict RED groups through one stateful ephemeral `KnowledgeAnswer` instance per scenario:

1. canonical anchors and ordered displayed result sets remain distinct; a bare list creates no
   singular anchor, a requested typed traversal consumes every and only displayed member in order,
   excludes a retrieved-but-undisplayed trap, retains protected constraints, and preserves minimal
   enumeration mode/scope/as-of/displayed/continuation state;
2. a displayed unresolved `WebEntityHandle` retains its tagged type, bounded snapshot identity,
   resolution state, and display order; it may support coreference/evidence narrowing but neither
   its handle nor URL may become a Canonical ID or execute canonical traversal, which instead returns
   a typed limitation/read-only-resolution path;
3. synthetic non-blocking and blocking ambiguity decisions are rendered without recalibrating their
   gate: non-blocking output identifies the selected interpretation and exposes alternatives only as
   bounded switch options; blocking output is clarification-only with no primary claims; selecting an
   option binds the next turn to its exact Canonical or Web handle and retains the ambiguity trace;
4. each accepted continuation trigger and one no-trigger case produce the conditional structured
   presence/absence contract, at most three executable options bound to exact handles/result sets,
   constraints, coverage, and operations; selecting an option continues that context, while an
   explicit topic switch replaces active anchor/result-set/constraints/path for the new active turn.

## Non-goals

- Do not implement Tasks 9.1-9.4/9.6-9.8, `knowledge_answer.py`, session storage, TTL, prompts,
  ambiguity calculation, prose quality, HTTP/chat adapters, or `ContinuationOffer` production logic.
- Do not repeat Task 8.6's full enumeration ledger, implement S8 planning/fusion/read/runtime, or test
  Web snapshot tamper/provider-change/expiry/URL-collision lifecycle owned by Tasks 8.5/8.8.
- Do not calibrate ambiguity thresholds, classify fuzzy topic switches, run real provider/latency/
  unsupported-claim-rate gates, or claim aggregate S9/S8 acceptance.
- Do not introduce a second public Session/Context interface or turn a Web handle, URL, derived path,
  or session relation into canonical knowledge.

## Allowed scope

- One new test owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py`.
- This Slice Contract and, after Candidate review, existing OpenSpec task/change-log/agent-link,
  portfolio, mainline-plan, and verification evidence files.
- Synthetic future-shaped evidence sets, Canonical/Web handles, bounded Web snapshots, displayed-set
  selections, protected slots, typed paths, minimal enumeration coverage, ambiguity decisions,
  continuation triggers/options/selections, transition receipts, claims, and limitations only. The
  test imports the exact absent KnowledgeAnswer target before any future dependency or fixture shape.

## Forbidden changes

- Any production/shared-contract/migration/provider/runtime/source/database/index/consumer file.
- A public `SessionManager` or other second behavior seam; all observable state transitions must
  emerge from consecutive calls to one ephemeral `KnowledgeAnswer.answer` instance.
- A test-local `KnowledgeAnswer` implementation, hand-built returned `TurnResult`, broad
  `ModuleNotFoundError`, `importorskip`, runtime `pytest.xfail`, private store/call-order assertion,
  re-supplying prior resolved IDs as the next request's answer, real credential/network access, or
  prose-only success criterion.
- Any Task 9.6/9.7 GREEN, Task 9.8 acceptance, S2C, real provider, storage, TTL, ambiguity-threshold,
  fuzzy-topic-switch, or aggregate S9 claim.

## Expected unchanged behavior

- S8W/S8S/S9A/S10A/S10B and all S1-S7 Accepted behavior remain unchanged.
- S2C3C2 remains Ready and externally pending; Task 8.1 reviewed calibration and S8/S9 claim-level
  acceptance-oracle execution remain blocked, but this synthetic Task 9.5 RED does not.
- Existing KnowledgeRead, KnowledgeAnswer/S9A, S8W, and S8S xfails remain expected.
- Original Postgres/Milvus/forensic sources, candidate/index state, and active pointers remain
  unchanged.

## Required checks

- Focused normal execution reports exactly four strict xfails and zero failures/errors/XPASS.
- Focused `--runxfail` reports exactly four failures caused only by the exact absent
  `src.data_agents.canonical_v2.knowledge_answer` target sentinel.
- Complete no-external Canonical V2 reports no real failure and only the existing KnowledgeRead,
  KnowledgeAnswer/S9A, S8W, S8S, and these four S9M scenarios as named xfails.
- Ruff check/format and Canonical V2 Pyright pass for changed/applicable scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, package-content, and frozen-
  source checks pass.
- At least one independent review reports zero open Critical/Important findings. Minor/YAGNI findings
  are recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `change-log.md`, and `agent-links.md` only after complete Task 9.5 RED
  acceptance.
- `.agents/portfolio.md` and current code-grounded mainline plan after acceptance.

## Stop conditions

- A case requires behavior absent from the active grounded-answer/session/ADR contracts or depends on
  an unaccepted S8 runtime result rather than a synthetic typed fixture.
- A result can use a retrieved-but-undisplayed member, create a singular anchor from a bare list,
  drop a protected constraint, or traverse an unresolved Web handle/URL as canonical.
- Blocking ambiguity can emit primary claims, a selection does not bind its exact option handle, an
  unsupported/unbound continuation can pass, or explicit topic switch leaves old active context.
- RED can pass through a local implementation/broad exception mask, exposes private storage/order,
  introduces another public seam, or needs production/shared-contract edits or an unresolved
  Critical/Important finding.

## Done means

- Four strict groups close canonical anchor/displayed-set/traversal/coverage, Web-handle, ambiguity/
  clarification selection, conditional continuation, and explicit topic-switch behavior through the
  single future answer interface, including the named negative traps.
- Exact RED, complete no-external/static/strict/scope/package/source checks, and independent review
  pass with zero open Critical/Important findings.
- Task 9.5/S9M is Accepted as RED only; Tasks 9.1-9.2 and 9.4/9.6-9.8 remain open.

## Plan

1. Add four exact-target strict RED groups without production/shared-contract edits.
2. Prove normal and forced RED identity, then run complete no-external/static/strict/package/source
   checks.
3. Obtain independent read-only review and repair only Critical/Important findings.
4. Persist Task 9.5 RED acceptance. Do not implement Tasks 9.6/9.7 without separate Ready Slice
   Contracts and Accepted production predecessors.

## Rollback note

Remove the new RED test, this contract, and its status/evidence entries. No external state exists to
roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256 is
  `d3f3e1fe446ea516d6e8046fd2ca951974fda6b3a954c91d5ad960f778e9bcfd`; final test SHA-256 is
  `441b6e54b8e907fc2c480e2885ef4c3534c065d452880961a7f9fde147da1f8f`.
- Focused normal execution is exactly `4 xfailed`; forced `--runxfail` is exactly four
  `_MissingKnowledgeAnswerModule` failures for the absent
  `src.data_agents.canonical_v2.knowledge_answer` target. Nested dependency failures remain real.
- Canonical multi-turn state keeps the explicit Professor anchor separate from an ordered displayed
  Paper result set, binds follow-up to the exact prior result-set identity plus `representative`/
  `open_world` coverage, retains protected constraints, and executes only registered
  `professor_attributed_to_paper` forward/inverse paths. A hidden source/target is first in current
  evidence/proposal order and still cannot enter the traversal or answer.
- Mixed Canonical/Web display order, bounded snapshot identity, and unresolved resolution state are
  retained. An ordinal follow-up overrides a hostile selector using session state; canonical Patent
  traversal over the Web handle/URL is blocked with a typed read-only-resolution limitation and no
  primary claim or fabricated Canonical ID.
- Non-blocking ambiguity exposes one interpretation plus a bounded alternative; blocking ambiguity
  suppresses hostile primary claims/text and returns clarification only. Opaque selection turns with
  hostile proposals bind the recorded Canonical or Web option exactly and preserve ambiguity trace/
  Web snapshot lineage without resupplying target IDs.
- All six accepted continuation reasons plus an ordinary complete-simple no-trigger case are
  data-driven. Unavailable candidates are selected by the hostile proposal but removed before the
  three-option cap; options retain exact source candidate, handle/result-set, constraint, evidence,
  operation, and eligible relationship binding. Opaque selection restores the recorded option;
  explicit topic switch replaces old active anchor/result-set/constraints/path and omits an offer.
- Complete no-external Canonical V2 is `296 passed, 141 skipped, 15 xfailed`; the xfails are exactly
  the existing KnowledgeRead, KnowledgeAnswer/S9A, S8W, S8S, and four S9M groups. Complete Canonical
  V2 Ruff/Pyright and changed-test format checks pass.
- Strict OpenSpec, `git diff --check`, scope/secret/cache, and fresh wheel checks pass. The first
  isolated wheel attempt could not fetch `hatchling` because the configured mirror ended its TLS
  handshake; the locked offline build then succeeded with unchanged wheel SHA-256
  `af7332f68739a5d87c87639089765580a0e446f3788d2d8aeeb87ade1c884d00`. The wheel excludes tests/
  `.agents`, includes Accepted `knowledge_gap_feedback.py`, and contains no S9M production module.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; recovery lab remains
  network-none/no-port; original Milvus SHA-256 remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Two independent pre-review/re-review tracks and Candidate identity review end zero Critical/
  Important after closing coverage-state, protected-constraint, Web ambiguity, availability/binding,
  no-trigger, hostile-answer, registered-path, stored-selection, hidden-cap, and exact-result-set
  false-green gaps. Nonblocking Minor/YAGNI: two local variable names retain an earlier Company label
  while carrying Professor IDs; cross-release misuse remains Task 9.6-owned; the first traversal is
  represented in the accumulated public path receipt rather than a second dedicated assertion.
- Task 9.5/S9M is Accepted at 53/80. Tasks 9.1-9.2 and 9.4/9.6-9.8 remain open; S2C3C2/S2C3C3 still
  gate only S8/S9 claim-level acceptance-oracle execution. No provider, database, index, source,
  release pointer, production code, Commit, Push, PR, archive, or Cutover changed.
