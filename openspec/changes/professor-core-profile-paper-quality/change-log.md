# Change Log

## 2026-06-13

- Created `professor-core-profile-paper-quality` after read-only review of the
  current Professor seed, paper ingest, quality gate, Admin API, and React
  Professor workbench code.
- Scoped the change to the official Professor seed/profile/paper chain and
  excluded hidden Professor-company roles from Professor core readiness.
- Added the initial proposal, design, specification, task list, source links,
  agent links, and acceptance placeholders.
- Completed task group 1 by adding a read-only baseline audit command, scenario
  records for Ahmed Elazab, Ding Wenbo, and pFedGPA, targeted tests, and real
  RED baseline evidence in the run verification log.
- Completed task group 2 by adding additive V042 schema storage for Professor
  profile sections and Paper merge aliases, plus thin Postgres storage helpers
  and targeted RED/GREEN tests.
- Completed task group 3 by adding research-overview extraction, injected
  English-to-Chinese translation support, Chinese validation, storage
  persistence wrapper, deterministic dry-run/write CLI, Ahmed real database
  dry-run evidence, navigation-noise regression coverage, and source-hash
  idempotency coverage.
- Partially completed task group 4 by wiring title-enrichment merge operations
  to durable `paper_merge_alias` rows and by making Professor output-summary
  inputs plus Admin Professor detail active paper lists resolve aliases and
  filter duplicate normalized title/year groups. The canonical homepage write
  path and real Ahmed/pFedGPA acceptance checks remain pending.
- Extended task group 4 coverage so homepage page-only reuse resolves
  `paper_merge_alias`, canonical paper links keep official Professor-page
  evidence, and the merge regression matrix includes Ahmed Elazab's duplicated
  Alzheimer paper title plus a generic duplicate title/year group. The full
  author-aware canonical homepage deduplication contract remains pending.
- Added pFedGPA arXiv coverage: provider fixture resolution returns
  `2409.05701` and an arXiv PDF URL, and the title-enrichment backfill forwards
  the arXiv id to canonical paper upsert. Real database pFedGPA acceptance
  remains pending in the release-evidence stage.
- Completed task group 4 by adding canonical Professor-homepage write-path
  reuse before paper upsert for DOI, arXiv id, and title/year/author matches.
  The path now keeps official Professor-page evidence attached to reused
  canonical paper ids instead of creating new page-only rows.
- Completed task group 5 by adding a seed-scoped Professor core profile-paper
  quality closure runner, replacing the admin homepage-ingest-only follow-up
  with full closure scheduling for successful unlimited full seed runs, blocking
  sample/limited ready promotion through the closure, and recording idempotent
  closure-stage failure evidence through existing `data_quality_flag` pipeline
  issues.
- Completed task group 6 by strengthening persisted Professor quality
  evaluation: `ready` now requires a 200-300 character Chinese
  `profile_summary`, non-repetitive summary content, durable Chinese research
  overview when official source text has one, no duplicate verified paper
  title/year groups, and `paper_summary` when verified papers exist. Added Ding
  Wenbo coverage that keeps hidden company roles out of Professor core
  readiness, and locked before/after quality distribution reporting for
  re-evaluation.
- Completed task group 7 by updating the Admin Professor detail workbench API
  to prefer persisted Chinese research-overview sections, return
  alias-resolved and deduplicated Paper rows with local id, quality,
  canonical-source, DOI/arXiv/PDF/external link fields, render Professor
  workbench paper titles as `/paper/<paper_id>` links, and generate chat local
  Paper citations through the configured admin/frontend base URL instead of the
  obsolete browse hash route.
- Completed release-evidence task group 8 except final all-case acceptance:
  applied V042 to `miroflow_real`, recorded plan-only and bounded dry-run
  reports, executed targeted write-mode backfills for Ahmed Elazab's Chinese
  research overview, Ahmed's duplicated Alzheimer paper, and the pFedGPA paper,
  fixed title-enrichment PDF URL persistence into `paper_full_text`, and added
  paper-detail alias resolution so `/api/paper/<old_id>` returns the canonical
  paper detail. The post-write audit now passes pFedGPA and Ahmed's duplicate
  check, but final acceptance remains blocked by Ahmed's missing
  `paper_summary`, Ding Wenbo's short `profile_summary`, and unresolved dataset
  gates.
- Completed final baseline-case acceptance for task 8.4. Targeted writes added
  Ahmed Elazab's `paper_summary`, expanded Ahmed's `profile_summary` to the
  200-300 character contract, merged Ahmed's remaining duplicated 2024
  Alzheimer paper page-only row, expanded Ding Wenbo's `profile_summary`, wrote
  Ding's Chinese `research_overview` section, wrote Ding's `paper_summary`, and
  re-evaluated both Professors to `ready`. The final case audit reports Ahmed
  Elazab, Ding Wenbo, and pFedGPA as `passing`; dataset-level gates remain
  blocked for broad backfill work outside the targeted acceptance cases.
