# Acceptance — paper-implausible-title-cleanup

> Each item maps to a requirement/scenario in `specs/paper-title-cleanup/spec.md`.
> Evidence under `.agents/runs/paper-implausible-title-cleanup/`. Mark Met / Partial /
> Unmet with the artifact or the specific gap.

## A1. Implausible-title rejection (spec §1)
- **A1.1** `is_clearly_garbage_paper_title(title_clean)` True + `prof_page_only` + not already rejected/merged ⇒ scan rejects (`identity_status='rejected'`). — RED 5.2.
- **A1.2** Plausible title ⇒ unchanged. Already rejected/merged ⇒ skipped. — RED 5.2.

## A2. Evidence + traceability (spec §2)
- **A2.1** Applied rejection files `pipeline_issue` at stage `title_cleanup` / `reported_by='paper_title_cleanup_scan'` with `run_id`; distinct from W0b `identity_gate` issues. — RED 5.1.
- **A2.2** `quality_status` not mutated. — RED 5.1.

## A3. Retrieval exclusion (spec §3)
- **A3.1** Rejected paper not indexable (`_is_indexable_paper`); after re-backfill, not in retrieval. — W0b's existing test + 6.3 spot-check.

## A4. Admin display exclusion (spec §4)
- **A4.1** `/paper` list default-excludes `identity_status in {rejected, merged}`; exposes `identity_status`; filter can include them. — RED 5.3.
- **A4.2** After scan apply + re-backfill, the user's example garbage titles ("Co-supervised PhD student", "011 (IF: 26.8") no longer appear on `/paper` default. — 6.3 spot-check.

## A5. Dry-run + flag + non-destructive (spec §5)
- **A5.1** Default dry-run writes nothing + JSONL + counts; `PAPER_TITLE_CLEANUP_ENABLED` falsy ⇒ skip. — RED 5.2.
- **A5.2** No LLM calls in the scan (pure rule-based). — code review.

## A6. Baseline / blast-radius
- **A6.1** Eligibility baseline recorded before `--apply`; applied reject count compared. — 1.2 + 6.1.

## Out of scope (explicitly not accepted here)
- Auto-restore on title correction (deferred).
- Parser root-cause fix (W1b — prevention at ingest).
- Rejecting plausible-titled `prof_page_only` papers (W0b's job).
