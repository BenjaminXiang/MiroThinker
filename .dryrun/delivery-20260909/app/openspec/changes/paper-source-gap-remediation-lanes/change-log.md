# Change Log

## 2026-06-15

- Created the OpenSpec change to cover remaining Paper source gaps after
  `professor-dataset-candidate-generation`.
- Scoped the change to lane-based source remediation rather than direct LLM
  fabrication for rows without usable source text.
- Added requirements for read-only source-gap classification, existing-source
  summary fast path, identifier metadata enrichment, full-text slow lane,
  conservative `prof_page_only` repair, professor-seeded boundary preservation,
  and partial-run evidence.
- Added the initial read-only source-gap audit implementation and CLI. The
  audit assigns one primary lane per active Paper source-gap row, records
  secondary lanes, source buckets, sampled Paper ids, skip-reason counts, and
  deterministic selection hashes without writing database rows.
- Recorded the first compact `miroflow_real` baseline at
  `.agents/runs/paper-source-gap-remediation-lanes/paper-source-gap-audit-baseline-20260615.json`.
  It classified `17,320` active source-gap rows into `771`
  existing-source fast-path rows, `4,605` identifier metadata rows, `38`
  full-text acquisition rows, `11,603` `prof_page_only` parser/title cleanup
  rows, and `303` review-only residual rows.
- Added explicit existing-source summary fast-path mode to
  `run_paper_summary_zh_backfill.py`. `--existing-source-only` is mutually
  exclusive with DOI metadata enrichment and reports
  `source_acquisition_enabled=false`.
- Ran the existing-source fast path with eight DeepSeek workers. The run
  selected `272` rows, processed `221`, wrote `83` Chinese summaries, rejected
  `138`, skipped `51`, attempted `0` metadata/full-text source operations, and
  recorded `0` script-level row errors.
- Re-ran the compact source-gap audit after the fast path. Source-gap rows
  dropped from `17,320` to `17,248`; existing-source fast path dropped from
  `771` to `699`. Remaining source lanes are identifier metadata `4,605`,
  full-text acquisition `38`, `prof_page_only` parser/title cleanup `11,603`,
  and review-only residual `303`.
- Added an explicit identifier metadata source lane via
  `--identifier-metadata-only`. The mode is mutually exclusive with summary
  lanes, does not open an LLM client, does not write `summary_zh`, and reports
  bad DOI, provider miss, provider error, timeout, rate-limit, no-update, and
  usable-source persisted buckets.
- Added optional provider diagnostics to the Paper enrichment aggregator so
  per-source exceptions can be counted by the lane while enrichment remains
  non-throwing for callers. Crossref polite-pool `mailto` behavior remains
  covered by `tests/data_agents/paper/test_crossref.py`.
- Ran an initial broader metadata-only bounded write that processed `100` rows
  and filled metadata for `18` already source-backed rows without writing
  summaries. The selection was then narrowed to true source-gapped identifier
  rows so the lane measures source acquisition rather than generic metadata
  completion.
- Ran the corrected source-gap identifier lane on `200` rows. It processed all
  selected rows, wrote `0` summaries, attempted `0` full-text fetches, produced
  `0` usable source updates, recorded `200` no-update rows, `20` provider
  errors, `0` timeouts, and `0` rate limits. The post-run audit remained at
  `17,248` source-gap rows with identifier metadata `4,605`, which indicates
  the sampled identifier residuals need full-text slow-lane or source/parser
  repair rather than direct LLM summaries.
- Added a dedicated full-text slow-lane CLI and tests. The lane fetches bounded
  PDF/full-text sources, records timeout, HTTP status, content-type, size-cap,
  duplicate-content, parse-failure, and fetched-but-no-usable-text buckets, and
  persists only usable full-text evidence without writing `summary_zh`.
- Fixed a full-text fetcher timeout bug where injected HTTP client timeouts were
  overwritten by the default download timeout. The regression test now proves
  `_download_pdf()` does not override the injected client timeout.
- Audited the existing-source DeepSeek cleaning path after a 4-worker
  continuation run exposed high `rejected_boilerplate` counts. The root cause
  was a strong second-stage judge: DeepSeek could generate a substantive
  summary and then classify it as `BOILERPLATE`. The judge is now advisory:
  `BOILERPLATE` only rejects when local low-information signals also match.
- Weakened summary length gates for development cleaning: the minimum remains
  `100` Chinese characters to avoid too-short summaries, while the maximum is
  now `800` characters so slightly verbose but valid summaries are not rejected.
- Added `summary_rejection_reason_counts` and checkpoint rejection reasons for
  summary backfill runs. This makes parallel cleaning failures diagnosable
  instead of collapsing every failure into a single `summaries_rejected` count.
- Verified the weak judge with real DeepSeek runs. A post-weak-judge
  4-worker run selected `40` rows, processed `20`, wrote `17`, rejected `3`,
  and recorded `0` `boilerplate_judge` rejections. A targeted max-800 retry
  wrote `3/3` rows that had previously failed only because generated summaries
  were slightly over the old length cap.
- Final current aggregate after this slice: `40,422` active Papers,
  `23,764` with `summary_zh`, `16,658` still missing `summary_zh`,
  `23,338` with `abstract_clean`, and `17,084` still missing `abstract_clean`.
- Added a bridge from identifier metadata enrichment to the full-text slow
  lane: `--identifier-metadata-only` now persists provider `pdf_url` into
  `paper_full_text` when metadata exposes a PDF candidate, without fetching the
  PDF and without writing `summary_zh`.
- Added worker sharding to the professor-page title repair CLI so conservative
  title re-resolution can run in parallel over existing page-declared Paper
  rows without changing the professor-seeded discovery boundary.
- Ran a final existing-source fast-path continuation with four DeepSeek
  workers. It selected `122` rows, processed `71`, wrote `66` summaries,
  rejected `5`, skipped `51`, and recorded `0` row errors.
- Ran conservative `prof_page_only` cache-only repair over `11,636` rows. It
  canonicalized `155` rows, performed `152` in-place updates, migrated `3`
  official professor-page links, merged `3` page-only Papers, and rejected the
  common implausible title pollution classes. A follow-up plan audit shows
  `0` remaining implausible titles under the local guard, `72` missing
  title/link rows, and `81` unsafe-link rows.
- Ran the capped primary full-text lane over the `38` audited primary rows. It
  fetched `9`, persisted `2` usable source records, failed `29`, recorded `2`
  timeouts, `21` content-type rejections, `1` parse failure, `7`
  fetched-but-no-usable-text residuals, and wrote `0` summaries.
- Ran the full identifier metadata-only bridge with eight workers. It
  processed `4,573` rows, attempted provider metadata for `4,482`, persisted
  `5` source updates, wrote `0` summaries, recorded `92` bad DOI rows, `452`
  provider errors, and `229` provider rate limits.
- Ran a bounded live title resolver shard over `400` remaining professor-page
  rows. It resolved `2`, migrated `2` official professor-page links, merged
  `2` page-only Papers, and left the rest unresolved because OpenAlex/Crossref
  title resolution was dominated by misses, timeouts, and temporary provider
  disablement.
- Ran a broad full-text residual pass over `1,067` PDF/full-text candidate
  rows. It fetched `389`, persisted `12` usable source records, failed `678`,
  recorded `50` timeouts, `266` content-type rejections, `9` size-cap
  rejections, `377` fetched-but-no-usable-text residuals, and wrote `0`
  summaries.
- Re-ran existing-source summary after source lanes produced new text. The
  final post-full-text run selected `66` rows, processed `15`, wrote `12`
  summaries, rejected `3`, skipped `51`, and backfilled `7`
  `abstract_clean` values from full-text evidence.
- Closed four superseded full-text workers and seven older stale Paper
  remediation workers as `partial` with interruption evidence. A post-cleanup
  DB check reports no `running` Paper pipeline runs.
- Final source-gap audit after run closure reports `15,763` source-gap rows:
  existing-source summary fast path `572`, identifier metadata enrichment
  `4,590`, `prof_page_only` parser/title cleanup `10,264`,
  professor-page full-text acquisition `34`, and review-only residual `303`.
  A live active aggregate reports `39,075` active Papers, `23,846` with
  `summary_zh`, `15,229` missing `summary_zh`, `23,349` with
  `abstract_clean`, and `15,726` missing `abstract_clean`.
- Ran a follow-up code/data cleanup after separating two issues: code-level
  cleaning lane drift versus true remaining source gaps. The fix introduced a
  shared Paper source-text quality helper and aligned the source-gap audit,
  summary writer, full-text lane, and identifier metadata selection so
  `paper_full_text.intro` is not treated as a true abstract and citation or
  affiliation metadata is not counted as usable source text.
- Added `run_paper_abstract_clean_quality_cleanup.py` to clear existing dirty
  `abstract_clean` values instead of preserving them as false positives. The
  write run scanned `23,359` active nonempty abstracts, cleared `59` unusable
  values, demoted `4` `ready` rows to `partial`, and a follow-up live quality
  check reports `remaining_unusable_abstract_clean: 0`.
- Re-ran source-backed cleanup lanes after the code fixes. The existing-source
  fast path wrote `1` summary and backfilled `10` abstracts after the initial
  eligibility fix, then wrote `1` summary and backfilled `3` abstracts after
  dirty-abstract cleanup, and finally wrote `4` summaries and backfilled `3`
  abstracts after the full-text pass. The remaining single fast-path row was
  retried and rejected by the LLM output gate with
  `translation_invalid_or_empty`.
- Re-ran the identifier metadata-only lane with corrected true-abstract
  selection. Eight workers processed `5,069` rows, attempted provider metadata
  for `4,977`, persisted `11` metadata updates, wrote `0` summaries, recorded
  `93` bad DOI rows and `460` provider errors, and did not reduce the source
  gap because those updates did not provide usable abstracts.
- Re-ran the full-text source lane after source-text quality was shared across
  lanes. Four workers processed `1,078` rows, fetched `488`, persisted `4`
  usable full-text records, failed `590`, skipped `484` fetched rows with no
  usable text, and wrote `0` summaries. The largest failure buckets were
  fetched-no-usable-text `484`, disallowed PDF content type `299`, HTTP 403
  `223`, timeout `13`, network `15`, and PDF size cap `8`.
- Final live aggregate after the follow-up cleanup reports `39,075` active
  Papers, `23,852` with `summary_zh`, `15,223` still missing `summary_zh`,
  `23,306` with `abstract_clean`, `15,769` still missing `abstract_clean`,
  `4,535` DOI-backed rows still missing summary, and `5,052` DOI-backed rows
  still missing abstract. The source-gap audit now reports `15,753` rows:
  existing-source fast path `1`, identifier metadata `5,122`,
  `prof_page_only` parser/title cleanup `10,264`, full-text acquisition `63`,
  and review-only residual `303`.
