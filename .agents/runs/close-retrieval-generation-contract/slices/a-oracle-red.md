# Slice Contract: A — oracle-red

## Status

In Progress — stopped at the Task 1.5 substrate gate; explicit sequencing/substrate decision required

## Parent

- OpenSpec change: `openspec/changes/close-retrieval-generation-contract/`
- Verification contract: `.agents/runs/close-retrieval-generation-contract/verification-contract.md`

## Goal

Replace the mutable/text-presence paper oracle with a fixed, ID-grounded, three-stage evaluator and
capture reproducible true-RED evidence for the current checkpoint before any production behavior
change.

## Non-goals

- Fixing routing, retrieval, evidence assembly, synthesis, citation rendering, or index coverage.
- Changing public API/frontend behavior, database schema/data, Milvus contents, prompts, provider
  selection, ranking, thresholds, or production configuration.
- Claiming the paper system is GREEN because the evaluator itself works.

## Allowed scope

- Evaluation scripts, case fixtures/manifests, scorer-only models/helpers, evaluator tests, and
  immutable run artifacts for this Epic.
- This slice contract, `verification.md`, OpenSpec tasks/acceptance/change log, and portfolio status.
- Read-only snapshot and index inspection needed to bind IDs and environment fingerprints.
- Read-only two-level paper/chunk parity preflight; no reconciliation or mutation.

## Forbidden changes

- Production paths under chat/retrieval/synthesis/frontend modules.
- Migrations, canonical-data writes, embedding calls that persist state, or Milvus mutations.
- Replacing canonical IDs with substring tokens, query echo, judge-only retrieval scoring, or Web
  results.
- Editing expected IDs/intents, topic/rubric/blind-label protocol, thresholds, sample strata, or
  latency protocol after candidate output is inspected without versioning and rerunning the parent.
- Starting Slice B implementation before this slice is Accepted.

## Expected unchanged behavior

- All user-visible `/api/chat`, retrieval, synthesis, citation, and UI behavior remains byte/semantic
  equivalent except evaluator-only debug/output artifacts outside public contracts.
- Existing production config and provider calls remain unchanged.
- Existing stored data and active index remain unchanged.

## Required checks

- Strict OpenSpec validation and `git diff --check`.
- Focused scorer/manifest tests proving only allowlisted canonical result/evidence/claim fields score.
- Failure-injection tests proving every hard gate exits nonzero.
- Type4 blind-union-label/micro-P@5 tests proving missing/duplicate/Web slots cannot inflate score and
  no recall claim appears without a candidate universe.
- 100-case classifier tests for type/domain/normalized name-or-topic/endpoint, including
  type-correct/entity-wrong failure injection.
- Same-snapshot parent and `c0f3db2` paired replay with identical saved provider fixtures, plus a
  separately labeled >=3-run live P0 stability report, manifest/environment hashes, and raw responses.
- Immutable-clone or before/after DB/physical-Milvus cryptographic manifest checks and read-only
  paper/chunk substrate viability report.
- Corrected per-path retrieval, citation, semantic, and regression report.
- Diff audit proving no production behavior file changed.

Exact runnable commands, test counts, environment, and artifact hashes must be recorded in
`verification.md`; code inspection is not evidence that a command passed.

## Evidence to update

- `.agents/runs/close-retrieval-generation-contract/verification.md` — Slice A commands, results,
  corrected RED table, hashes, review, optional authorized commit, and status.
- `openspec/changes/close-retrieval-generation-contract/acceptance.md` — Slice A criteria/evidence.
- `openspec/changes/close-retrieval-generation-contract/tasks.md` — only completed Slice A tasks.
- `openspec/changes/close-retrieval-generation-contract/change-log.md`.
- `.agents/portfolio.md` — Candidate/Accepted state and next Ready slice.

## Stop conditions

- Expected IDs or semantics cannot be grounded from the frozen snapshot.
- Parent and candidate cannot run on the same database/index/identical saved-provider-fixture
  identity, or the live stability protocol cannot meet its repetition floor.
- Read-only parity shows current index gaps that make the fixed Type4 evaluation substrate non-viable
  and no explicit sequencing/substrate decision exists.
- The evaluator requires a production behavior change to expose canonical IDs not covered by Slice
  A; record that as RED/interface evidence and re-plan rather than changing production.
- Existing unrelated failures make the claimed gate ambiguous.
- The diff enters any production, migration, data, index, or rollout scope.

## Done means

- The fixed manifest and snapshot fingerprints are immutable-hashed and independently reviewable.
- The evaluator's own tests pass and known production cases remain reproducible true RED.
- The old response-wide/token oracle cannot pass via query echo or mutable Type4 tokens.
- No production behavior changed.
- Verification evidence and review are complete, immutable hashes (and any explicitly authorized
  commit) are linked, and the slice is marked Accepted before Slice B is changed to Ready.

## Rollback

Revert the Slice A artifact diff (or explicitly authorized isolated commit). No production/data/
index rollback is required because the slice is gate-only. A real A invalidation applies the Epic
matrix and returns every downstream checkpoint/archive eligibility to Candidate.
