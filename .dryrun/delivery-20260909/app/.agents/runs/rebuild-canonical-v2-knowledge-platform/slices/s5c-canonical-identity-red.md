# Slice Contract: s5c-canonical-identity-red

## Status

Accepted at `2026-07-12T05:21:29Z` under the approved OpenSpec and the user's objective-verification
self-approval authorization. This is a test-only strict RED slice for OpenSpec Task 5.3. It does not
authorize Task 5.4 production code, schema changes, canonical-candidate writes, or S5 aggregate
acceptance.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `5.3`
- Depends on: Accepted Task 5.2 at commit `764aa38`

## Lean execution

- This slice contract and OpenSpec Task 5.3 are the only plan sources.
- Add one observable identity scenario at a time and prove its exact missing-module RED before the
  next scenario.
- Perform one combined specification/code-quality review for Task 5.3 after all five scenarios are
  RED. This test-only slice adds no separate migration/safety review.
- Run complete no-database regression, static checks, OpenSpec validation, and frozen-source safety
  audit only at the Task 5.3 commit checkpoint.

## Goal

Define a deep package-internal identity-resolution interface whose observable outcomes prove that
offline Canonical V2 builds can merge strong identifiers, adjudicate ambiguous cross-format
evidence, keep same-name people separate, split a mistaken merge, and retain recovery lineage. The
result must expose unambiguous source-identity ownership after every action so downstream facts and
relationships cannot attach to the wrong real-world object.

## Non-goals

- Implement normalization, candidate recall, deterministic rules, structured LLM adjudication,
  review queues, identity persistence, or source-identity mapping (Task 5.4).
- Implement temporal validity/history policy (Task 5.5) or aggregate S5 verification (Task 5.6).
- Change shared contracts, C2 migrations, typed domain projections, relationships, publication,
  Milvus, query/answer behavior, or legacy `chat.py`.
- Preserve pre-launch canonical IDs or assert a physical identity-storage design.

## Allowed scope

- One focused test module under `apps/miroflow-agent/tests/canonical_v2/`.
- This slice contract plus Task 5.3 OpenSpec/change-log and verification evidence.
- Deterministic synthetic four-domain source identities/assertions, existing canonical/history
  values, and one content-bound recorded structured-LLM adapter contract.

## Forbidden changes

- Any file under `apps/miroflow-agent/src/` or `canonical_v2_alembic/`.
- Any database, source, Milvus, provider, runtime, admin, retrieval, answer, or benchmark write/call.
- Direct SQL/table/repository assertions, implementation call-count/order assertions, or a local
  fake resolver that fabricates expected results.
- A normal failing suite. Intentional RED must use strict `xfail` limited to the exact missing future
  `canonical_identity_resolution` module and must be separately demonstrated with `--runxfail`.

## Expected unchanged behavior

- Accepted S1-S4 and Tasks 5.1-5.2 remain GREEN and immutable.
- The durable candidate remains C2_0004 with the Accepted landing checkpoint and zero non-landing
  business rows; no Task 5 decision/identity data is written there.
- The four Task 3.1 future deep-module interfaces remain strict RED.

## Required scenarios

1. Matching strong identifiers across source formats deterministically merge two prior canonical
   identities into one active identity, retain both predecessors, and map both source identities to
   the same output independent of input order.
2. Ambiguous cross-format evidence uses a content-bound recorded structured-LLM decision and retains
   every supporting assertion/record, policy/model/schema version, confidence, rationale, and
   uncertainty.
3. Same-name identities with contradictory strong identifiers remain separate without model
   adjudication or silent flattening.
4. A named historical mistaken merge is reversed by one replacement decision that produces a 1-to-N
   split topology: one predecessor, at least two active successors, exact per-source reassignment,
   predecessor/successor lineage, and an explicit reference to the reversed merge. A standalone
   `split` action is reserved for 1-to-N correction without a named prior decision.
5. A recovered historical source links to a current canonical identity while retaining its original
   source system/key, landing record IDs, historical identifier, decision evidence, and mapping;
   the historical ID is lineage, not a required canonical ID.

## Task 5.4 GREEN handoff

- The identity result needs an explicit output-specific source-identity mapping. Existing
  decision-wide membership is insufficient for a split with multiple outputs and must not be
  inferred heuristically.
- Current active canonical identities and their unique source assignments must be separate from
  retained terminal/history identities. Historical merge/split membership cannot be passed to
  downstream current-projection logic as a second active owner.
- Candidate comparison returns `same_entity`, `different_entities`, or `unresolved` independently
  from applied identity actions. `different_entities` must not be represented as
  `IdentityAction.reject`, which denotes hard rejection of an identity.
- Identity decisions, canonical lifecycle states, mappings, structured traces, and supporting
  assertions/records must be mutually consistent, content-bound, deterministic, release-scoped,
  and reproducible.
- Query/answer paths remain read-only; Task 5.3 neither defines nor authorizes online identity
  mutation.

## Required checks

- Each scenario is observed failing for the exact absent target module before all five are retained.
- Focused normal run reports exactly five strict xfails and zero failures/errors/XPASS.
- Focused `--runxfail` reports exactly five failures, all caused by the absent
  `src.data_agents.canonical_v2.canonical_identity_resolution`; nested missing dependencies fail
  normally.
- At the commit checkpoint: Canonical V2 no-database regression, Ruff, Pyright, strict OpenSpec,
  diff/secret checks, and read-only frozen-source/candidate invariants pass.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`

## Stop conditions

- A scenario requires a product or identity-policy decision not traceable to the approved OpenSpec.
- A test can pass through a local fake result without executing the future resolver interface.
- RED fails for anything other than the exact absent target module.
- Correct RED coverage requires production, shared-contract, migration, database, provider, query,
  or Task 5.4+ changes.

## Done means

- Five strict scenarios cover all Task 5.3 effects through one resolver/result interface and expose
  exact source ownership after merge/link/split.
- Normal and forced RED shapes are exact, the one merged review has zero open Critical/Important
  findings, checkpoint checks pass, and verification evidence is current.
- Task 5.3 is Accepted and committed alone; Task 5.4 has not started in the same commit.

## Acceptance checkpoint

- Five strict scenarios cover deterministic Paper strong-ID merge, content-bound cross-format
  Professor LLM adjudication, deterministic same-name Professor separation, named Company merge
  reversal with exact split assignments, and recovered Patent linkage to an existing canonical.
- Candidate comparison verdicts are independent from terminal identity actions. Active current
  identities, terminal history, and exact source-to-canonical assignments are distinct; every
  decision-governed assignment targets that decision's output without duplicate or missing owners.
- Applied decisions bind policy/run/method, exact source records, supporting assertions, output
  identities, release-scoped manifests, retained source/assertion payloads, and mutation-sensitive
  decision/result hashes. Recorded LLM inputs and exact raw output bytes remain content-bound.
- The exact-target sentinel prevents nested or lazy `ModuleNotFoundError` from being masked. Normal
  focused pytest reported exactly `5 xfailed`; forced RED reported exactly five sentinel failures,
  each directly caused by absence of the exact future module.
- The single merged specification/code-quality review is `APPROVED` with zero open
  Critical/Important findings after closing assignment completeness/cross-wiring, overly broad
  xfail, recovery-create-vs-link, evidence binding, and candidate/action coupling defects.
- Commit-checkpoint evidence: Canonical V2 no-DB `93 passed, 48 skipped, 9 expected xfails`; S1/gate
  `17 passed`; S2/S2B `32 passed`; S4 checkpoint `23 passed`; formal backup gate `accepted/50`;
  Ruff, Pyright, strict OpenSpec, diff, and secret checks passed.
- Original `pgtest` remains paused on the exact source volume; original Milvus hash and S4 hashes
  match. The forced-read-only candidate remains C2_0004 with landing `15/6/21/6/6` and all 20
  knowledge/publish tables empty. Its known persistent read-only default remains `off`; no database,
  source, index, provider, runtime, or legacy `chat.py` mutation occurred.
