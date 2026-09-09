# Acceptance — paper-implausible-title-cleanup

> Each item maps to a requirement/scenario in `specs/paper-title-cleanup/spec.md`.
> Evidence under `.agents/runs/paper-implausible-title-cleanup/`. Mark Met / Partial /
> Unmet with the artifact or the specific gap.

## A1. Implausible-title rejection (spec §1)
- **A1.1** `is_clearly_garbage_paper_title(title_clean)` True + `prof_page_only` + not already rejected/merged ⇒ scan rejects (`identity_status='rejected'`). — RED 5.2.
- **A1.2** Plausible title ⇒ unchanged. Already rejected/merged ⇒ skipped. — RED 5.2.

## A2. Evidence + traceability (spec §2)
- **A2.1** Applied rejection files `pipeline_issue` at stage `identity_gate` / `reported_by='paper_title_cleanup_scan'` with `run_id` — distinct from W0b's (`paper_identity_scan`) by `reported_by` (the `pipeline_issue.stage` CHECK constraint has no `title_cleanup` value, so the allowed `identity_gate` is reused). — RED 5.1 + **full apply (2026-06-22): 528 `pipeline_issue` at `identity_gate`/`paper_title_cleanup_scan` with `run_id` (`apply-2026-06-22.jsonl`)**.
- **A2.2** `quality_status` not mutated. — RED 5.1.

## A3. Retrieval exclusion (spec §3)
- **A3.1** Rejected paper not indexable (`_is_indexable_paper`); after re-backfill, not in retrieval. — W0b's existing test + **targeted Milvus delete (2026-06-23): the 528 title-cleanup-rejected papers' chunks are part of the 33,335 rejected/merged removed from `apps/miroflow-agent/milvus.db` (delete-sample 4→0, confirmed survive, backup at `mirothinker-milvus-backup-20260623.db`)**. Retrieval visibility after admin-console reload.

## A4. Admin display exclusion (spec §4)
- **A4.1** `/paper` list default-excludes `identity_status in {rejected, merged}`; exposes `identity_status`; filter can include them. — RED 5.3.
- **A4.2** After scan apply (528 rejected) + Milvus delete, the user's example garbage titles ("Co-supervised PhD student", "(IF=14.7)" citations, parser noise) are `rejected` and removed from `paper_chunks`; `/paper` default-exclusion (code, on branch) hides them after admin-console restart. — 6.2/6.3 evidence.

## A5. Dry-run + flag + non-destructive (spec §5)
- **A5.1** Default dry-run writes nothing + JSONL + counts; `PAPER_TITLE_CLEANUP_ENABLED` falsy ⇒ skip. — RED 5.2.
- **A5.2** No LLM calls in the scan (pure rule-based). — code review.

## A6. Baseline / blast-radius
- **A6.1** Eligibility baseline recorded before `--apply`; applied reject count compared. — dry-run-refined (561 high-precision rejects, 30/30 samples clear garbage) + **apply (2026-06-22): 528 rejected, 0 `ready` (455 `needs_enrichment` + 73 `rejected`); `identity_status` rejected 8,480→9,008** (`apply-2026-06-22.jsonl`).

## Out of scope (explicitly not accepted here)
- Auto-restore on title correction (deferred).
- Parser root-cause fix (W1b — prevention at ingest).
- Rejecting plausible-titled `prof_page_only` papers (W0b's job).
