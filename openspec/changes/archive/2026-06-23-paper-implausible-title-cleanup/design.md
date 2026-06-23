# Design — paper-implausible-title-cleanup

## Context

W0b (`wire-paper-identity-gate-rejection`) introduced `paper.identity_status` transitions
+ the `is_plausible_paper_title` guard. W0b's `decide_identity_status_rejection` returns
`no_change` / `implausible_title` for garbage titles — deliberately deferring them to a
cleanup step. This change IS that cleanup step.

## Why a separate scan (not a W0b mode)

W0b's scan (`run_paper_identity_scan.py`) runs the LLM same-person gate per professor
(heavy, ~1.5s/batch call). Title-cleanup is **pure rule-based**
(`is_clearly_garbage_paper_title`, no LLM) — fast and cheap (can scan all 97k papers in
seconds). Mixing the two would either force LLM cost on a rule-based check or complicate
the W0b scan. A separate lightweight script (`run_paper_title_cleanup_scan.py`) is
cleaner and lets the two scans run independently.

## Writer parameterization

`apply_identity_status_rejection` currently hardcodes `_STAGE = "identity_gate"` +
`_REPORTED_BY = "paper_identity_scan"`. To file title-cleanup issues at a distinct stage
(`title_cleanup`) + reported_by (`paper_title_cleanup_scan`), extend the writer with
`stage` + `reported_by` keyword params (defaulting to the W0b values for backward
compat). This keeps W0b + title-cleanup issues distinguishable in `pipeline_issue` while
sharing the `rejected` status + restore machinery. The `_fetch_open_issue` query filters
by stage + reported_by, so the two issue streams don't collide.

## Display exclusion

`PAPER_SELECT_SQL` adds `WHERE p.identity_status NOT IN ('rejected','merged')` as a
**default** condition (applied when no explicit identity_status filter is requested),
and `SELECT p.identity_status`. The existing filter UI (`domains.py` filter parsing)
gains an `identity_status` filter option so admins can explicitly show `rejected`/
`merged` for review. This preserves admin review capability while defaulting to a clean
view (the user's ask: "don't show garbage on /paper").

## Reversibility decision (deferred auto-restore)

W0b's `restore_identity_status` triggers when a `verified` link appears. Title-cleanup's
analog would trigger when a title is corrected (re-scraped to plausible) — a rarer event
requiring re-ingest. Auto-restore on title correction is **deferred** to keep this change
tight; manual restore via the admin workbench (or a re-scan with a restore mode) remains
available. The `pipeline_issue` at `title_cleanup` records the prior status for a future
restore path.

## Risks

- **Classifier false positives**: `is_clearly_garbage_paper_title` is high-precision by
  design — it deliberately spares real technical titles that the broad
  `is_plausible_paper_title` over-flags. (The initial plan reused
  `is_plausible_paper_title`, but the dry-run showed ~30-50% false positives on real
  titles like "Kinetic Modeling and Reaction Engineering" — flagged by the broad guard's
  over-aggressive `.search()` rules + person-name helpers; the dedicated high-precision
  classifier fixed this: 30/30 reject samples are clear garbage, real titles spared, and
  it additionally catches 284 broad-missed "Not explicitly ... in text" parser-noise rows.)
  Residual risk is low; mitigation remains dry-run-first + `pipeline_issue` traceability
  + restore.
- **Blast radius**: like W0b, the eligible set is `prof_page_only` + implausible title;
  the 2026-06-22 scan will quantify it. The apply is bounded + reversible.
- **Display default change**: default-excluding `rejected`/`merged` from `/paper` changes
  what admins see by default. Mitigation: the filter UI still allows showing them; this
  is the intended UX (clean default, opt-in review).

## Open questions

- Should the scan cover ALL papers with implausible titles, or only `prof_page_only`?
  (Draft: `prof_page_only` — the parser-garbage source. Non-prof_page_only sources have
  API-sourced real titles. Extend if garbage is found elsewhere.)
- Should the `/paper` default-exclusion also hide `quality_status='rejected'` papers
  (25,894 of them per the 2026-06-22 scan)? Most are already `identity_status='merged'`
  (24,327) and thus hidden by the identity_status filter; the residual is small. Confirm
  against the existing `quality_status` semantics before extending.
