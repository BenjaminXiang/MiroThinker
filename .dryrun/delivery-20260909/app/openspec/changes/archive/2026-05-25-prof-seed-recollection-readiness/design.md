## Context

The Professor seed line now has three archived foundations:

- `professor-seed-management` introduced the persisted `professor_seed`
  inventory and per-seed trigger.
- `professor-seed-ops-hardening` introduced bounded trigger modes and
  failure-class evidence.
- `professor-seed-adapter-coverage` plus
  `professor-blocked-seed-source-remediation` proved the current seed rows have
  either named resolver coverage or explicit blocked evidence, and moved the
  UESTC/SIAS rows to the official yjsjy mentor source.

P6 is the bridge between that coverage work and any broader recollection run.
Its job is not to recollect the whole dataset. Its job is to make the next
operator action for every current seed explicit, testable, and reversible.

## Goals / Non-Goals

**Goals:**

- Produce a row-level P6 readiness matrix for every current
  `miroflow_real.professor_seed` row.
- Derive a deterministic recommended next mode for each seed:
  `blocked`, `preview`, `sample`, or `full`.
- Require bounded E2E evidence before any seed can be recommended for
  unbounded full recollection.
- Keep approved blocked seeds, especially seed id 5 while it lacks an accepted
  official replacement source, visible as operational debt.
- Write P6 evidence into OpenSpec artifacts and the `.agents/runs/` verification
  record before P6 can be marked complete.

**Non-Goals:**

- No destructive cleanup, table truncation, or source-data deletion.
- No unbounded bulk recollection run.
- No expansion of online RAG domain coverage or chat behavior.
- No schema change to `professor_seed`, `pipeline_run`, or `pipeline_issue`.
- No change to P4/P5 semantics that allowed approved blocked evidence to pass
  the coverage guard while staying distinct from successful crawl coverage.

## Decisions

### Decision 1: P6 is a readiness gate, not a recollection run

The implementation should add a deterministic planner/reporting path instead of
starting with a broad runner. The planner reads the seed inventory, resolver
coverage, latest run status, and relevant issue evidence, then emits a matrix
that can be reviewed before any full run.

Alternative considered: run all non-blocked seeds in `full` mode immediately.
That would mix validation with irreversible data mutation and would bypass the
bounded-mode discipline created in `professor-seed-ops-hardening`.

### Decision 2: Full recollection requires post-P5 bounded success

A seed can only be recommended for `full` when it has a named resolver or
registered source path and a post-P5 bounded `sample` success with no fatal
issue. A successful `preview` is enough to recommend `sample`, not `full`.

Alternative considered: allow P4/P5 preview success to imply full readiness.
Preview mode intentionally avoids canonical writes, so it does not exercise the
write path or sample-size guard needed before full recollection.

### Decision 3: Blocked remains a first-class terminal recommendation

Rows with approved `fetch_blocked` evidence and no accepted official
replacement source are reported as `blocked`; they are not silently skipped.
The P6 matrix must show the issue id or reason, and `full_recollection_allowed`
must be false.

Alternative considered: omit blocked rows from the next-run plan. That would
make the matrix look cleaner while hiding operational debt and would break P4/P5
traceability.

### Decision 4: P6 artifacts define the execution handoff for P7

The P6 output should be usable as the input for the next stage. Rows recommended
as `sample` become P7 candidates. Rows recommended as `blocked` require source
remediation or operator acceptance. Rows recommended as `full` remain subject
to a later explicit operator confirmation before any unbounded run.

Alternative considered: bundle sample execution and full promotion into P6. That
would create a large stage with unclear rollback boundaries.

## Risks / Trade-offs

- External roster sites may change between P5 and P6, causing previously green
  rows to fail bounded E2E -> P6 records the latest failure class and blocks
  full recommendation until refreshed evidence is reviewed.
- Some preview/sample runs can update operational status tables even when they
  avoid canonical writes -> P6 must record exact commands and run ids, and it
  must not perform cleanup or deletion.
- The current `professor_seed` inventory may change while P6 is running -> the
  readiness script must emit the observed seed count and ids, and P6 completion
  requires acceptance evidence for every observed row.
- Existing historical `fetch_blocked` issues can remain after a later success ->
  the planner must prefer the latest bounded terminal run when deciding
  `recommended_next_mode`, while still preserving historical issue references
  as context.
