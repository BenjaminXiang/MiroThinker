# Independent Review: S3 Interface and Database Foundation

## Disposition

Accepted at `2026-07-11T18:22:18Z` under the user's objective-verification self-approval
authorization. The review found and repaired every Critical/Important foundation issue before any
S4 adapter or domain builder depended on it. No S4 landing replay, canonical business row,
publication projection, provider call, or index write began.

## Review scope

- Accepted predecessor: S2B commit `a581ff5`.
- S3 implementation under review: commits `905ca35..e7fffe2` plus the Task 3.5 repair candidate.
- Behavior sources: OpenSpec proposal/design/delta specs/tasks/acceptance, verification contract,
  shared typed contracts, independent Alembic history, real constraint tests, and the five strict
  deep-module RED interfaces.
- Review question: can S4/S5+ code safely depend on one coherent interface/database foundation
  without losing evidence identity, provenance, reversible history, release scope, or source
  safety?

## Findings and disposition

| Finding | User/operator effect | Disposition |
|---|---|---|
| Future module tests could define duplicate `SourceRecord`, `CandidateRelease`, and publication types | Later adapters could silently lose parser, manifest, time, or verification evidence | Fixed: RED interfaces must re-export the shared classes and now construct their complete fields |
| Artifact parent ID did not bind the recorded parent hash; assertions could cite identities not mapped to their evidence record | Chain of custody could look valid while linking the wrong bytes or real-world object | Fixed with composite hash/provenance foreign keys and real rejection tests |
| Append-only tables allowed `TRUNCATE`; mutable parser/source-identity rows allowed provenance-field rewrite and deletion | A bulk or metadata operation could erase/rewrite audit history | Fixed with statement-level truncate guards plus field-aware update/delete guards while status/time progression remains allowed |
| Reversal/supersession only worked inside one release, then a global-ID repair still allowed self or wrong-subject lineage | Corrective releases could not retain history, or could claim a false predecessor | Fixed with globally unambiguous decision IDs, cross-release references bound to the same logical field/relationship, and self-reference checks |
| Structured-LLM decisions had a typed trace but no storage column | Model adjudication could not be reproduced or audited | Fixed with schema-checked JSONB trace storage on all three decision families |
| Relationship assertions admitted canonical endpoints and field decisions accepted non-field policies | Source assertions and canonical judgments could be conflated | Fixed in the shared validators and contract tests |
| Default repository xdist ran destructive migrations concurrently against one disposable database | A normal test command could race downgrade/upgrade and produce misleading failures or partial state | Fixed by making the Canonical V2 test subtree select zero automatic xdist workers; the default command proved serial |

No Critical or Important finding remains open.

## Accepted boundary, not deferred defects

- The five deep modules remain intentional strict RED and belong to S4/S7/S8/S9 implementation;
  forced RED is exactly five missing-module failures.
- Typed domain tables, identity-build repositories, policy/decision association cardinality,
  candidate verification records, and publication authorization belong to their named later slices.
  Those slices must use the accepted Pydantic seam and add transaction-level integration tests;
  direct caller SQL is not an accepted public interface.
- C2_0003 deliberately adds only shared-foundation integrity. It does not pre-implement landing
  parsers, canonical fusion, domain projections, Milvus, query planning, or answer generation.

## Verification evidence

- Review RED: eight serial C2_0002 database failures plus one relationship-contract failure; second
  pass four metadata/self-lineage failures plus two contract failures; final lineage pass two wrong-
  subject database failures plus one wrong-policy contract failure. The earlier parallel
  `FEEEEEEE` run was classified as the xdist migration-race finding, not product RED.
- Focused GREEN after C2_0003: all retained cases passed; full default Canonical V2 command reported
  `47 passed, 5 xfailed` without starting xdist workers.
- Forced interface RED reported exactly `5 failed`, all `ModuleNotFoundError` for the five future
  module seams after shared-type alignment.
- Real disposable migration exercised upgrade, downgrade through C2_0001, and re-upgrade. It ended
  at C2_0003 with 24 shared tables, zero rows, 141 constraints, 44 non-internal triggers, and three
  LLM-trace columns.
- Two disposable dumps and the durable candidate dump normalized to SHA-256
  `7d85702ecb0e84cbbbbbc175f88c4b735190e53f4a576c72e49088899dd94991` over 63,875 bytes after
  removing exactly two PostgreSQL 16 random control lines.
- Durable candidate `miroflow_canonical_v2_candidate_s3b` was forward-upgraded only to C2_0003 and
  matched the disposable structure/counts with zero business rows. The disposable was then dropped.
- S1 safety reported `10 passed, 5 explicit skips`; S2/S2B reported `32 passed`; Ruff passed,
  Pyright reported zero findings, strict OpenSpec passed, and `git diff --check` passed.
- Formal S2B admission remained `accepted/50`. Original `pgtest` remained paused on its exact
  volume, recovery lab remained network-none/no-port, and original Milvus/salvage hashes matched.

## Acceptance rationale

The accepted S3 surface now preserves the effects later slices require: one shared type vocabulary,
immutable and hash-bound evidence, record-to-identity provenance, reversible cross-release decision
history, release-scoped canonical endpoints, auditable LLM judgment, deterministic schema identity,
and fail-closed target/test behavior. The remaining RED modules are explicit next-slice work rather
than hidden partial implementation, so S4 may receive its own Ready contract.
