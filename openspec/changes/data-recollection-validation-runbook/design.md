## Context

The collection and cleaning fixes for professor seeds, professor
quality, professor facts, professor admin review, homepage-first paper
and patent attribution, paper enrichment, summary promotion, and Milvus
refresh have been implemented and archived. The remaining issue is not
that old rows need more analysis; the old rows were produced by earlier
partial flows and are disposable verification data.

This change defines the operational layer after implementation:
operators need a safe way to remove stale verification rows, recollect
through the fixed flows, and produce one evidence package that answers
"is the recollected data usable enough for the next review?"

## Goals / Non-Goals

**Goals:**

- Provide a repeatable cleanup and recollection runbook with dry-run
  preview, explicit target database, and backup/export checkpoint.
- Run bounded seed batches before any full recollection.
- Validate the recollected output using operational evidence:
  collection counts, seed status transitions, pipeline issue taxonomy,
  quality-status distribution, fact extraction coverage, paper/patent
  link evidence, summary readiness, Milvus refresh results, and RAG
  retrieval sanity.
- Persist the evidence in a run workspace so later agents can audit what
  happened without rerunning collection.
- Keep destructive actions explicit and reversible until the user
  approves the final cleanup command.

**Non-Goals:**

- No changes to collection semantics, ranking, identity matching, or
  quality-state definitions.
- No new database schema or Milvus collection schema.
- No attempt to rescue legacy verification rows collected by broken
  flows.
- No full production run without a bounded sample pass and explicit
  user approval.

## Decisions

1. **Use a runbook plus small scripts instead of embedding recollection
   into existing pipelines.**

   Rationale: the existing pipeline code now owns collection behavior.
   This change only orchestrates cleanup, bounded execution, and
   evidence reporting. Keeping that orchestration outside the core
   collectors prevents accidental semantic drift.

   Alternative considered: add cleanup/recollection modes directly to
   seed, paper, and Milvus scripts. Rejected because it mixes operator
   lifecycle concerns into domain collectors.

2. **Require a dry-run preview before destructive cleanup.**

   Rationale: cleanup can remove disposable verification rows. Even
   when the user has approved deleting old data in principle, the target
   database and affected tables must be visible before the destructive
   step.

   Alternative considered: direct truncation by table list. Rejected
   because a wrong `DATABASE_URL` or stale environment variable would be
   too costly.

3. **Treat current database volume as non-authoritative until
   recollection completes.**

   Rationale: row counts collected through old flows are not a useful
   quality signal. The validation report should measure only the
   recollection batch it just ran.

   Alternative considered: compare against previous global row counts.
   Rejected because that rewards retaining legacy artifacts.

4. **Use bounded seed batches as the promotion gate to larger runs.**

   Rationale: seed trigger safety was identified as an operational gap.
   A sample batch validates status semantics, adapter coverage, failure
   taxonomy, paper/patent extraction, summary promotion, and Milvus
   refresh before long-running full seeds are attempted.

   Alternative considered: immediately run all known seeds. Rejected
   because supported seeds can produce hundreds of profiles and mask
   failure semantics.

5. **Generate one run workspace per recollection attempt.**

   Rationale: the platform needs durable evidence, not terminal-only
   status. A run workspace makes the exact commands, environment
   fingerprint, row deltas, issue samples, and retrieval checks
   reviewable.

## Implemented Operator Contract

The implemented operator entrypoint is:

```bash
cd apps/miroflow-agent
uv run python scripts/run_data_recollection_validation.py <subcommand>
```

Supported subcommands:

- `init-workspace` creates
  `.agents/runs/data-recollection-validation-runbook/<run-id>/` with
  placeholders for environment, cleanup preview, batch plan,
  validation report, and command verification.
- `cleanup-preview` reports the target database fingerprint, Alembic
  revision, affected cleanup-scope tables, row counts, and whether the
  invocation is dry-run or destructive. It is dry-run by default.
  Destructive execution requires both `--destructive` and
  `--confirm-database <current_database()>`.
- `plan-batch` writes a bounded recollection plan. Sample batches
  require explicit `--seed-id` values plus `--sample-limit`. Full runs
  are blocked unless `--sample-evidence` points to an existing sample
  report.
- `generate-report` renders the evidence sections used for stakeholder
  review. Report verdicts separate code-path success from
  data-readiness success and incomplete evidence.

Cleanup scope is intentionally narrow. It includes disposable generated
verification rows in these tables when they exist:

```text
professor_paper_link
professor_patent_link
professor_fact
professor_affiliation
professor_admin_action
paper_full_text
paper_title_resolution_cache
paper
patent
professor
pipeline_issue
pipeline_run
```

Cleanup scope explicitly excludes source backfills, seed definitions,
schema history, archived OpenSpec evidence, and raw source assets. In
particular, `professor_seed`, `alembic_version`, and
`source_backfill` are protected and rejected by the cleanup helper.

The bounded batch plan is not a replacement for the domain collectors.
It records the intended existing commands and bounds for the operator
to run only after the cleanup dry-run evidence is reviewed. Runtime
fields to capture in the run workspace are seed ids, pipeline run ids,
elapsed time, status transitions, processed counts, and failure
reasons.

## Risks / Trade-offs

- Wrong database target -> Mitigation: require target fingerprint,
  database name, current Alembic revision, and affected row preview in
  dry-run output.
- Cleanup removes rows needed for debugging -> Mitigation: export
  pre-cleanup snapshots or table counts before delete/truncate.
- External pages or APIs are unstable during recollection -> Mitigation:
  classify failures by seed and stage, and keep failed URLs in the
  evidence report.
- Bounded sample passes but full run later fails -> Mitigation: the
  runbook separates sample acceptance from full-run acceptance and
  requires recording both.
- Summary generation cost or latency is high -> Mitigation: support
  targeted paper ids and batch-size controls; report skipped or failed
  papers separately from collector failures.
- Milvus refresh succeeds but retrieval is poor -> Mitigation: include
  query sanity checks with expected paper/professor hits and record
  top-k evidence.
