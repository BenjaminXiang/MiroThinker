# Verification Contract: paper-source-gap-remediation-lanes

## Scope

This run workspace verifies the lane-based cleanup contract for active Paper
rows still missing `summary_zh` or `abstract_clean`.

## RED/GREEN Contract

### Source-Gap Lane Reporting

RED:

- `tests/data_agents/paper/test_source_gap_audit.py` fails until the system can
  classify active Paper source gaps into one primary lane, preserve secondary
  actions, produce source buckets, and compute deterministic lane selection
  hashes.

GREEN:

- The report includes lane counts, source buckets, sampled Paper ids,
  skip-reason counts, and deterministic selection hashes.
- Each row has exactly one primary lane.

### Existing-Source Summary Fast Path

RED:

- Script tests fail until an explicit existing-source fast path can avoid DOI
  providers, title resolvers, and PDF/full-text fetchers.

GREEN:

- Rows with usable `abstract_clean`, `paper_full_text.abstract`, or
  `paper_full_text.intro` are separated from source-acquisition work.
- Fast-path reports include processed, written, rejected, skipped, provider
  failure, and script-level row-error counts.

### Full-Text Slow Lane

RED:

- Slow-lane tests fail until PDF/full-text acquisition reports timeout, HTTP
  status, content-type, size-cap, parse, and fetched-but-no-usable-text
  residual buckets.

GREEN:

- Full-text acquisition does not write `summary_zh`.
- It persists only usable abstract, intro, or excerpt evidence and leaves the
  rest as source residuals with retry recommendations.

### No Direct LLM Fabrication

RED:

- Tests fail if any source-gapped row without usable source text is promoted to
  summary generation or written with `summary_zh`.

GREEN:

- LLM output is only used for translation, summarization, self-check, or
  classification from recorded evidence.
- Rows without usable source text remain in residual lanes.

### Professor-Seeded Boundary

RED:

- Tests fail if cleanup creates Professor-Paper links from author-name provider
  discovery.

GREEN:

- Cleanup may enrich already discovered Paper rows by title, identifier,
  official page, or full-text evidence.
- It must not create Professor paper lists from external author-name searches.

### Partial-Run Closure

RED:

- Tests fail if superseded workers can remain as ambiguous active runs without
  checkpoint evidence.

GREEN:

- Interrupted or superseded workers close as `partial` with checkpoint counts,
  written/skipped/rejected counts, and interruption reason.

## Required Evidence

- Read-only `miroflow_real` source-gap baseline artifact.
- Targeted unit/script tests for source-gap audit and each implemented lane.
- Ruff on touched Paper scripts/modules/tests.
- `openspec validate "paper-source-gap-remediation-lanes" --strict`.

## Non-Goals

- This contract does not authorize direct LLM summaries for rows without
  usable source text.
- This contract does not change Agentic RAG routing or frontend detail routes.
