## Context

P6 created a deterministic Professor seed readiness gate. The latest matrix
shows one blocked row, seed 5, and 19 rows whose latest bounded sample run
succeeded with `full_recollection_allowed=true`.

P7 consumes that matrix and runs controlled `full` mode only for eligible rows.
The stage must remain auditable because `full` mode writes canonical Professor
bundles and can change downstream data quality metrics.

## Goals / Non-Goals

**Goals:**

- Re-read the latest P6 readiness matrix immediately before execution.
- Select only rows with `recommended_next_mode=full` and
  `full_recollection_allowed=true`.
- Execute controlled `full` recollection for each selected seed.
- Record a row-level full-run E2E matrix with run ids, terminal status, item
  counts, failure class, and issue outcome.
- Leave seed 5 visible as blocked and excluded.
- Produce a P8 handoff that separates data-quality validation from P7
  execution.

**Non-Goals:**

- No cleanup, truncation, hard deletion, or historical-data rewrite.
- No full execution for seed 5 or any row not currently full-ready.
- No online RAG publish/index refresh; that belongs to a later stage.
- No schema migration or public API change.

## Decisions

### Decision 1: Candidate selection is matrix-derived

P7 should call the readiness planner and select rows from the latest matrix
instead of relying on the P6 acceptance table alone. This catches drift if a
seed's latest status changes between P6 archive and P7 execution.

Alternative considered: use the archived P6 candidate list directly. That list
is useful context but can become stale after additional runs.

### Decision 2: Execute full runs sequentially by default

The initial P7 runner should execute candidates sequentially in stable seed-id
order. This is slower than concurrent execution, but it keeps external-site
load, database writes, and failure diagnosis simple for the first full
recollection pass.

Alternative considered: parallel full execution. This can be introduced later
after the first full pass proves data-quality and runtime behavior.

### Decision 3: P7 validates execution, not quality acceptance

P7 completion means eligible seeds were run in `full` mode and row-level E2E
evidence was recorded. It does not mean the resulting canonical dataset passes
all quality, retrieval, or publication gates. Those become P8/P9 inputs.

Alternative considered: bundle quality audit and publish refresh into P7. That
would make the stage too broad and obscure which failure came from collection
versus downstream validation.

### Decision 4: Full-run failures are recorded, not hidden

If any eligible seed fails in `full` mode, P7 records the failure class and
issue evidence in the matrix. P7 is not complete until every selected row has a
terminal full-run result, but it may complete with failures if the acceptance
record explicitly shows them and P8 handoff classifies the remediation path.

Alternative considered: require all full runs to succeed before completing P7.
That would hide useful terminal evidence and could block later quality work
behind a single external-site outage.

## Risks / Trade-offs

- External sites can change during the full run -> each row records its own run
  id and terminal failure class.
- Full mode writes canonical Professor rows -> P7 explicitly excludes cleanup
  and defers quality decisions to P8.
- Sequential runs may take longer -> stable ordering improves auditability and
  avoids avoidable load on school sites.
- Existing historical issues may remain after a successful full run -> the P7
  matrix uses latest full-run status as execution evidence while preserving
  issue references for context.
