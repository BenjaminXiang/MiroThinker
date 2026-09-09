# Slice Contract: S5G Temporal Precision Correction

## Status

Accepted at `2026-07-13T09:19:45Z`. The user accepted the preserve-precision direction and
`explicit-calendar-v1` comparison policy on 2026-07-13; ADR-012 and the active OpenSpec record both
decisions. Pure contracts, both real-disposable PostgreSQL adapters, C2_0008 migration cycles,
restart/tamper/direct-SQL checks, static checks, strict OpenSpec, and the affected S5 regression
surface are GREEN. The merged specification/code-quality review has zero open Critical/Important
findings. Task 6.3 may resume from this Accepted dependency.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `5.7`
- Decision: `docs/architecture-decisions/ADR-012-canonical-v2-preserve-temporal-precision.md`

## Goal

Provide one precision-preserving temporal value contract for validity bounds across retained source
assertions, canonical current selections, typed domain subobjects, canonical JSON/hashes, PostgreSQL,
and restart reconstruction, without fabricating missing source time information.

## Non-goals

- No domain projection GREEN, relationship/path implementation, release publication, query, answer,
  or consumer migration.
- No full bitemporal model for static values.
- No UTC-midnight conversion for date-only values.
- No original/recovery/durable-candidate write.

## Allowed scope

- Canonical V2 shared temporal contracts and their pure helpers.
- Narrow decision/identity/projection contract adapters required to consume the shared type.
- One reversible Canonical V2 migration only if existing disposable S5 persistence requires a
  representation change.
- Focused S5/S6 temporal tests plus this slice's OpenSpec/evidence artifacts.

## Forbidden changes

- Legacy V042 schemas or code; active release/index pointers; original PostgreSQL/Milvus; recovery
  checkpoints; domain/relation/path business policy; broad refactors; unrelated dependency changes.
- Silent coercion between precision kinds or weakening assertion-to-projection lineage equality.

## Required RED cases

1. Date-only validity round-trips as date-only through JSON, hashing, PostgreSQL, and restart.
2. Instant validity canonicalizes equivalent offsets to one UTC instant without becoming date-only.
3. Same lexical day with different precision is not exact temporal equality.
4. Cross-precision comparison without caller-supplied calendar/timezone context returns
   `indeterminate` and never reads ambient/system defaults.
5. Tampering only with precision changes content identity and is rejected.
6. Under explicit `Asia/Shanghai` and UTC contexts, the same date produces the corresponding
   half-open civil-day interval for comparison only; an inside instant overlaps but is not equal.

## Required checks

- Focused pure shared-contract, decision, identity, and projection temporal matrices.
- Explicit disposable-Postgres migration/adapter/restart checks when storage changes.
- Prior S5 temporal/history regression plus the S6 affiliation date-only reproduction.
- Ruff, Pyright, strict OpenSpec, diff/secret/scope checks, and frozen-source audit.
- Independent specification/code-quality review with zero open Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- OpenSpec tasks, acceptance, and change log
- ADR-012 if the named cross-precision policy materially changes the accepted decision

## Stop conditions

- The representation requires inventing a timezone or instant absent from the source.
- Implementation requires an ambient/default timezone, rewrites stored dates, or changes
  `indeterminate` into guessed ordering.
- Migration would touch any non-disposable or durable-candidate database.
- The change expands into S6 domain behavior or weakens accepted S5 history/lineage invariants.

## Done means

- Task 5.7 has RED/GREEN and restart evidence for both precision kinds and fail-closed comparison.
- Affected S5 decision/identity/history contracts remain GREEN.
- The S6 date-only affiliation reproduction reaches the shared temporal interface without coercion.
- Independent review accepts S5G; Task 6.3 may then resume from its preserved worktree.
