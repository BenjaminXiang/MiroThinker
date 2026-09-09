## Why

The baseline case closure fixed Ahmed Elazab, Ding Wenbo, and pFedGPA, but the
real Professor/Paper dataset still fails the release-quality audit because
thousands of records remain below the user-facing quality contract. A separate
dataset-level closure is needed so broad backfills are planned, dry-run first,
traceable, reversible, and kept within the official Professor profile -> paper
chain.

## What Changes

- Add a dataset-level quality closure contract for the remaining Professor core
  profile and Professor-linked Paper blockers.
- Introduce read-only blocker bucketing before any write-mode backfill.
- Require bounded dry-run evidence for profile-summary repair, Chinese research
  overview backfill, Professor paper-summary generation, and duplicate paper
  merge candidates.
- Define batch write rules with per-batch quality re-evaluation, alias audit,
  API sampling, and index-refresh selection.
- Require every skipped or unsafe record to become a visible unresolved issue or
  residual-risk row instead of being silently ignored.
- Preserve the existing domain boundary: Professor core readiness depends on
  official roster/profile/paper evidence, while company/news association stays
  in runtime multi-source recall or the Company/News domains.

## Capabilities

### New Capabilities

- `professor-dataset-quality-closure`: Defines the controlled dataset-level
  closure process for clearing or explicitly classifying Professor core profile
  and Professor-linked Paper quality blockers.

### Modified Capabilities

- None. Existing Professor audit, summary-field, final-validation, seed, and
  retrieval capabilities remain consumers or neighbors of this closure contract.

## Impact

- Affected scripts and services:
  - Professor core profile-paper quality audit and post-full audit scripts.
  - Professor profile-summary repair and research-overview backfill scripts.
  - Professor output-summary generation.
  - Paper title-enrichment and merge-alias backfill.
  - Professor quality re-evaluation and pipeline issue recording.
  - Index/vector refresh selection for changed Professor and Paper rows.
- Affected APIs and UI checks:
  - Admin Professor detail API sampling for profile sections and paper lists.
  - Paper detail route sampling for merge aliases and PDF/external links.
  - Professor workbench paper-link behavior remains a regression surface.
- Affected data:
  - Existing `miroflow_real` Professor rows with short summaries.
  - Existing Professor profile sections missing Chinese research overviews.
  - Professors with verified papers missing `paper_summary`.
  - Active verified duplicate Professor-paper title/year groups.
- This change is behavior-affecting. The new
  `professor-dataset-quality-closure` capability owns the behavior contract for
  dataset-level blocker closure and residual-risk classification.
