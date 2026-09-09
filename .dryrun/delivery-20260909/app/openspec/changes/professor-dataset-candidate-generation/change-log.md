# Change Log

## 2026-06-15

- Reopened the change for Paper source-gap remediation after the current
  aggregate still showed `36,000+` active Paper rows missing Chinese summaries
  or clean abstracts. The new slice targets source expansion first, not direct
  unsafe LLM fabrication.
- Added a cache-only title-resolution requirement for `prof_page_only` Paper
  remediation. The operator mode must consume existing title-resolution cache
  evidence, support `--paper-id-file` scoped runs, allow dry-run cache reads,
  and leave cache misses as unresolved rows without live provider searches.
- Implemented `--paper-id-file` and `--cache-only` in
  `run_paper_title_enrichment_backfill.py`. Cache-only dry-run can read the
  existing title-resolution cache but still writes no Paper rows, links,
  merge aliases, pipeline issues, or cache entries.
- Generated a current source-backed title-cache Paper id file with `6,726`
  candidate ids. Cache-only dry-run resolved `6,008` scoped rows and the write
  run migrated `6,037` verified Professor-Paper links, wrote `6,007` merge
  aliases, and marked `6,007` old page-only rows as merged.
- Fixed a discovered storage-boundary bug where
  `title_resolution:semantic_scholar` exceeded the `paper_full_text.source`
  `varchar(32)` limit. The script now writes shortened
  `title_res:<source>` labels and the failed Semantic Scholar row was retried
  successfully.
- Re-ran four parallel DeepSeek/DOI Paper summary workers after cache-only
  title remediation. The workers wrote `21` additional Chinese summaries,
  enriched `7` metadata rows, attempted `578` full-text enrichments, and
  recorded `0` identifier contradictions or script-level row errors.
- Final current aggregate after this slice: `41,876` active Paper rows,
  `11,372` with `summary_zh`, `30,504` still missing `summary_zh`, `30,717`
  still missing `abstract_clean`, and `2,231` active DOI rows still missing
  `summary_zh`. Remaining gaps are dominated by unresolved `prof_page_only`
  rows, DOI/full-text source failures, and a small set of clearly polluted DOI
  values such as combined DOI strings or truncated DOI prefixes.
- Added live resolver provider preflight support before task group 15: Crossref
  now reads contact metadata from environment variables instead of a hardcoded
  placeholder mailto, Semantic Scholar request helpers send the configured API
  key header when available, and Paper title enrichment can run with
  `--disable-semantic-scholar-title-search` while OpenAlex/Crossref-primary
  source acquisition proceeds.
- Recorded provider-preflight regression evidence without executing a live
  resolver shard: the targeted provider/title resolver/title-enrichment pytest
  suite passed with `125` tests, and Ruff passed on the touched files. The live
  data tasks 15.1-15.5 remain open.
- Added a conservative DOI pollution admission gate for the Paper cleaning
  layer. Nested DOI prefixes, separator-joined values, URL-tailed values,
  publisher stubs, and invalid DOI formats are now classified before DOI
  provider lookup. Paper summary backfill reports bad DOI-only rows via
  `metadata_enrichment_skipped_bad_doi` and bounded `bad_doi_samples` instead
  of sending those rows to OpenAlex/Crossref/Semantic Scholar/Unpaywall DOI
  lookup paths.
- Verified the DOI gate with targeted enrichment and Paper summary tests:
  `65 passed in 10.71s`; Ruff passed on the touched files. No live database
  mutation was executed for this admission-gate slice.
- Extended the DOI gate to the Paper title-enrichment existing-identifier
  shortcut. Polluted DOI values such as `10.1021/10.1002/poc.4450` are no
  longer promoted directly as trusted `doi_lookup` resolutions; the report now
  records `bad_doi_identifiers` and `bad_doi_samples`, while title resolver
  fallback remains available.
- Verified the title-enrichment shortcut gate with the focused RED/GREEN
  regression, the full title-enrichment script suite (`32 passed in 9.66s`),
  Ruff on the touched script/test files, and OpenSpec strict validation. No
  live database mutation was executed for this shortcut-gate slice.
- Completed the live Paper title resolver source-acquisition slice. Existing
  shard artifacts scoped `27,643` remaining `prof_page_only` missing-summary
  rows after cache-only remediation. The OpenAlex/Crossref-primary write run
  processed `27,507` scoped rows, resolved `16,114`, migrated `16,310`
  verified links, wrote `16,098` merge aliases, and recorded `0` script-level
  row errors.
- Re-ran Paper `summary_zh` backfill after live resolver source acquisition.
  The mixed DOI/full-text workers wrote `5,261` summaries but skipped `3,135`
  rows with no abstract and were closed as partial because PDF/full-text
  acquisition was the dominant bottleneck. A separate existing-abstract fast
  path then ran eight DeepSeek workers without DOI/PDF enrichment, processing
  `5,133` rows, writing `4,937` summaries, rejecting `196`, skipping `51`, and
  recording `0` script-level row errors.
- Final stable Paper aggregate after terminating stale mixed workers:
  `40,401` active Papers, `20,601` with `summary_zh`, `19,800` missing
  `summary_zh`, `20,517` with `abstract_clean`, `19,884` missing
  `abstract_clean`, `7,782` DOI-backed active rows still missing summary, and
  `11,619` `prof_page_only` rows still missing summary. Remaining gaps are now
  source-acquisition/parser-quality work rather than a safe direct LLM write
  lane.
- Split the remaining post-live summary cleanup into a bounded fast existing
  abstract rerun plus explicit one-pass identifier/no-abstract slow source
  batches. The fast rerun wrote `83` additional summaries from `262` residual
  rows. The slow batches covered `7,594` identifier-backed rows that lacked a
  usable abstract, enriched `4,244` metadata records and `354` full-text
  records, backfilled `152` abstracts, wrote `2,929` summaries, and recorded
  `0` script-level row errors.
- Recorded the latest Paper aggregate after the follow-up cleanup:
  `40,401` active Papers, `23,613` with `summary_zh`, `16,788` missing
  `summary_zh`, `23,884` with `abstract_clean`, `16,517` missing
  `abstract_clean`, and `4,772` DOI-backed active rows still missing summary.
  The remaining misses are explicitly classified as source gaps or quality
  rejections: `11,619` `prof_page_only` rows without identifier/abstract,
  `4,572` identifier-backed rows attempted once but still without usable
  abstract source, `272` existing-abstract rows rejected or skipped by summary
  quality checks, and `325` other missing-summary rows.

## 2026-06-14

- Created `professor-dataset-candidate-generation` to define the missing
  candidate-generation layer after `professor-dataset-quality-closure`.
- Scoped the change to four lane candidates: Chinese profile summaries,
  Chinese research overviews or source-hash-keyed translations, Professor
  paper summaries from deduplicated verified links, and duplicate Paper
  canonical merge plans.
- Preserved the Professor official profile -> verified paper boundary and kept
  provider-only author-name paper discovery plus hidden company/startup roles
  outside Professor core remediation.
- Implemented typed candidate models, validation helpers, provider-failure
  reporting, source-grounded profile/research/paper generation helpers, and
  conservative duplicate Paper merge planning.
- Added `candidate-dry-run` CLI mode with `--candidate-output`, preserved the
  existing closure `selection_hash` as `closure_selection_hash`, and added
  write-mode handoff support that injects `write_evidence_rows` into current
  bucket rows.
- Real `miroflow_real` baseline showed the current `professor` table does not
  contain `institution`, `department`, or `title`; the profile-summary loader
  was adjusted to avoid assuming those physical columns.
- Updated the candidate policy from strict pre-write blocking to relaxed
  LLM-first candidate reporting. Weak but usable output now needs status,
  quality flags, source confidence, write recommendation, and LLM self-check
  evidence instead of being broadly rejected before operator review.
- Recorded a new bounded `miroflow_real` relaxed dry-run artifact at
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-relaxed-bucket5.json`.
  The duplicate merge lane now emits five reviewable candidates with zero
  validation failures for the sampled bucket.
- Added the Professor candidate LLM provider adapter and made
  `candidate-dry-run` default to real provider mode. Deterministic candidate
  generation now requires explicit `--provider-mode deterministic`.
- Recorded
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-profile-bucket1.json`
  as the first default real-provider dry-run artifact. The current environment
  lacks `DEEPSEEK_API_KEY`, so it records `MissingLLMCredentials` as provider
  failure evidence instead of silently falling back to deterministic synthesis.
- Loaded `apps/miroflow-agent/.env` from the candidate dry-run CLI, documented
  `DEEPSEEK_API_KEY` in `.env.example`, and ignored the supported local
  `.deepseek_api_key` fallback file.
- Recorded bounded successful real-provider artifacts for profile summary
  synthesis, English research overview translation, and Professor paper summary
  synthesis:
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-profile-bucket1-dotenv.json`,
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-research-bucket12-translation-dotenv.json`,
  and
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-paper-summary-bucket1-dotenv.json`.
- Recorded duplicate Paper merge lane coverage at
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-duplicate-merge-bucket1-dotenv.json`;
  this lane remains deterministic/manual-review oriented and does not require
  a real LLM provider.
- Added bounded parallel candidate dry-run support. The CLI now accepts
  `--candidate-concurrency`, `--provider-max-concurrency`, and
  `--provider-min-interval-seconds`; parallel candidate generation uses worker
  connection factories and preserves the serial candidate evidence shape.
- Reused the existing provider rate limiter for Professor DeepSeek-backed
  candidate providers so provider pressure is bounded independently from row
  worker concurrency.
- Recorded a bounded parallel real-provider dry-run artifact at
  `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-parallel-llm-bucket20.json`.
  The run used worker concurrency `4`, provider max concurrency `4`, and
  provider interval `0.05s`; profile and research lanes produced `20/20`
  candidates, paper summary produced `11/20` candidates with `9`
  duplicate-link rejections, and duplicate merge produced `20/20` candidates.
- Recorded read-only full current-data audit artifacts:
  `.agents/runs/professor-dataset-candidate-generation/core-profile-paper-quality-audit-full-summary.json`,
  `.agents/runs/professor-dataset-candidate-generation/paper-bad-title-cleanup-readonly-full.txt`,
  and
  `.agents/runs/professor-dataset-candidate-generation/paper-table-field-coverage.json`.
  These show the current Paper dirty-data problem is systemic: `5,186`
  duplicate verified Paper title/year groups, `37,400+` verified linked Papers
  missing abstracts or Chinese summaries, and `1,597` implausible existing
  `paper.title_clean` rows found by the title guard. The full row-level bucket
  artifact was generated locally but is not tracked to avoid committing a
  production-data dump. No write-mode remediation was executed.
- Recorded a full read-only duplicate Paper merge candidate summary at
  `.agents/runs/professor-dataset-candidate-generation/duplicate-merge-candidate-dry-run-full-summary.json`.
  It found `5,125` DOI-match merge candidates from `5,186` duplicate groups:
  `4,891` ready auto-write candidates, `234` review-before-write candidates,
  and `61` ambiguous fuzzy rejections.
- Added a duplicate merge write-mode guard so `needs_review` or
  `review_before_write` candidate evidence becomes an unresolved write issue
  and does not insert `paper_merge_alias` rows.
- Ran the duplicate Paper merge write loop against matching dry-run evidence
  until no auto-write candidates remained. The loop attempted `7,533` merge
  writes, persisted `3,998`, recorded `0` failed writes, and stopped with
  `295` remaining review-only or ambiguous rows.
- Repaired an over-broad Paper title-quality heuristic that misclassified
  title-case technical paper titles containing `and` as author-prefixed
  citation records. The regression keeps real titles such as `Removing
  Interference and Recovering Content Imaginatively for Visible Watermark
  Removal` and `Human Obedience and Social Norm Adherence in Small Groups with
  Virtual Agents` eligible.
- Re-ran Paper title-enrichment plan-only evidence after the title-quality fix.
  The implausible-title count dropped to `1,342`, but broad bad-title cleanup
  remains read-only because the cleanup sample still contains plausible real
  titles.
- Ran parallel DeepSeek/DOI Paper summary enrichment with four workers. The
  batch processed `3,183` DOI-backed Paper rows and wrote `875` Chinese
  summaries without identifier contradictions or script-level row errors.
- Hardened the Paper summary worker-shard SQL by casting `hashtext(paper_id)`
  to `bigint` before `abs(...)`, avoiding the rare int32 minimum-value overflow
  case during parallel batch partitioning.
- Re-ran Professor paper-summary candidate generation after Paper enrichment.
  Only one Professor paper-summary candidate met the auto-write gate and was
  persisted with successful post-write verification; remaining rows are
  review-only, missing provenance, or blocked by duplicate verified Paper links.
- Added a follow-up research-overview source-cleaning slice after the full-run
  sample showed official Chinese source spans can still include teaching,
  recruitment, contact, link, publication-heading, award, and navigation noise.
  The new contract allows noisy Chinese source text to use an LLM cleaner before
  write-mode evidence while preserving source span/hash and review gates.
- Implemented the research-overview source-cleaning slice. Noisy Chinese
  research-overview sources now route through `generation_method=llm_cleaning`
  when a provider is available, teacher-maintained `.github.io` personal
  homepages are recursively crawled on the same host, and source spans that
  contain only navigation/link noise become explicit source-limitation
  rejections instead of fabricated candidates or provider failures.
