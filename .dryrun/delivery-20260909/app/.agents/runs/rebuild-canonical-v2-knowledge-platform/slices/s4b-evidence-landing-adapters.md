# Slice Contract: s4b-evidence-landing-adapters

## Status

Accepted at `2026-07-11T19:06:55Z`. This slice implements OpenSpec task 4.2 against Accepted task
4.1 RED. It does not authorize Task 4.3 persistence, real source replay, canonical construction, or
index/publication writes.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `4.2`
- Depends on: Accepted task 4.1 at commit `b3428dc`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4-landing-implementation-plan.md`

## Goal

Provide one concrete storage-independent EvidenceLanding core and safe deterministic adapters that
turn immutable source bytes/envelopes into replayable shared SourceRecords without losing readable
partial evidence, inventing facts, or touching active canonical state.

## Non-goals

- Persist landing rows in PostgreSQL or add/modify migrations.
- Replay actual forensic/historical files or connect to recovery databases/Milvus.
- Acquire Web/provider responses, recollect data, or inspect original source bytes beyond existing
  hash-only safety checks.
- Build assertions, identities, domain objects, relationships, eligibility, releases, or indexes.
- Accept S4; tasks 4.3–4.5 remain separate.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/evidence_landing.py`.
- `apps/miroflow-agent/src/data_agents/canonical_v2/evidence_adapters.py`.
- Focused Canonical V2 interface/replay/adapter tests.
- This slice/plan, OpenSpec task/change log, and verification contract/evidence.
- Synthetic bytes and temporary test-only SQLite/XLSX materialization.

## Forbidden changes

- Alembic, C2 schema, database/container/source/Milvus/provider/dependency/runtime consumer changes.
- Original/recovery paths or real network/provider calls from adapters/tests.
- Direct canonical/publication/index mutation or a non-null active release in landing results.
- Hard-coded placeholder substitution for unreadable/missing values.
- Storage/table/collection names or internal call ordering exposed as public interface behavior.

## Expected unchanged behavior

- Accepted S1–S3/S2B safety and C2_0003 candidate state remain unchanged.
- KnowledgeBuild, KnowledgeRead, KnowledgeAnswer, and ReleasePublication remain strict RED.
- Legacy chat/data agents and all current public payloads remain untouched.

## Required checks

- Observed RED for every new adapter family before implementation.
- Task 3.1 EvidenceLanding, all four Task 4.1 replay scenarios, and Task 4.2 adapter cases GREEN
  through real core behavior; no local fake-success subclass for behavior scenarios.
- Contract validation covers invalid hash/parent/parser/source-kind/options and typed degradation.
- Focused/expanded Canonical V2, S1, S2/S2B, Ruff, Pyright, strict OpenSpec, and diff checks pass.
- Formal gate/original hash/pause/recovery isolation and read-only candidate C2_0003/zero-row state
  match after tests.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`

## Stop conditions

- An adapter requires opening an original or unverified recovery/Milvus/database source.
- Actual source format is required but not specified by accepted evidence; use a verified record
  envelope and leave bounded real replay to task 4.4 rather than guessing.
- Durable storage/schema work is needed for GREEN; stop at the Task 4.3 boundary.
- A new dependency, public contract change outside OpenSpec, or later-slice behavior becomes needed.

## Done means

- All named source families have deterministic safe adapter behavior and typed failure paths.
- Task 4.1 effects are GREEN through the concrete core; only the other four deep modules remain RED.
- No durable/external state changes; task 4.2 is Accepted and committed alone; task 4.3 has not
  started in the same commit.

## Acceptance checkpoint

- The concrete ephemeral composition passes the Task 3.1 EvidenceLanding contract, all Task 4.1
  replay cases, and source-family adapter cases without a fake-success implementation.
- Focused landing verification is `16 passed`; default Canonical V2 is `39 passed, 24 skipped,
  4 xfailed`. Forced interface execution is exactly one EvidenceLanding pass and four
  `ModuleNotFoundError` failures for the future KnowledgeBuild/Read/Answer/ReleasePublication seams.
- S1 is `10 passed, 5 skipped`; S2/S2B is `32 passed`; Ruff, Pyright, strict OpenSpec, and diff checks
  pass.
- Formal admission remains `accepted/50`; original pause/volume and Milvus/salvage hashes, recovery
  isolation, and the read-only candidate identity/C2_0003/24-table/zero-row state are unchanged.
- No migration, durable database row, actual source replay, Milvus/provider access, canonical or
  release/index mutation, dependency, or runtime consumer change occurred. Task 4.3 remains
  unstarted.
