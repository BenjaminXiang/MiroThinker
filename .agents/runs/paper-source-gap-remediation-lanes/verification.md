# Verification: paper-source-gap-remediation-lanes

## Source-Gap Audit Slice

### RED Evidence

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/data_agents/paper/test_source_gap_audit.py -q
```

Result: failed before implementation with
`ModuleNotFoundError: No module named 'src.data_agents.paper.source_gap_audit'`.

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/scripts/test_run_paper_source_gap_audit.py -q
```

Result: failed before implementation because
`scripts/run_paper_source_gap_audit.py` did not exist.

### Implementation Evidence

Changed behavior:

- Added `src/data_agents/paper/source_gap_audit.py`.
- Added `scripts/run_paper_source_gap_audit.py`.
- The audit is read-only and does not open pipeline runs or commit database
  transactions.
- CLI reports are compact by default and omit row-level classifications unless
  `--include-rows` is explicitly passed.

Lane precedence:

1. unsafe terminal rows;
2. existing usable source text;
3. DOI/arXiv/OpenAlex identifier metadata enrichment;
4. PDF/full-text acquisition;
5. `prof_page_only` parser/title cleanup;
6. review-only residual.

### Baseline Artifact

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python scripts/run_paper_source_gap_audit.py \
  --sample-limit 20 \
  --output ../../.agents/runs/paper-source-gap-remediation-lanes/paper-source-gap-audit-baseline-20260615.json
```

Result: passed. The compact artifact size is `5,206` bytes:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-source-gap-audit-baseline-20260615.json
```

Baseline lane counts:

| Lane | Count |
| --- | ---: |
| `existing_source_summary_fast_path` | 771 |
| `identifier_metadata_enrichment` | 4,605 |
| `professor_page_full_text_acquisition` | 38 |
| `prof_page_only_title_parser_cleanup` | 11,603 |
| `review_only_residual` | 303 |

Source buckets:

| Source | Count |
| --- | ---: |
| `prof_page_only` | 11,658 |
| `openalex` | 3,063 |
| `crossref` | 2,269 |
| `manual` | 287 |
| `dblp` | 41 |
| `semantic_scholar` | 2 |

### GREEN Evidence

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/paper/test_source_gap_audit.py \
  tests/scripts/test_run_paper_source_gap_audit.py \
  -q
```

Result: passed, `8 passed in 3.72s`.

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/paper/source_gap_audit.py \
  scripts/run_paper_source_gap_audit.py \
  tests/data_agents/paper/test_source_gap_audit.py \
  tests/scripts/test_run_paper_source_gap_audit.py
```

Result: passed, `All checks passed!`.

## Residual Risk

- This slice classifies remaining gaps but does not write summaries or source
  fields.
- The largest next lane is `prof_page_only_title_parser_cleanup` with `11,603`
  rows. It needs parser/title/source repair, not direct LLM fabrication.
- The `identifier_metadata_enrichment` lane has `4,605` rows that need a
  source-acquisition lane separated from summary generation.
- The `existing_source_summary_fast_path` lane has `771` rows that can be run
  through a no-source-acquisition summary path next.

## Existing-Source Summary Fast Path

### RED Evidence

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_parse_args_existing_source_only_refuses_doi_enrichment \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_existing_source_only_report_refuses_source_acquisition \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_cli_dry_run_dispatches_without_paper_update \
  -q
```

Result: failed before implementation because `--existing-source-only` was not
recognized and summary reports did not expose `existing_source_only` or
`source_acquisition_enabled`.

### Bounded Dry Run

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python scripts/run_paper_summary_zh_backfill.py \
  --existing-source-only \
  --limit 10 \
  --llm-profile deepseekv4pro \
  --dry-run \
  --log-level WARNING \
  > ../../.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-fastpath-dry-run-20260615.json
```

Result: passed. The dry run selected `10` rows, processed `6`, skipped `4`,
wrote `2`, rejected `4`, attempted `0` metadata enrichment, attempted `0`
full-text enrichment, and reported `source_acquisition_enabled=false`.

### Full Fast-Path Write Run

Command pattern:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python scripts/run_paper_summary_zh_backfill.py \
  --existing-source-only \
  --worker-count 8 \
  --worker-index <0..7> \
  --llm-profile deepseekv4pro \
  --log-level WARNING \
  > ../../.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-fastpath-20260615-worker<0..7>.json
```

Combined artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-fastpath-20260615-workers-summary.json
```

Result: passed. Eight workers selected `272` rows, processed `221`, skipped
`51`, wrote `83` Chinese summaries, rejected `138`, attempted `0` metadata
enrichment, attempted `0` full-text enrichment, and recorded `0` script-level
row errors.

### Post-Fast-Path Audit

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python scripts/run_paper_source_gap_audit.py \
  --sample-limit 20 \
  --output ../../.agents/runs/paper-source-gap-remediation-lanes/paper-source-gap-audit-after-existing-source-fastpath-20260615.json
```

Result: passed. Source-gap rows dropped from `17,320` to `17,248`.

| Lane | Before | After |
| --- | ---: | ---: |
| `existing_source_summary_fast_path` | 771 | 699 |
| `identifier_metadata_enrichment` | 4,605 | 4,605 |
| `professor_page_full_text_acquisition` | 38 | 38 |
| `prof_page_only_title_parser_cleanup` | 11,603 | 11,603 |
| `review_only_residual` | 303 | 303 |

Aggregate active Paper gap artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-gap-after-existing-source-fastpath-20260615-summary.json
```

Current active aggregate after this fast path:

- active Papers: `40,401`
- active Papers with `summary_zh`: `23,696`
- active Papers missing `summary_zh`: `16,705`
- active Papers with `abstract_clean`: `23,337`
- active Papers missing `abstract_clean`: `17,064`
- active DOI rows still missing summary: `4,689`

### GREEN Evidence

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/paper/test_source_gap_audit.py \
  tests/scripts/test_run_paper_source_gap_audit.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  -q
```

Result: passed, `55 passed in 7.64s`.

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/paper/source_gap_audit.py \
  scripts/run_paper_source_gap_audit.py \
  scripts/run_paper_summary_zh_backfill.py \
  tests/data_agents/paper/test_source_gap_audit.py \
  tests/scripts/test_run_paper_source_gap_audit.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py
```

Result: passed, `All checks passed!`.

### Residual Risk

- `83` summaries were written, but `138` rows were rejected by summary quality
  checks and `51` were skipped despite having some source evidence. These
  remain in the existing-source fast-path audit lane for prompt/validator
  review or manual adjudication.
- The remaining large gaps are not fast-path work. They require identifier
  metadata source acquisition, full-text slow-lane extraction, and
  `prof_page_only` parser/title repair.

## Identifier Metadata Source Lane

### RED Evidence

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_parse_args_identifier_metadata_only_refuses_summary_lanes \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_identifier_metadata_only_persists_source_without_llm_or_summary \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_identifier_metadata_only_reports_provider_miss_without_summary \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_identifier_metadata_only_reports_bad_doi_without_provider_call \
  -q
```

Result: failed before implementation because `--identifier-metadata-only` was
not recognized.

### Implementation Evidence

Changed behavior:

- Added `--identifier-metadata-only` to `scripts/run_paper_summary_zh_backfill.py`.
- The mode is mutually exclusive with `--enrich-doi-metadata` and
  `--existing-source-only`.
- The mode does not open an LLM client, does not call summary generation, does
  not write `summary_zh`, and does not fetch PDF/full-text.
- The selection was narrowed to identifier rows that are missing existing
  source text; generic metadata gaps are not enough to enter this source lane.
- The report now records `identifier_metadata_only`,
  `summary_generation_enabled`, `full_text_fetch_enabled`,
  `metadata_provider_misses`, `metadata_provider_errors`,
  `metadata_provider_timeouts`, `metadata_provider_rate_limits`,
  `metadata_provider_error_samples`, and `metadata_no_updates`.
- Added optional provider diagnostics to `src/data_agents/paper/enrichment.py`
  so OpenAlex, Crossref, Semantic Scholar, Unpaywall, and arXiv lookup
  exceptions can be counted by the lane while the aggregator remains
  non-throwing by default.

### Real Dry Runs And Write Runs

Initial broader metadata-only dry-run artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-identifier-metadata-only-dry-run-20260615.json
```

Result: selected `20`, processed `20`, wrote `0` summaries, enriched `3`, and
recorded `2` provider errors. This proved the report shape but also showed the
selection was too broad.

Initial broader metadata-only bounded write artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-identifier-metadata-only-bounded-20260615-workers-summary.json
```

Result: four workers selected `100`, processed `100`, wrote `0` summaries,
enriched `18`, attempted `0` full-text operations, and recorded `9` provider
errors. Direct DB inspection showed the `18` written rows already had usable
abstracts and summaries, so the selection was narrowed afterward. The writes
were useful metadata completion and were not reverted.

Corrected source-gap dry-run artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-identifier-metadata-only-sourcegap-dry-run-20260615.json
```

Result: selected `20`, processed `20`, wrote `0` summaries, enriched `0`,
recorded `20` no-update rows, `2` provider errors, `0` timeouts, and `0` rate
limits.

Corrected source-gap bounded write artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-identifier-metadata-only-sourcegap-bounded-20260615-workers-summary.json
```

Result: four workers selected `200`, processed `200`, wrote `0` summaries,
attempted `0` full-text operations, enriched `0`, recorded `200` no-update
rows, `1` bad DOI skip, `20` provider errors, `0` timeouts, and `0` rate
limits. Provider errors were Semantic Scholar 404s in the sampled rows.

Post-source-gap identifier audit:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-source-gap-audit-after-identifier-metadata-sourcegap-bounded-20260615.json
```

Result: source-gap counts stayed unchanged after the corrected source-gap
identifier run.

| Lane | After Fast Path | After Identifier Source-Gap Run |
| --- | ---: | ---: |
| `existing_source_summary_fast_path` | 699 | 699 |
| `identifier_metadata_enrichment` | 4,605 | 4,605 |
| `professor_page_full_text_acquisition` | 38 | 38 |
| `prof_page_only_title_parser_cleanup` | 11,603 | 11,603 |
| `review_only_residual` | 303 | 303 |

Interpretation: the sampled identifier rows did not have usable abstracts in
OpenAlex, Crossref, Semantic Scholar, Unpaywall, or arXiv metadata. They should
move to full-text slow-lane acquisition or source/parser repair; they must not
be repaired by direct LLM summary generation.

### GREEN Evidence

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/paper/test_enrichment.py \
  tests/data_agents/paper/test_crossref.py \
  tests/data_agents/paper/test_source_gap_audit.py \
  tests/scripts/test_run_paper_source_gap_audit.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  -q
```

Result: passed, `85 passed in 7.74s`.

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/paper/enrichment.py \
  scripts/run_paper_summary_zh_backfill.py \
  tests/data_agents/paper/test_enrichment.py \
  tests/data_agents/paper/test_crossref.py \
  tests/data_agents/paper/test_source_gap_audit.py \
  tests/scripts/test_run_paper_source_gap_audit.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py
```

Result: passed, `All checks passed!`.

Command:

```bash
openspec validate "paper-source-gap-remediation-lanes" --strict
```

Result: passed, `Change 'paper-source-gap-remediation-lanes' is valid`.

## Full-Text Slow Lane And Cleaning Gate Follow-Up

### Full-Text Slow Lane Evidence

Implemented `scripts/run_paper_full_text_source_lane.py` with bounded PDF/full
text fetching, failure buckets, checkpointing, and no summary writes.

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/paper/test_full_text_fetcher.py \
  tests/scripts/test_run_paper_full_text_source_lane.py \
  -q
```

Result: passed during the slice. The suite covers timeout, HTTP status, bad
content type, size cap, parse failure, duplicate content, fetched-but-no-usable
text, and usable abstract persistence without `summary_zh` writes.

Dry-run artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-full-text-source-lane-dry-run-short-timeout-20260615.json
```

Result: processed `5`, attempted `5`, fetched `1`, persisted `0` in dry-run,
failed `4`, recorded `4` timeouts, fetched `1` row with no usable text, and
wrote `0` summaries. This also verified the injected HTTP timeout fix.

### Cleaning Gate Root Cause

The real existing-source DeepSeek continuation exposed high rejection counts:
`189` selected, `138` processed, `26` written, `112` rejected, and `51`
skipped. Investigation found two code gaps:

- The judge parser could treat `INFORMATIVE, not BOILERPLATE` as
  `BOILERPLATE`.
- Even after parser repair, the second-stage judge was a strong gate. A real
  DeepSeek reproduction generated a substantive summary for
  `PAPER-256CE02E8CA4` and then returned raw judge verdict `BOILERPLATE`.

Fixes:

- `_parse_judge_verdict()` now scans verdict tokens in order, respects simple
  negation, and fails open for non-string provider output.
- `judge_summary_boilerplate()` is advisory: it rejects only when the LLM says
  `BOILERPLATE` and local low-information signals also match.
- Summary length gates are now `100` to `800` characters.
- Backfill reports include `summary_rejection_reason_counts`, and checkpoints
  include stable rejection reasons.

### Tests

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/paper/test_abstract_translator.py \
  tests/data_agents/paper/test_abstract_translator_boilerplate_judge.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  -q
```

Result: passed, `74 passed in 7.60s`.

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/paper/test_abstract_translator.py \
  tests/data_agents/paper/test_abstract_translator_boilerplate_judge.py \
  tests/data_agents/paper/test_full_text_fetcher.py \
  tests/scripts/test_run_paper_full_text_source_lane.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  -q
```

Result: passed after the final max-length adjustment, `141 passed in 35.19s`.

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/paper/abstract_translator.py \
  scripts/run_paper_summary_zh_backfill.py \
  tests/data_agents/paper/test_abstract_translator.py \
  tests/data_agents/paper/test_abstract_translator_boilerplate_judge.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py
```

Result: passed, `All checks passed!`.

### Real DeepSeek Verification

Post parser/report fix artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-post-gatefix-20260615-workers-summary.json
```

Result: four workers selected `80`, processed `56`, wrote `21`, rejected `35`,
and recorded `0` script-level errors. Reason counts were
`boilerplate_judge=29` and `translation_invalid_or_empty=6`, which exposed the
strong judge gap.

Post weak-judge artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-post-weakjudge-20260615-workers-summary.json
```

Result: four workers selected `40`, processed `20`, wrote `17`, rejected `3`,
and recorded `0` script-level errors. Reason counts were only
`translation_invalid_or_empty=3`; there were `0` `boilerplate_judge`
rejections.

Targeted max-800 retry artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-post-max800-retry-20260615.json
```

Result: reprocessed `3` rows that had failed because generated summaries were
slightly over the old length cap; wrote `3`, rejected `0`, errors `0`.

### Current Aggregate

Read-only database aggregate after this slice:

```json
{
  "active_papers": 40422,
  "summary_zh_present": 23764,
  "summary_zh_missing": 16658,
  "abstract_clean_present": 23338,
  "abstract_clean_missing": 17084
}
```

Post-cleaning source-gap audit artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-source-gap-audit-after-weakjudge-cleaning-20260615.json
```

Result: `17,187` source-gap rows remain. Lane counts: existing-source fast
path `638`, identifier metadata `4,605`, full-text acquisition `38`,
`prof_page_only` parser/title cleanup `11,603`, and review-only residual `303`.

Command:

```bash
openspec validate paper-source-gap-remediation-lanes --strict
```

Result: passed, `Change 'paper-source-gap-remediation-lanes' is valid`.

## Follow-Up Code/Data Cleanup After Source-Text Eligibility Drift

### Defect Class

The follow-up split two issues that were previously conflated:

- code-level drift between audit/source-gap classification and writer
  eligibility;
- true remaining data gaps where no usable source text is currently available.

The drift was caused by duplicated source-text quality logic. The audit counted
`paper_full_text.intro` and citation-like `abstract_clean` values as existing
source fast-path evidence in cases where the writer would not safely use them
as abstracts. This made the final residual report overstate directly cleanable
rows.

### Code Changes

- Added `src/data_agents/paper/source_text_quality.py` as the shared source
  text quality boundary.
- Updated `src/data_agents/paper/source_gap_audit.py` so
  `paper_full_text.intro` only supports summary generation when `summary_zh`
  is missing; it is not counted as a true abstract backfill source when the
  summary already exists.
- Updated `scripts/run_paper_summary_zh_backfill.py` so
  `paper_full_text.abstract` can backfill missing `abstract_clean` without
  regenerating an existing summary, and identifier metadata selection no longer
  treats `paper_full_text.intro` as a true abstract.
- Updated `scripts/run_paper_full_text_source_lane.py` to use the same source
  text quality helper before persisting source text.
- Added `scripts/run_paper_abstract_clean_quality_cleanup.py` to clear existing
  unusable `abstract_clean` values and demote affected `ready` rows to
  `partial`.

### RED/GREEN Evidence

Targeted regression cases were added for:

- intro-only rows with an existing summary are not audit fast-path rows;
- `paper_full_text.abstract` can backfill `abstract_clean` when a summary
  already exists;
- citation metadata is not usable source text;
- identifier metadata-only mode treats `paper_full_text.intro` as missing true
  abstract;
- existing summary rows are not regenerated when only `abstract_clean` is
  backfilled;
- dirty `abstract_clean` values are cleared and ready rows are demoted.

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/paper/test_source_gap_audit.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/scripts/test_run_paper_full_text_source_lane.py \
  tests/scripts/test_run_paper_abstract_clean_quality_cleanup.py \
  -q
```

Result: passed, `79 passed in 8.88s`.

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/paper/source_text_quality.py \
  src/data_agents/paper/source_gap_audit.py \
  scripts/run_paper_summary_zh_backfill.py \
  scripts/run_paper_full_text_source_lane.py \
  scripts/run_paper_abstract_clean_quality_cleanup.py \
  tests/data_agents/paper/test_source_gap_audit.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/scripts/test_run_paper_full_text_source_lane.py \
  tests/scripts/test_run_paper_abstract_clean_quality_cleanup.py
```

Result: passed, `All checks passed!`.

Command:

```bash
openspec validate "paper-source-gap-remediation-lanes" --strict
```

Result: passed, `Change 'paper-source-gap-remediation-lanes' is valid`.

### Follow-Up Data Runs

Initial existing-source write after the fast-path eligibility fix:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-after-abstract-fastpath-fix-write-20260615.json
```

Result: processed `13`, skipped `51`, wrote `1` summary, rejected `2`,
backfilled `10` `abstract_clean` values from full-text abstract evidence, and
recorded `0` row errors.

Identifier metadata-only follow-up after true-abstract selection fix:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-identifier-metadata-only-after-intro-selection-fix-20260615-workers-summary.json
```

Result: processed `5,069`, attempted metadata for `4,977`, persisted `11`
metadata updates, persisted `0` PDF URL upserts, recorded `4,966` no-update
rows, `93` bad DOI rows, `460` provider errors, `0` timeouts, `0` rate limits,
wrote `0` summaries, and recorded `0` row errors.

Dirty `abstract_clean` cleanup:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-abstract-clean-quality-cleanup-write-20260615.json
```

Result: scanned `23,359` active nonempty abstracts, cleared `59` unusable
abstracts, demoted `4` ready rows to partial, and recorded run id
`c755636d-1f2b-4bf4-94cd-173957678ae9`.

Existing-source write after dirty-abstract cleanup:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-after-abstract-clean-cleanup-20260615.json
```

Result: processed `5`, skipped `7`, wrote `1` summary, rejected `1`,
backfilled `3` `abstract_clean` values, and recorded `0` row errors.

Full-text follow-up after source-text quality sharing:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-full-text-after-selection-fixes-20260615-workers-summary.json
```

Result: processed `1,078`, attempted `1,078` fetches, fetched `488`, persisted
`4` usable full-text records, failed `590`, skipped `484` fetched rows with no
usable text, wrote `0` summaries, and recorded `0` row errors. Main failure
buckets were fetched-no-usable-text `484`, disallowed PDF content type `299`,
HTTP 403 `223`, timeout `13`, network `15`, HTTP 5xx `9`, PDF size cap `8`,
and parse failure `1`.

Existing-source write after full-text follow-up:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-after-full-text-selection-fixes-20260615.json
```

Result: processed `5`, skipped `7`, wrote `4` summaries, rejected `1`,
backfilled `3` `abstract_clean` values, and recorded `0` row errors.

Final single-row retry:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-final-single-retry-20260615.json
```

Result: processed `1`, wrote `0`, rejected `1` with
`translation_invalid_or_empty`. This is the only remaining existing-source
fast-path row.

### Final Live Checks

Final source-gap audit artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-source-gap-audit-final-after-code-data-gap-cleanup-20260615.json
```

Result: `15,753` source-gap rows remain. Lane counts are existing-source fast
path `1`, identifier metadata `5,122`, `prof_page_only` parser/title cleanup
`10,264`, full-text acquisition `63`, and review-only residual `303`.

Live aggregate query:

```text
running_paper_pipeline_runs: 0
active_papers: 39075
summary_zh_present: 23852
summary_zh_missing: 15223
abstract_clean_present: 23306
abstract_clean_missing: 15769
doi_missing_summary: 4535
doi_missing_abstract_clean: 5052
```

Live bad-abstract quality query:

```text
remaining_unusable_abstract_clean: 0
```

The net `abstract_clean` count decreased because the cleanup cleared `59`
unusable values and later source-backed runs backfilled `16` true abstracts.
This makes the database more honest even though the visible missing count
increased relative to the pre-cleanup false-positive count.

### Remaining Risks

- `prof_page_only` parser/title cleanup remains the largest residual lane at
  `10,264` rows and needs source acquisition or parser repair, not LLM
  fabrication.
- Identifier metadata residuals remain large at `5,122` rows; the latest
  provider run produced metadata but not usable abstracts for most rows.
- The full-text lane still reattempts many previously failed PDF URLs. A future
  improvement should add failure cooldown or explicit retry policy to avoid
  repeatedly fetching known 403/content-type/no-usable-text failures.
- Metadata reports currently count generic metadata updates together with
  source-gap-reducing updates. A future report improvement should separate
  source-text updates from venue/year/author-only updates.

## Final Source-Lane Completion Slice

### Code Gap Fixes

Changed behavior:

- `scripts/run_paper_summary_zh_backfill.py` now persists provider
  `pdf_url` candidates from `--identifier-metadata-only` into
  `paper_full_text` without fetching PDFs and without writing `summary_zh`.
  This lets the full-text slow lane pick up newly discovered PDF candidates in
  a later source-acquisition pass.
- `scripts/run_paper_title_enrichment_backfill.py` now supports
  `--worker-count` and `--worker-index` sharding. The shard predicate is based
  on `paper_id` and preserves the existing page-only selection boundary.

Regression commands:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_identifier_metadata_only_persists_pdf_url_for_slow_lane_without_fetch \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_identifier_metadata_only_persists_source_without_llm_or_summary \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_identifier_metadata_only_reports_provider_miss_without_summary \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_cli_uses_enriched_pdf_url_when_metadata_has_no_abstract \
  -q
```

Result: passed, `4 passed in 11.49s`.

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/scripts/test_run_paper_title_enrichment_backfill.py::test_build_select_sql_can_shard_prof_page_only_candidates_by_worker \
  tests/scripts/test_run_paper_title_enrichment_backfill.py::test_parse_args_validates_worker_shard_bounds \
  tests/scripts/test_run_paper_title_enrichment_backfill.py::test_build_select_sql_scopes_seed_to_page_only_verified_links \
  tests/scripts/test_run_paper_title_enrichment_backfill.py::test_main_plan_only_is_read_only_and_does_not_open_pipeline_run \
  -q
```

Result: passed, `4 passed in 9.22s`.

### Real Data Lane Runs

Source-gap audit before this final slice:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-source-gap-audit-start-continue-20260615.json
```

Result: `17,184` source-gap rows remained: existing-source fast path `635`,
identifier metadata `4,605`, full-text acquisition `38`, `prof_page_only`
parser/title cleanup `11,603`, and review-only residual `303`.

Existing-source final continuation:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-final-20260615-workers-summary.json
```

Result: four workers selected `122`, processed `71`, wrote `66`, rejected `5`,
skipped `51`, and recorded `0` row errors.

Conservative `prof_page_only` cache-only title repair:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-title-prof-page-only-cache-only-write-20260615.json
```

Result: processed `11,636` rows, canonicalized `155`, performed `152`
in-place updates, migrated `3` official professor-page links, merged `3`
page-only Papers, copied `154` enrichment records, and filtered common
implausible title/link pollution.

Capped primary full-text lane:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-full-text-primary-lane-capped-20260615-workers-summary.json
```

Result: processed `38`, fetched `9`, persisted `2`, failed `29`, recorded `2`
timeouts, `21` content-type rejections, `1` parse failure, `7`
fetched-but-no-usable-text residuals, and wrote `0` summaries.

Source-gap audit after existing/title/full-text source lanes:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-source-gap-audit-after-existing-title-fulltext-20260615.json
```

Result: `15,779` source-gap rows remained: existing-source fast path `572`,
identifier metadata `4,605`, full-text acquisition `34`, `prof_page_only`
parser/title cleanup `10,265`, and review-only residual `303`.

Existing-source summary after source lanes:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-after-source-lanes-20260615-workers-summary.json
```

Result: four workers selected `58`, processed `7`, wrote `5`, rejected `2`,
skipped `51`, and recorded `0` row errors.

Full identifier metadata-only bridge:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-identifier-metadata-only-full-bridge-20260615-workers-summary.json
```

Result: eight workers processed `4,573`, attempted provider metadata for
`4,482`, persisted `5` source updates, persisted `0` new PDF URL candidates,
wrote `0` summaries, recorded `92` bad DOI rows, `452` provider errors, and
`229` provider rate limits.

Existing-source summary after identifier metadata:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-after-identifier-full-20260615-workers-summary.json
```

Result: four workers selected `56`, processed `5`, wrote `2`, rejected `3`,
skipped `51`, and recorded `0` row errors.

Bounded live professor-page title resolver shard:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-title-prof-page-only-live-openalex-crossref-limit100-20260615-workers-summary.json
```

Result: processed `400`, resolved `2`, left `398` unresolved, migrated `2`
official professor-page links, merged `2` page-only Papers, copied `1`
enrichment record, and recorded `0` row errors. OpenAlex/Crossref title
resolution was miss/timeout heavy in this lane, so it was not scaled blindly.

Final `prof_page_only` plan audit:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-title-prof-page-only-plan-after-title-live-20260615.json
```

Result: `10,137` page-only rows remain in plan scope, including `10,065`
resolver candidates, `0` local implausible titles, `72` missing title/link
rows, and `81` unsafe-link rows.

Broad full-text residual pass:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-full-text-residual-20260615-workers-summary.json
```

Result: processed `1,067`, fetched `389`, persisted `12`, failed `678`,
recorded `50` timeouts, `266` content-type rejections, `9` size-cap
rejections, `1` parse failure, `377` fetched-but-no-usable-text residuals, and
wrote `0` summaries.

Existing-source summary after full-text residual:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-summary-existing-source-after-fulltext-residual-20260615-workers-summary.json
```

Result: four workers selected `66`, processed `15`, wrote `12`, rejected `3`,
skipped `51`, backfilled `7` `abstract_clean` values from full-text evidence,
and recorded `0` row errors.

### Pipeline-Run Closure

Four superseded full-text workers were closed as `partial` with
`run_scope.interruption_reason=superseded_by_primary_lane_id_file` and
checkpoint evidence `paper-full-text-primary-lane-ids-20260615.txt`.

Seven older stale Paper remediation runs were also closed as `partial` with
`run_scope.interruption_reason=stale_no_live_process_manual_closure`,
`error_summary.checkpoint_counts_unavailable=true`, and a live process check
showing no matching Paper cleanup processes.

Verification command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python - <<'PY'
import os, psycopg
conn = psycopg.connect(os.environ['DATABASE_URL'])
with conn.cursor() as cur:
    cur.execute("""
        select coalesce(run_scope->>'task','<missing>') as task, count(*)
        from pipeline_run
        where status = 'running'
          and coalesce(run_scope->>'task','') like 'paper%'
        group by 1
        order by 1
    """)
    rows = cur.fetchall()
    print(rows if rows else 'no running paper pipeline_run rows')
PY
```

Result: `no running paper pipeline_run rows`.

### Final Residual Audit

Final source-gap audit artifact:

```text
.agents/runs/paper-source-gap-remediation-lanes/paper-source-gap-audit-final-post-run-closure-20260615.json
```

Result: `15,763` source-gap rows remain. Lane counts are existing-source fast
path `572`, identifier metadata `4,590`, `prof_page_only` parser/title cleanup
`10,264`, full-text acquisition `34`, and review-only residual `303`.

Read-only active aggregate after run closure:

```text
active_papers: 39075
summary_zh_present: 23846
summary_zh_missing: 15229
abstract_clean_present: 23349
abstract_clean_missing: 15726
doi_missing_summary: 4541
doi_missing_abstract_clean: 5004
```

The remaining rows are not safe direct LLM-cleanable rows. They are dominated
by `prof_page_only` rows without usable source text, identifier rows where
providers returned no abstract or hit rate limits/errors, PDF/full-text
failures such as 403/content-type/timeout/no usable text, and review-only
residuals.

### Final Validation

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/scripts/test_run_paper_title_enrichment_backfill.py \
  tests/scripts/test_run_paper_full_text_source_lane.py \
  tests/scripts/test_run_paper_source_gap_audit.py \
  tests/data_agents/paper/test_source_gap_audit.py \
  tests/data_agents/paper/test_full_text_fetcher.py \
  -q
```

Result: passed, `163 passed in 36.38s`.

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  scripts/run_paper_summary_zh_backfill.py \
  scripts/run_paper_title_enrichment_backfill.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/scripts/test_run_paper_title_enrichment_backfill.py
```

Result: passed, `All checks passed!`.

Command:

```bash
openspec validate paper-source-gap-remediation-lanes --strict
```

Result: passed, `Change 'paper-source-gap-remediation-lanes' is valid`.
