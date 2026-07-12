# Slice Contract: s5e-proportional-temporal-semantics

## Status

Accepted at `2026-07-12T09:58:35Z` (Ready at `2026-07-12T08:59:41Z`, In Progress at
`2026-07-12T09:27:32Z`). This slice implements OpenSpec Task 5.5 against Accepted Task 5.4 commit
`3d9db81`. It does not authorize Task 5.6 aggregate S5 acceptance, S6 typed catalogs or projections,
any durable-candidate write, or full bitemporal query behavior.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `5.5`
- Depends on: Accepted Task 5.4 at commit `3d9db81`

## Lean execution

- This slice contract and OpenSpec Task 5.5 are the only implementation-plan sources.
- Implement one observable vertical RED/GREEN increment at a time and run only its nearest checks.
- Perform one merged specification/code-quality review for Task 5.5.
- Run complete regression and frozen safety/source checks only at the Task 5.5 commit checkpoint.

## Goal

Make temporal meaning proportionate and user-visible without imposing full bitemporal storage. Every
assertion keeps the exact time at which the build observed it and the optional source publication or
event time supplied by evidence. Naturally changing field or relationship facts may retain a
validity interval. Immutable decisions and assertions remain history; `current_fields` and
`current_relationships` contain only selected facts valid at the offline build's `as_of` instant.

The primary user-effect scenario is a Professor moving from institution A to institution B: both
evidence-backed affiliation episodes and their intervals remain auditable, while only B appears in
the current projection at and after the transition. This is expressed through generic relationship
episodes; S6 later defines the typed affiliation catalog and materialized Professor projection.

## Non-goals

- Implement two-axis bitemporal queries such as “what did the system know then about an event time.”
- Infer missing dates, close open intervals, choose a primary affiliation, or treat latest fetch time
  as proof that a conflicting value is newer or correct.
- Freeze the S6 field/sub-object/relationship catalog or implement typed domain projections.
- Implement review queues, aggregate current/history acceptance, publication, query, answer, Web,
  Milvus, or consumer migration.
- Add a migration merely to duplicate assertion time already present in C2_0002–C2_0006.

## Allowed scope

- Deepen the package-internal `CanonicalDecisionEngine.decide(request) -> result` interface and its
  existing PostgreSQL adapter; do not add a second caller-orchestrated temporal engine.
- Add exact validity to generic current-selection result types when derived from selected evidence.
- Focused pure and real-disposable PostgreSQL tests for time retention, current/history derivation,
  deterministic replay, tampering, and restart load.
- Minimal shared-contract reconciliation proven necessary by the RED scenarios.
- This slice, OpenSpec task/change log, and verification evidence.

## Forbidden changes

- Original/recovery/durable-candidate database write, original Milvus open, live provider call,
  release/index mutation, or production-like cutover.
- Generic `DATABASE_URL` fallback, inferred target identity, weakened backup/append-only/rollback
  gates, or overwriting prior assertions/decisions to make a value “current.”
- Latest-observation-wins, fabricated interval endpoints, silent overlapping-value flattening, or a
  global requirement that static identifiers carry validity history.
- S6+, legacy chat/query/admin/runtime changes, dependency additions, unrelated refactors, test
  weakening, or a new migration unless an observed persistence RED proves existing columns cannot
  retain the approved effect.

## Expected unchanged behavior

- Accepted S1–S4 and Tasks 5.1–5.4 remain GREEN.
- Identity decisions, source ownership, current/terminal identity history, and C2_0005/C2_0006
  persistence remain exact and append-only.
- Static assertions with no validity interval follow existing decision behavior and require no
  synthetic temporal history.
- `observed_at > as_of` remains `observed_after_build`; source event/publication time never replaces
  the knowledge-time cutoff.
- The four Task 3.1 future deep modules remain approved xfails.

## Temporal invariants

- `observed_at` is the build knowledge cutoff; `source_event_time` is optional source-supplied
  publication-or-event time and is retained independently.
- Validity uses half-open intervals `[valid_from, valid_to)`. Null endpoints stay unknown/open for
  membership evaluation but are never replaced with invented timestamps.
- A selected evidence set must have one exact validity pair. Different intervals are not unioned,
  intersected, or silently treated as equal even when values/attributes match.
- Relationship decisions copy the exact selected validity pair. Field current selections derive the
  same exact pair from their selected assertions without adding a duplicate durable column.
- A selected/accepted decision outside its interval remains immutable history but produces no
  current selection. At a shared boundary, the ending episode is historical and the starting episode
  is current.
- Unknown validity alone is not a hard gate. A selected fact with both endpoints null may remain
  current; known endpoints may prove that it has not started or has ended.
- Overlapping materially different current evidence follows the existing unresolved/structured-
  adjudication path; fetch recency never decides it automatically.
- `source_event_time` alone never synthesizes a validity interval. Typed point-event versus ongoing-
  state serving semantics remain owned by the versioned S6 relationship catalog.
- Reordering or exact replay at one `as_of` yields identical decisions, current/history projections,
  and content hashes. Crossing an observation or validity boundary may change only the current
  subset; retained evidence and decisions do not disappear.

## Vertical increments

1. **Current/history relationship episodes:** RED then implement old/new Professor affiliation
   episodes, half-open boundary behavior, future episodes, unknown endpoints, and exact selected
   interval propagation into decisions/current projections.
2. **Field/static and conflict invariants:** prove selected field validity is derived exactly, static
   identifiers incur no temporal burden, interval-mismatched equal evidence does not auto-merge, and
   overlapping different values remain unresolved without adjudication.
3. **Integrity and replay:** reject a historical/future decision inserted into current, a missing
   valid current selection, changed decision/current interval, or reordered/rehashed temporal
   projection; retain source observation/event time exactly.
4. **PostgreSQL restart:** persist/load/replay the transition through existing C2_0005+ storage,
   proving assertion times, relationship decision intervals, derived current subsets, atomic
   rollback, and no schema duplication.

## Required checks

- Every new production behavior has an observed failing test before implementation.
- L1 uses only the nearest pure or PostgreSQL scenario.
- L2 covers the complete Task 5.5 temporal matrix plus directly affected decision/store siblings.
- At the commit checkpoint: complete Canonical V2/S1/S2/S2B/S4/S5 regression required by the
  verification contract, Ruff, Pyright, wheel contents, strict OpenSpec, diff/secret/formal gate,
  source pause/hash/isolation, forced-read-only durable-candidate audit, and owned disposable cleanup
  pass.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`

## Stop conditions

- The user effect requires independent source publication and occurrence timestamps on one
  assertion, time precision/uncertainty, multiple discrete episodes under one relationship ID, or
  full knowledge-time/event-time querying absent from approved OpenSpec.
- Correctness requires S6 typed catalog semantics, a new public interface, or a migration not
  justified by an observed Task 5.5 persistence failure.
- A command resolves to an original/recovery/durable-candidate/ambiguous target, or accepted source/
  gate identity changes.
- Task 5.6+, live provider, domain projection, release, query, answer, or index work is required to
  make focused Task 5.5 checks pass.

## Done means

- The affiliation transition, boundary, future, unknown-endpoint, overlap-conflict, static-field,
  source-time, replay, and tamper scenarios are GREEN through one deep decision interface.
- Current selections are exactly the as-of-valid subset of immutable selected/accepted decisions;
  prior and future evidence/decisions retain their times and remain available for audit.
- A fresh process reconstructs the identical typed result from existing append-only PostgreSQL
  history without a duplicate temporal store or inferred timestamps.
- The merged review has zero open Critical/Important findings, checkpoint evidence is current, Task
  5.5 is Accepted and committed alone, and Task 5.6 production work has not started in the same
  commit.

## Acceptance checkpoint

- Pure shared-contract and decision matrix: `39 passed`; focused real-disposable decision storage:
  `16 passed`.
- Explicit no-database Canonical V2: `136 passed, 82 skipped, 4 approved xfails`; real S5E
  disposable Canonical V2 excluding the fixed-name S4C module: `208 passed, 4 approved xfails`;
  independent S4C compatibility: `10 passed`.
- S1 target/write-gate safety: `17 passed`; S2/S2B harnesses: `32 passed`; S4E checkpoint harness:
  `23 passed`; formal backup gate remains `accepted/50`.
- Ruff format/check, targeted Pyright, wheel contents through C2_0006, diff/whitespace,
  high-confidence secret scan, writer-import isolation, and strict OpenSpec passed.
- The single merged specification/code-quality review ended `APPROVED`. Its non-UTC hash/restart and
  private-exception findings were repaired with UTC canonicalization, typed generation errors, and
  corrupt-restart coverage; zero Critical/Important findings remain.
- Original `pgtest` remains paused on exact volume `d81c6381…d241`; original Milvus and verified FPI
  salvage hashes remain `43ef203e…67cc` and `cef8eb6b…bb7`. The durable candidate remains forced-
  read-only audited at C2_0004 with landing `15/6/6/21/6` and zero rows in all 20 knowledge/publish
  tables.
- Owned disposable `75195921…ce9` used PostgreSQL system ID `7661567410199961641`, network `none`,
  no ports, restart `no`, read-only rootfs, and tmpfs PGDATA. Its S5E/S4C bases ended at C2_0006 with
  zero business rows; container, socket, test databases, and wheel artifacts were removed. Docker
  volume-set SHA-256 stayed `8314a2b0…896c`.
- No migration, durable-candidate write, original/recovery write, Milvus open, provider call,
  domain projection, publication, query/chat change, index rebuild, push, PR, or cutover occurred.
  Task 5.6 owns review queues, aggregate S5 acceptance, and the deferred `superseded` relationship-
  interval contract.
