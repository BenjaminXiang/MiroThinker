# Verification Contract: professor-core-profile-paper-quality

## Purpose

This change is behavior-affecting. The verification oracle is the OpenSpec
requirements in
`openspec/changes/professor-core-profile-paper-quality/specs/professor-core-profile-paper-quality/spec.md`.
Unit tests alone are not sufficient because the defect class spans schema,
pipeline state, real database quality, Admin API/UI behavior, and chat citation
routes.

## RED Evidence Required Before Production-Code Edits

- A read-only database audit showing the current baseline for:
  - Professor summary length and ready-status mismatch.
  - Missing durable Chinese research overview.
  - Missing Professor `paper_summary` for Professors with verified papers.
  - Active duplicate verified paper title/year groups.
  - Ahmed Elazab duplicate paper state.
  - Ding Wenbo summary/profile completeness state.
  - pFedGPA missing arXiv/PDF enrichment state.
- Failing or pending regression tests/scenario checks for:
  - Ahmed Chinese research overview persistence.
  - Ahmed duplicate paper collapse.
  - Ding Wenbo core profile readiness and company-role non-blocking.
  - pFedGPA arXiv/PDF enrichment and `/paper/<paper_id>` route.
  - Professor workbench paper title links.
  - Chat paper citation URL shape.

## GREEN Evidence Required For Completion

- Migration tests pass for profile section storage and paper merge traceability.
- Professor section extraction/translation tests pass for Chinese source,
  English source, missing source, and source-hash idempotency.
- Paper deduplication tests pass for DOI, arXiv, title/year/author fallback,
  link migration, and merge alias resolution.
- Seed closure tests pass for full-run scheduling, sample-run non-promotion,
  idempotent rerun, and stage-failure issue recording.
- Professor quality gate tests pass for summary length, repetitive summary,
  missing research overview, duplicate paper links, missing `paper_summary`, and
  critical issue blocking.
- Admin API tests pass for persisted research overview and deduplicated paper
  payloads.
- Frontend tests or browser checks prove paper titles navigate to
  `/paper/<paper_id>`.
- Chat regression checks prove local paper citations use the configured base URL
  plus `/paper/<paper_id>`.
- Real database acceptance checks pass for Ahmed Elazab, Ding Wenbo, and
  pFedGPA.

## Commands To Record During Implementation

- OpenSpec validation:
  - `openspec validate professor-core-profile-paper-quality --strict`
- Targeted backend tests:
  - `uv run pytest <relevant professor/paper/admin tests> -q -n0 --no-cov`
- Targeted frontend tests:
  - `npm run test -- <ProfessorWorkbench related tests>` or documented nearest
    available frontend check.
- Read-only database audits:
  - exact command to be created by the implementation slice.
- Backfill dry-runs and write-mode commands:
  - exact commands, row counts, before/after distributions, skipped checks, and
    blockers.

## Completion Rule

Do not mark `tasks.md` complete or this change ready to archive until
`acceptance.md` and `.agents/runs/professor-core-profile-paper-quality/verification.md`
contain real command/API/UI evidence for every requirement or explicitly record
remaining blockers.
