## Why

The admin `/paper` list surfaces parser-garbage "papers" — homepage-scraped text that is not a real paper title, e.g. "Co-supervised PhD student" (a role/bio fragment) or "011 (IF: 26.8" (a journal-impact-factor fragment). These are `prof_page_only` papers whose `title_clean` was extracted from a professor homepage by a parser that captured non-title text (root cause C2/C3 from the 2026-06-16 gap-analysis).

The existing `paper-identity-status` capability (introduced by `wire-paper-identity-gate-rejection`, W0b) deliberately leaves such implausible-titled papers `unverified`: its `decide_identity_status_rejection` returns `no_change` / `implausible_title`, because "garbage title" is a different problem from "wrong attribution" — W0b defers garbage titles to a separate cleanup step. **That cleanup step does not exist yet**, so the garbage flows through to the `/paper` display and to Milvus retrieval.

This change closes that gap: it adds the deferred title-cleanup pass that marks implausible-titled `prof_page_only` papers `identity_status='rejected'`, reusing W0b's `rejected` status + Milvus exclusion, and excludes `rejected`/`merged` papers from the admin `/paper` list by default. Garbage titles are then removed from both retrieval and the `/paper` interface, without hard-deleting rows (referential integrity + traceability preserved via `pipeline_issue`).

This is **behavior-affecting** (changes which paper rows are eligible for retrieval and which appear in the admin `/paper` list). The behavior contract is owned by the new capability `paper-title-cleanup`, which depends on `paper-identity-status` (W0b).

## What Changes

- **NEW behavior**: a `prof_page_only` paper whose `title_clean` is flagged by `is_clearly_garbage_paper_title` (a new high-precision classifier in `paper/title_quality.py`; the broad `is_plausible_paper_title` is reused unchanged by W0b but is too low-precision for rejection) transitions to `identity_status='rejected'` via a dedicated title-cleanup scan. The existing `paper/milvus_backfill._is_indexable_paper` filter already excludes `{rejected, merged}`, so such rows drop from retrieval with no Milvus code change (same as W0b).
- **NEW script** `scripts/run_paper_title_cleanup_scan.py`: dry-run by default, `--apply` to write, JSONL per-row decisions, `_ScanStats`-style counts. **No LLM calls** — the guard is pure rule-based, so this scan is cheap and fast (unlike W0b's LLM gate). Independent env flag `PAPER_TITLE_CLEANUP_ENABLED` (default off), separate from `PAPER_IDENTITY_GATE_ENABLED`.
- **Writer parameterization**: extend `paper/identity_status_writer.apply_identity_status_rejection` to accept `stage` + `reported_by` keyword params (currently hardcoded to `identity_gate` / `paper_identity_scan`), so the title-cleanup scan files `pipeline_issue` at stage `title_cleanup` / `reported_by='paper_title_cleanup_scan'`. This keeps W0b's `identity_gate` issues and the new `title_cleanup` issues distinguishable while sharing the `rejected` status + restore machinery.
- **Display exclusion**: `PAPER_SELECT_SQL` (admin-console `domains.py`) adds `WHERE p.identity_status NOT IN ('rejected','merged')` as a **default** (overridable via the existing filter UI, so admins can still review rejected papers), and `SELECT`s `p.identity_status`. After this + the scan apply, garbage titles no longer appear on `/paper` by default.
- **Non-destructive + traceable**: status transitions only (no row deletion); each rejection carries a stage-`title_cleanup` `pipeline_issue` with the implausible-title reason + `run_id`; `run_id` traceability preserved.
- **Reversibility (deferred)**: this change does NOT auto-restore when a title is later corrected (re-scraped to plausible). W0b's `restore_identity_status` handles the link-verified case; the title-corrected case is rarer and deferred to a follow-up. Manual restore via the admin workbench remains available.

## Capabilities

### New Capabilities
- `paper-title-cleanup`: the rule-based rejection of implausible-titled `prof_page_only` papers and their exclusion from admin display. Depends on `paper-identity-status` (W0b) for the `rejected` status + Milvus exclusion.

### Modified Capabilities
<!-- none — `paper-identity-status` is reused as-is (the `rejected` status + Milvus filter are unchanged). The writer's `stage`/`reported_by` parameterization is an internal change, not a behavior-contract change. -->

## Impact

- **Affected code**: new `apps/miroflow-agent/scripts/run_paper_title_cleanup_scan.py`; extend `apps/miroflow-agent/src/data_agents/paper/identity_status_writer.py` (`apply_identity_status_rejection` stage/reported_by params); new `paper/title_quality.is_clearly_garbage_paper_title` (high-precision; the broad `is_plausible_paper_title` is unchanged, W0b's); `apps/admin-console/backend/api/domains.py` `PAPER_SELECT_SQL` (default-exclusion + SELECT identity_status + filter option).
- **Retrieval**: `paper/milvus_backfill._is_indexable_paper` unchanged (already excludes `{rejected, merged}`); a Milvus re-backfill is required for the apply to take effect on already-indexed rows (same as W0b).
- **Storage**: no migration (reuses the existing `paper.identity_status` column + values; no new enum value). New `pipeline_issue` rows at stage `title_cleanup`.
- **Evidence/provenance**: each rejection carries `run_id` + the implausible-title reason in a `pipeline_issue`; scan JSONL records per-paper decisions.
- **Admin UI**: `/paper` list default-excludes `rejected`/`merged`; the existing filter UI can still show them on demand.
- **No public API change** (serialized formats unchanged); classifier A–G and `_VALID_DOMAINS` untouched.

## Non-goals

- Does **not** auto-restore when a title is later corrected (re-scraped) — deferred to a follow-up; manual admin restore remains available.
- Does **not** fix the parser root cause (C2/C3 — homepage extractor capturing non-title text). That is portfolio W1b (`homepage-parser-boundary-guards`), which prevents NEW garbage at ingest. This change REMEDIATES existing garbage; W1b prevents recurrence.
- Does **not** reject plausible-titled `prof_page_only` papers (those are W0b's identity-gate concern, not title-cleanup's).
- Does **not** hard-delete paper rows (status transition only; referential integrity preserved).
- Does **not** change `is_plausible_paper_title`'s rules (reused unchanged from W0b).
