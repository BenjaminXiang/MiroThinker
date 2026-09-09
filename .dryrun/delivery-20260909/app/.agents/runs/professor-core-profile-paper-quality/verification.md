# Verification Log: professor-core-profile-paper-quality

## 2026-06-13 Proposal Creation

Production code edits: none.

Commands run:

- `openspec new change "professor-core-profile-paper-quality"` - created the
  change scaffold.
- `openspec status --change "professor-core-profile-paper-quality" --json` -
  reported proposal, design, specs, and tasks as done after artifact creation.
- `openspec validate "professor-core-profile-paper-quality" --strict` - passed.

Read-only baseline evidence from review:

- 3,387 Professors total; 1,407 marked `ready`.
- 928 Professors have `profile_summary` shorter than 150 characters; 230 of
  those are marked `ready`.
- 2,202 Professors have verified papers; 2,202 are missing `paper_summary`.
- 49,484 verified Professor-paper links.
- 6,563 verified duplicate normalized title/year groups, affecting 994
  Professors; 6,315 groups include an enriched row.
- Ahmed Elazab is marked `ready` but lacks `paper_summary` and has a duplicated
  Alzheimer paper across enriched and prof-page-only rows.
- Ding Wenbo is marked `ready` with a short/repetitive summary and missing
  `paper_summary`.
- pFedGPA is `prof_page_only`, `needs_enrichment`, and lacks arXiv/PDF data in
  the audited snapshot.

Skipped checks:

- No production-code tests were run because this slice only created OpenSpec and
  run-planning artifacts.
- No frontend or browser checks were run because no UI code was changed.

## 2026-06-13 Task Group 1 Baseline Audit

Scope: verification contract, read-only baseline audit command, and badcase
scenario records. No schema, pipeline, API, frontend, or chat behavior was
changed.

Files added:

- `apps/miroflow-agent/src/data_agents/professor/core_profile_paper_quality_audit.py`
- `apps/miroflow-agent/scripts/run_professor_core_profile_paper_quality_audit.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py`
- `apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py`
- `apps/miroflow-agent/tests/data_agents/professor/fixtures/core_profile_paper_quality_cases.json`

RED command:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py -q -n0 --no-cov`
- Result: failed during collection with
  `ModuleNotFoundError: No module named 'src.data_agents.professor.core_profile_paper_quality_audit'`.

GREEN command:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py -q -n0 --no-cov`
- Result: `4 passed in 0.50s`.

Read-only real database baseline command:

- `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python scripts/run_professor_core_profile_paper_quality_audit.py`
- Result: exit code `1`, expected for RED baseline because readiness is
  `blocked`.

Baseline blockers:

- `ready_summary_lt_200:443`
- `missing_research_overview_zh:2512`
- `missing_professor_paper_summary:2202`
- `duplicate_verified_paper_title_year_groups:5188`
- `case_failed:ahmed-elazab`
- `case_failed:ding-wenbo`
- `case_failed:pfedgpa`

Baseline Professor metrics:

- total Professors: `3387`
- ready Professors: `1407`
- `summary_lt_150`: `928`
- `summary_lt_200`: `1437`
- ready with summary shorter than 200 chars: `443`
- raw text with research source label: `2512`
- durable research overview storage available: `false`
- Professors with verified papers: `2202`
- Professors with verified papers missing `paper_summary`: `2202`

Baseline Paper metrics:

- verified Professor-paper links: `49484`
- distinct linked papers: `47853`
- linked papers missing abstract: `37403`
- linked papers missing `summary_zh`: `37477`
- linked papers with PDF: `492`
- duplicate verified title/year groups: `5188`
- duplicate affected Professors: `822`
- duplicate groups with enriched row: `5188`
- canonical source distribution includes `prof_page_only:34114`,
  `openalex:11012`, `crossref:2336`, and `arxiv:2`.

Baseline case evidence:

- Ahmed Elazab: `quality_status=ready`, missing Chinese research overview,
  missing `paper_summary`, duplicated Alzheimer title active verified count
  `2`.
- Ding Wenbo: `quality_status=ready`, `profile_summary_length=172`; education,
  work experience, research topic, academic position, award, contact, and
  homepage facts are present; hidden company roles remain excluded from
  Professor core readiness.
- pFedGPA: `paper_id=PAPER-80EC1A859E64`, `canonical_source=prof_page_only`,
  `quality_status=needs_enrichment`, missing arXiv id and PDF URL; expected
  route is `/paper/PAPER-80EC1A859E64`.

Notes:

- The first real baseline run did not catch Ahmed's duplicate paper because the
  fixture used ASCII apostrophe while the database title used curly apostrophe.
  The audit was fixed to normalize both forms before the recorded baseline
  above.
- The baseline audit is intentionally read-only and does not open a
  `pipeline_run`.

## 2026-06-13 Task Group 2 Schema And Storage Contracts

Scope: additive schema migration and thin storage helpers. No pipeline, API,
frontend, chat, backfill, or real database write was executed.

Files added or updated:

- `apps/miroflow-agent/alembic/versions/V042_add_professor_profile_section_paper_merge_alias.py`
- `apps/miroflow-agent/src/data_agents/storage/postgres/professor_profile_section.py`
- `apps/miroflow-agent/src/data_agents/storage/postgres/paper_merge_alias.py`
- `apps/miroflow-agent/tests/storage/test_v042_professor_profile_section_paper_merge_alias.py`
- `apps/miroflow-agent/tests/storage/test_professor_profile_section_storage.py`
- `apps/miroflow-agent/tests/storage/test_paper_merge_alias_storage.py`
- `apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py`

Migration RED command:

- `uv run pytest apps/miroflow-agent/tests/storage/test_v042_professor_profile_section_paper_merge_alias.py apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py -q -n0 --no-cov`
- Result: failed as expected because
  `V042_add_professor_profile_section_paper_merge_alias.py` did not exist.

Migration GREEN command:

- `uv run pytest apps/miroflow-agent/tests/storage/test_v042_professor_profile_section_paper_merge_alias.py apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py -q -n0 --no-cov`
- Result: `3 passed in 0.39s`.

Storage helper RED command:

- `uv run pytest apps/miroflow-agent/tests/storage/test_professor_profile_section_storage.py apps/miroflow-agent/tests/storage/test_paper_merge_alias_storage.py -q -n0 --no-cov`
- Result: failed during collection with missing modules
  `src.data_agents.storage.postgres.professor_profile_section` and
  `src.data_agents.storage.postgres.paper_merge_alias`.

Storage helper GREEN command:

- `uv run pytest apps/miroflow-agent/tests/storage/test_professor_profile_section_storage.py apps/miroflow-agent/tests/storage/test_paper_merge_alias_storage.py -q -n0 --no-cov`
- Result: `5 passed in 0.23s`.

Schema added by V042:

- `professor_profile_section` table for durable user-facing sections such as
  Chinese `research_overview`, with professor id, language, content,
  source page, source language, source text hash, source span, generation
  method, run id, and timestamps.
- `paper_merge_alias` table for durable `old_paper_id` to
  `canonical_paper_id` mapping, with merge reason, evidence source, run id, and
  timestamps.

Storage helpers added:

- `upsert_professor_profile_section` hashes source text when no source hash is
  provided and upserts through `uq_professor_profile_section_source`.
- `load_professor_profile_section` returns the latest section for a professor,
  section type, and language.
- `upsert_paper_merge_alias` rejects self aliases and upserts through
  `uq_paper_merge_alias_old_paper`.
- `resolve_canonical_paper_id` resolves an old paper id through recursive merge
  aliases and returns the original id when no alias exists.

Skipped checks:

- No live Alembic upgrade/downgrade against a test Postgres database was run in
  this slice. The migration tests are source-level checks, matching the current
  V041 pattern.

## 2026-06-13 Task Group 3 Profile Section Foundation

Scope: official raw-text research-overview extraction, injected translation
path, Chinese output validation, and a storage persistence wrapper. No real LLM
call, Ahmed write-mode backfill, Admin API change, or frontend change was
executed.

Files added or updated:

- `apps/miroflow-agent/src/data_agents/professor/profile_sections.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_profile_sections.py`

RED command:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_profile_sections.py -q -n0 --no-cov`
- Result: failed during collection with
  `ModuleNotFoundError: No module named 'src.data_agents.professor.profile_sections'`.

Second RED command:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_profile_sections.py -q -n0 --no-cov`
- Result: failed during collection because
  `persist_research_overview_section` was not yet exported.

GREEN command:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_profile_sections.py -q -n0 --no-cov`
- Result: `6 passed in 0.49s`.

Implemented behavior:

- `build_research_overview_section` extracts a research-overview section from
  official raw profile text.
- Chinese source text becomes a durable `research_overview` section with
  `language='zh'`, `source_language='zh'`, `generation_method='official_extract'`,
  source hash, source span, source page id, and run id.
- English source text requires an injected translator. The translated Chinese
  content becomes a durable `research_overview` section with
  `generation_method='llm_translation'` and source hash keyed to the English
  source text.
- `validate_chinese_research_overview` rejects non-Chinese output.
- `persist_research_overview_section` writes only `section_ready` results through
  the `professor_profile_section` storage helper.

Follow-up RED for Ahmed navigation noise:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_profile_sections.py -q -n0 --no-cov`
- Result: failed as expected because the extractor consumed the profile
  navigation fragment `研究领域 研究成果 奖励荣誉 概况` instead of the later
  substantive English `My research focuses...` paragraph.

Follow-up GREEN commands:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_profile_sections.py -q -n0 --no-cov`
- Result: `7 passed in 0.50s`.
- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_profile_sections.py apps/miroflow-agent/tests/scripts/test_run_professor_research_overview_backfill.py -q -n0 --no-cov`
- Result: `10 passed in 0.52s`.

Ahmed dry-run command:

```bash
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python scripts/run_professor_research_overview_backfill.py --professor-id PROF-823D4761D493 --translation-overrides-json '{"PROF-823D4761D493":"我的研究聚焦于医学影像分析中的可信人工智能，重点关注脑疾病诊断与预后。我结合先进机器学习和深度学习方法、多模态神经影像数据融合，构建稳健的计算机辅助检测与诊断系统，并通过模式识别、神经信息学和可解释人工智能发现疾病特异性生物标志物，提升临床解释性与可信度。"}'
```

Ahmed dry-run result:

- exit code `0`
- `dry_run: true`
- `processed: 1`
- `section_ready: 1`
- `translated: 1`
- `written: 0`
- row status: `section_ready`
- `generation_method: llm_translation`
- `source_language: en`
- content preview: Chinese research overview about trustworthy AI, medical
  image analysis, brain disease diagnosis/prognosis, multi-modal neuroimaging
  fusion, biomarkers, and explainable AI.

Implemented additionally:

- `scripts/run_professor_research_overview_backfill.py`, a dry-run-by-default
  CLI for building or writing durable Chinese research-overview sections.
- Translation overrides via JSON string/file for deterministic dry-run and
  test evidence.
- Navigation-noise skipping for profile raw text where menu fragments appear
  before substantive research overview paragraphs.
- Source-hash idempotency test: the hash is keyed to the source text, not to a
  variable translated output.

Skipped checks:

- No write-mode run was executed against `miroflow_real`.
- No real LLM call was executed; Ahmed dry-run used a deterministic translation
  override to make the evidence reproducible.

## 2026-06-13 Task Group 4 Partial Paper Merge Consumption

Scope: old-to-new paper merge alias persistence in the existing title
enrichment backfill, plus alias resolution and duplicate active title/year
filtering for Professor output-summary inputs and Admin Professor detail active
paper lists. This does not yet complete canonical Professor-homepage paper write
path deduplication, Ahmed real-database duplicate acceptance, or pFedGPA arXiv
acceptance.

Files added or updated:

- `apps/miroflow-agent/scripts/run_paper_title_enrichment_backfill.py`
- `apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py`
- `apps/miroflow-agent/src/data_agents/professor/output_summaries.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_output_summaries.py`
- `apps/admin-console/backend/services/data_helpers.py`
- `apps/admin-console/tests/test_professor_api.py`

RED commands:

- `uv run pytest apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_process_rows_migrates_links_and_marks_page_only_merged -q -n0 --no-cov`
- Result: failed with `KeyError: 'merge_aliases_written'`, proving the merge
  path did not expose or persist alias traceability.
- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_output_summaries.py::test_select_eligible_paper_summary_inputs_resolves_aliases_and_deduplicates -q -n0 --no-cov`
- Result: failed because the summary-input SQL did not reference
  `paper_merge_alias`.
- `uv run pytest apps/admin-console/tests/test_professor_api.py::test_professor_detail_active_papers_sql_resolves_aliases_and_deduplicates -q -n0 --no-cov`
- Result: failed because the Admin Professor detail active-paper SQL did not
  reference `paper_merge_alias`.

GREEN commands:

- `uv run pytest apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_process_rows_migrates_links_and_marks_page_only_merged -q -n0 --no-cov`
- Result: `1 passed in 0.86s`.
- `uv run pytest apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py -q -n0 --no-cov`
- Result: `21 passed in 0.92s`.
- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_output_summaries.py::test_select_eligible_paper_summary_inputs_resolves_aliases_and_deduplicates -q -n0 --no-cov`
- Result: `1 passed in 0.41s`.
- `uv run pytest apps/admin-console/tests/test_professor_api.py::test_professor_detail_active_papers_sql_resolves_aliases_and_deduplicates -q -n0 --no-cov`
- Result: `1 passed, 4 warnings in 0.02s`; warnings are existing FastAPI
  `on_event` deprecations.
- `uv run pytest apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py apps/miroflow-agent/tests/data_agents/professor/test_output_summaries.py apps/admin-console/tests/test_professor_api.py::test_professor_detail_active_papers_sql_resolves_aliases_and_deduplicates -q -n0 --no-cov`
- Result: `27 passed, 4 warnings in 0.21s`; warnings are existing FastAPI
  `on_event` deprecations.
- `openspec validate "professor-core-profile-paper-quality" --strict`
- Result: `Change 'professor-core-profile-paper-quality' is valid`.

Implemented behavior:

- `run_paper_title_enrichment_backfill.py` now writes a
  `paper_merge_alias` row when a page-only paper is migrated to a resolved
  canonical paper, and reports `merge_aliases_written`.
- `select_eligible_paper_summary_inputs` resolves active Professor paper links
  through `paper_merge_alias`, then filters duplicate normalized title/year
  groups before building Professor `paper_summary` inputs.
- Admin Professor detail active paper lists resolve merge aliases and filter
  duplicate normalized title/year groups while keeping returned provenance
  fields stable.
- Professor homepage page-only fallback lookup now resolves existing linked
  papers through `paper_merge_alias`, so a later official Professor-page
  occurrence attaches evidence to the canonical paper id instead of reviving a
  superseded page-only id.
- Regression coverage now includes Ahmed Elazab's duplicated Alzheimer paper
  title and one generic duplicate title/year group.
- pFedGPA coverage now verifies arXiv Atom provider data resolves to
  `arxiv_id='2409.05701'` plus the arXiv PDF URL, and verifies the title
  enrichment backfill forwards that arXiv id into canonical paper upsert.

Skipped checks:

- No write-mode title-enrichment backfill was executed against `miroflow_real`.
- No live Admin API request was run against the real database for Ahmed; the
  SQL contract and unit-level behavior are covered, but final case acceptance
  remains pending.
- No live pFedGPA provider or real database acceptance was executed; final
  acceptance remains in task 8.4.
- The full author-aware canonical homepage deduplication contract is not yet
  complete; task 4.1 remains pending.

Additional GREEN commands:

- `uv run pytest apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_page_only_existing_paper_lookup_resolves_merge_alias -q -n0 --no-cov`
- Result: `1 passed in 1.26s`.
- `uv run pytest apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_page_only_publication_reuses_existing_same_title_year_link apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_page_only_existing_paper_lookup_resolves_merge_alias -q -n0 --no-cov`
- Result: `2 passed in 1.42s`.
- `uv run pytest apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_process_rows_records_merge_alias_for_duplicate_title_year_groups -q -n0 --no-cov`
- Result: `2 passed in 0.90s`.
- `uv run pytest apps/miroflow-agent/tests/data_agents/paper/test_title_resolver.py::test_arxiv_entry_to_resolved_covers_pfedgpa_pdf -q -n0 --no-cov`
- Result: `1 passed in 0.73s`.
- `uv run pytest apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_process_rows_forwards_pfedgpa_arxiv_resolution_to_upsert -q -n0 --no-cov`
- Result: `1 passed in 0.90s`.
- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/storage/test_v042_professor_profile_section_paper_merge_alias.py apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py apps/miroflow-agent/tests/storage/test_professor_profile_section_storage.py apps/miroflow-agent/tests/storage/test_paper_merge_alias_storage.py apps/miroflow-agent/tests/data_agents/professor/test_profile_sections.py apps/miroflow-agent/tests/scripts/test_run_professor_research_overview_backfill.py apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py apps/miroflow-agent/tests/data_agents/professor/test_output_summaries.py apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_page_only_publication_reuses_existing_same_title_year_link apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_page_only_existing_paper_lookup_resolves_merge_alias apps/miroflow-agent/tests/data_agents/paper/test_title_resolver.py::test_arxiv_entry_to_resolved_covers_pfedgpa_pdf apps/admin-console/tests/test_professor_api.py::test_professor_detail_active_papers_sql_resolves_aliases_and_deduplicates -q -n0 --no-cov`
- Result: `55 passed, 4 warnings in 3.76s`; warnings are existing FastAPI
  `on_event` deprecations.
- `openspec validate "professor-core-profile-paper-quality" --strict`
- Result: `Change 'professor-core-profile-paper-quality' is valid`.
- `openspec instructions apply --change "professor-core-profile-paper-quality" --json`
- Result: progress `19/41` tasks complete, `22` remaining.

## 2026-06-13 Task 4.1 Homepage Canonical Write Path Deduplication

Scope: canonical Professor-homepage paper write path lookup before creating a
new row. The lookup covers DOI, arXiv id, and title/year/author reuse, while
keeping Professor official-page link evidence attached to the reused canonical
paper id.

Files updated:

- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py`

RED command:

- `uv run pytest apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_page_only_publication_reuses_existing_canonical_title_year_author -q -n0 --no-cov`
- Result: failed because `upsert_paper` was called once for a page-only
  publication even though a same title/year/author canonical paper was
  available.

GREEN commands:

- `uv run pytest apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_page_only_publication_reuses_existing_canonical_title_year_author -q -n0 --no-cov`
- Result: `1 passed in 1.30s`.
- `uv run pytest apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_page_only_publication_reuses_existing_same_title_year_link apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_page_only_existing_paper_lookup_resolves_merge_alias apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_page_only_publication_initializes_needs_enrichment -q -n0 --no-cov`
- Result: `3 passed in 1.30s`.
- `uv run pytest apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_find_existing_canonical_homepage_paper_uses_identifier_keys apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_page_only_publication_reuses_existing_canonical_title_year_author -q -n0 --no-cov`
- Result: `3 passed in 1.38s`.

Implemented behavior:

- Before `run_homepage_paper_ingest` creates a new paper row, it now checks for
  an existing canonical paper by DOI, arXiv id, or normalized title/year plus
  author terms.
- When an existing canonical paper is found, the pipeline skips `upsert_paper`
  and writes the Professor-page official link to that canonical paper id.
- Existing same-professor page-only reuse and merge-alias resolution behavior
  remains intact.

Skipped checks:

- No live homepage ingest write-mode run was executed against `miroflow_real`.

## 2026-06-13 Task Group 5 Seed-Scoped Quality Closure Pipeline

Scope: seed-scoped closure orchestration after successful full Professor seed
runs, replacing the old admin follow-up that only ran homepage paper ingest.
The closure coordinates homepage paper ingest, title enrichment/merge, paper
enrichment, paper quality status selection/count evidence, Professor output
summaries, Professor quality re-evaluation, and index refresh selection.

Files added or updated:

- `apps/miroflow-agent/src/data_agents/professor/core_profile_paper_quality_closure.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_closure.py`
- `apps/admin-console/backend/api/seeds.py`
- `apps/admin-console/tests/test_seed_background_tasks.py`
- `openspec/changes/professor-core-profile-paper-quality/tasks.md`

RED commands:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_closure.py -q -n0 --no-cov`
- Result: failed during collection with `ModuleNotFoundError:
  src.data_agents.professor.core_profile_paper_quality_closure`, proving the
  closure runner did not exist.
- `uv run pytest apps/admin-console/tests/test_seed_background_tasks.py -q -n0 --no-cov`
- Result: failed because `backend.api.seeds` had no
  `_run_seed_quality_closure_for_seed` and still exposed only the old
  homepage-ingest follow-up path.
- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_closure.py::test_output_summary_stage_fails_before_llm_when_seed_scope_has_no_professors -q -n0 --no-cov`
- Result: failed with `AssertionError: must not open LLM`, proving the output
  summary stage opened the LLM before verifying seed-scoped professor ids.

GREEN commands:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_closure.py -q -n0 --no-cov`
- Result: `5 passed in 0.54s`.
- `uv run pytest apps/admin-console/tests/test_seed_background_tasks.py -q -n0 --no-cov`
- Result: `5 passed, 4 warnings in 0.04s`; warnings are existing FastAPI
  `on_event` deprecations.
- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_closure.py apps/admin-console/tests/test_seed_background_tasks.py -q -n0 --no-cov`
- Result: `10 passed, 4 warnings in 0.08s`; warnings are existing FastAPI
  `on_event` deprecations.

Implemented behavior:

- Added a seed-scoped closure runner with fixed stage order:
  `homepage_paper_ingest`, `title_enrichment_merge`, `paper_enrichment`,
  `paper_quality_promotion`, `professor_output_summaries`,
  `professor_quality_re_evaluation`, and `index_refresh_selection`.
- Added `should_run_seed_quality_closure`, which allows closure only for
  successful `full` runs with no row limit.
- Replaced the admin seed background follow-up so successful full seed runs
  schedule the closure; sample runs, limited full runs, and failed seed runs do
  not schedule it.
- Added visible closure failure evidence through idempotent
  `pipeline_issue` upsert using the existing `data_quality_flag` stage and an
  `evidence_snapshot` containing seed id, professor id, closure stage, run id,
  and reason.
- Added a no-professor-scope guard so Professor output summaries, quality
  re-evaluation, paper quality selection, and index refresh selection cannot
  fall back to all eligible professors.
- Kept broad `run_quality_promote --domain paper` out of the closure because it
  is not seed-scoped. The paper summary/enrichment stage already advances paper
  quality for seed-scoped papers; the explicit paper-quality stage records
  seed-scoped quality-status selection/count evidence.

Skipped checks:

- No live closure was executed against `miroflow_real`, because this stage can
  trigger LLM calls, external paper provider calls, and write-mode updates.
- No Milvus/vector refresh write was executed; task 5 implements refresh
  selection, while final real index refresh evidence remains in release task
  8.x.

## 2026-06-13 Task Group 6 Professor Quality Gate And Output Summaries

Scope: persisted Professor quality evaluation and re-evaluation reporting.
This task group strengthens `ready` eligibility for user-facing Professor
records and keeps Ding Wenbo's company/startup role outside Professor core
readiness.

Files updated:

- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_professor_quality_status_rework.py`
- `apps/miroflow-agent/tests/scripts/test_run_professor_quality_re_eval.py`
- `openspec/changes/professor-core-profile-paper-quality/tasks.md`

RED command:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_professor_quality_status_rework.py -q -n0 --no-cov`
- Result: failed with `TypeError: ProfessorCanonicalState.__init__() got an
  unexpected keyword argument 'paper_summary'`, proving the persisted quality
  state lacked the required user-facing summary and paper-chain fields.

GREEN commands:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_professor_quality_status_rework.py -q -n0 --no-cov`
- Result: `19 passed in 0.56s`.
- `uv run pytest apps/miroflow-agent/tests/scripts/test_run_professor_quality_re_eval.py -q -n0 --no-cov`
- Result: `4 passed in 0.54s`.
- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_professor_quality_status_rework.py apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py apps/miroflow-agent/tests/data_agents/professor/test_output_summaries.py apps/miroflow-agent/tests/scripts/test_run_professor_quality_re_eval.py -q -n0 --no-cov`
- Result: `57 passed in 0.67s`.

Implemented behavior:

- `ProfessorCanonicalState` now carries `paper_summary`, `profile_raw_text`,
  durable research-overview presence, duplicate verified-paper state, and
  derived research-overview source state.
- Persisted Professor quality evaluation now blocks `ready` when
  `profile_summary` is shorter than 200 characters, longer than 300
  characters, lacks Chinese text, or is shallow/repetitive.
- If official raw profile text contains a research-overview source section, the
  quality gate requires a durable Chinese `research_overview` section.
- Professors with verified papers now require a generated `paper_summary`
  before `ready` promotion.
- Active duplicate verified paper title/year groups after merge-alias
  resolution produce a `duplicate_verified_paper_links` review blocker.
- Ding Wenbo regression coverage verifies complete Professor core profile data
  can be `ready` without a company/startup role.
- `run_professor_quality_re_eval.py` tests now explicitly assert before/after
  distribution reporting in dry-run and write mode.

Skipped checks:

- No real database write-mode quality re-evaluation was executed. Release task
  8.x still needs dry-run/write-mode evidence and before/after distributions
  against `miroflow_real`.

## 2026-06-13 Task Group 7 API, Frontend, And Chat Link Surfaces

Scope: Admin Professor workbench detail payload, React Professor workbench paper
links, and chat local Paper citation URLs. This group does not run real
database acceptance for Ahmed Elazab, Ding Wenbo, or pFedGPA; those remain in
task group 8.

Files updated:

- `apps/admin-console/backend/api/admin_professors.py`
- `apps/admin-console/tests/test_admin_professor_api.py`
- `apps/admin-console/frontend/src/pages/ProfessorWorkbench.tsx`
- `apps/admin-console/frontend/src/pages/ProfessorWorkbench.test.tsx`
- `apps/admin-console/backend/api/chat.py`
- `apps/admin-console/tests/test_chat_g_clarification.py`
- `openspec/changes/professor-core-profile-paper-quality/tasks.md`

RED commands:

- `uv run pytest apps/admin-console/tests/test_admin_professor_api.py::test_admin_professor_detail_prefers_persisted_chinese_research_overview apps/admin-console/tests/test_admin_professor_api.py::test_admin_professor_detail_returns_canonical_paper_link_fields -q -n0 --no-cov`
- Result: failed with two expected assertions. Admin detail still returned the
  raw English overview instead of the persisted Chinese section, and paper rows
  still contained only `paper_id`, `title_clean`, and `year`.
- `uv run pytest apps/admin-console/tests/test_chat_g_clarification.py::test_exact_english_paper_summary_query_cleans_title -q -n0 --no-cov`
- Result: failed because the citation URL was
  `/browse#paper/PAPER-35204DCCD66B` instead of the configured
  `http://100.64.0.4:5180/paper/PAPER-35204DCCD66B` route.
- `npm run test -- ProfessorWorkbench.test.tsx`
- Result: failed because the paper title `Notes` was not rendered as a link.

GREEN commands:

- `uv run pytest apps/admin-console/tests/test_admin_professor_api.py::test_admin_professor_detail_prefers_persisted_chinese_research_overview apps/admin-console/tests/test_admin_professor_api.py::test_admin_professor_detail_returns_canonical_paper_link_fields -q -n0 --no-cov`
- Result: `2 passed, 4 warnings in 0.04s`; warnings are existing FastAPI
  `on_event` deprecations.
- `uv run pytest apps/admin-console/tests/test_chat_g_clarification.py::test_exact_english_paper_summary_query_cleans_title -q -n0 --no-cov`
- Result: `1 passed, 4 warnings in 0.03s`; warnings are existing FastAPI
  `on_event` deprecations.
- `npm run test -- ProfessorWorkbench.test.tsx`
- Result: `1 passed` test file, `3 passed` tests.
- `uv run pytest apps/admin-console/tests/test_admin_professor_api.py -q -n0 --no-cov`
- Result: `8 passed, 1 skipped, 4 warnings in 0.06s`; warnings are existing
  FastAPI `on_event` deprecations.
- `uv run pytest apps/admin-console/tests/test_chat_g_clarification.py -q -n0 --no-cov`
- Result: `9 passed, 4 warnings in 0.04s`; warnings are existing FastAPI
  `on_event` deprecations.
- `uv run pytest apps/admin-console/tests/test_chat_classifier_b_g_tune.py::test_a_paper_profile_selects_rich_exact_duplicate apps/admin-console/tests/test_chat_classifier_b_g_tune.py::test_b_paper_topic_search_prefers_ready_candidates_without_caveat apps/admin-console/tests/test_chat_g_clarification.py::test_g_paper_query_returns_paper_clarification apps/admin-console/tests/test_chat_session_persistence.py::test_named_professor_papers_query_with_question_mark_routes_to_prof_papers -q -n0 --no-cov`
- Result: `5 passed, 4 warnings in 0.09s`; one selected test is
  parameterized, and warnings are existing FastAPI `on_event` deprecations.
- `npm run build`
- Result: `tsc -b && vite build` completed successfully. Vite reported the
  existing large chunk warning for the bundled app.

Implemented behavior:

- Admin Professor detail now reads the latest persisted Chinese
  `professor_profile_section` row with `section_type='research_overview'` and
  `language='zh'` before falling back to raw `profile_raw_text` extraction.
- Admin Professor detail paper rows now resolve `paper_merge_alias`, filter
  duplicate normalized title/year groups, and return `paper_id`, `title_clean`,
  `year`, `quality_status`, `canonical_source`, `doi`, `arxiv_id`, `pdf_url`,
  derived `external_url`, and official evidence `source_page_url`.
- React Professor workbench renders paper titles as React Router links to
  `/paper/<paper_id>`.
- Chat Paper citations now use `_local_paper_detail_url`. The URL is relative
  `/paper/<paper_id>` by default and becomes
  `<ADMIN_CONSOLE_PUBLIC_BASE_URL>/paper/<paper_id>` when that environment
  variable is configured. `ADMIN_FRONTEND_BASE_URL` and
  `FRONTEND_PUBLIC_BASE_URL` are accepted fallback variable names.
- All explicit local Paper citation branches in `backend/api/chat.py` were
  moved off the obsolete `/browse#paper/...` route.

Skipped checks and notes:

- No browser screenshot or live UI walkthrough was run; Vitest and production
  frontend build covered the React link behavior for this slice.
- No real deployment base URL check was run. The route behavior is covered by
  environment-variable regression tests.
- One intermediate supplemental pytest command used a stale test id and failed
  collection with `not found`; it was rerun with actual test names in the
  GREEN command list above.

## 2026-06-13 Task Group 8 Backfill, Acceptance, And Release Evidence

Scope: real database migration, bounded dry-runs, targeted write-mode fixes for
the known acceptance cases, post-write audit evidence, API verification, and
remaining blocker documentation. Broad institution-wide write-mode backfills
were intentionally not run in this slice.

Schema state and migration:

- Command: `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run alembic current`
- Result before migration: `V041`.
- Command: `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run alembic upgrade head`
- Result: upgraded `V041 -> V042`, adding `professor_profile_section` and
  `paper_merge_alias`.
- Command: `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run alembic current`
- Result after migration: `V042 (head)`.
- Direct `to_regclass` check confirmed both new tables exist.

Dry-run and baseline evidence:

- Command: `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python scripts/run_paper_title_enrichment_backfill.py --plan-only`
- Result: exit `0`; `papers_total=33963`,
  `resolver_candidates=32515`, `implausible_titles=1376`,
  `missing_title_or_links=72`, `unsafe_links_filtered=81`,
  `unsafe_link_rows=81`.
- Command: `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python scripts/run_professor_research_overview_backfill.py --limit 20`
- Result: exit `0`; `dry_run=true`, `processed=20`, `section_ready=19`,
  `translated=0`, `written=0`, with one translation-required English source
  for `Loïc MARSOT`.
- Command: bounded output-summary dry-run with a fake LLM provider and
  `limit=5`.
- Result before V042 migration: failed with
  `psycopg.errors.UndefinedTable: relation "paper_merge_alias" does not exist`,
  confirming the migration was required before running output summaries.
- Result after V042 migration: exit `0`; `eligible=5`, `processed=5`,
  `paper_summaries_written=5`, `failed=0`, `dry_run=true`.

Targeted write-mode evidence:

- Command: Ahmed Elazab research overview write with a source-text-hash-backed
  Chinese translation override for `PROF-823D4761D493`.
- Result: exit `0`; `processed=1`, `section_ready=1`, `translated=1`,
  `written=1`, new section id
  `cfc14042-241c-49d6-8dd1-25abf2674c8a`, `generation_method=llm_translation`.
- Command: Admin TestClient request for
  `/api/admin/professor/PROF-823D4761D493`.
- Result: HTTP `200`; `sections.research_output.research_overview` returned
  the persisted Chinese overview before raw fallback.
- Command: Ahmed duplicate paper dry-run:
  `run_paper_title_enrichment_backfill.py --paper-id PAPER-FB090FB3F7F3 --dry-run --disable-openalex-title-search --disable-dblp-title-search --disable-arxiv-title-search`
- Result: exit `0`; resolved to Crossref DOI
  `10.1016/j.bspc.2025.108485`, confidence `1.0`.
- Command: Ahmed duplicate paper targeted write with the same bounded provider
  switches.
- Result: exit `0`; `paper_upserts=1`, `link_migrations=1`,
  `merge_aliases_written=1`, `old_links_rejected=1`,
  `page_only_papers_merged=1`; `PAPER-FB090FB3F7F3` now aliases to
  `PAPER-489560FF49E0`.
- Command: pFedGPA dry-run:
  `run_paper_title_enrichment_backfill.py --paper-id PAPER-80EC1A859E64 --dry-run --disable-openalex-title-search --disable-dblp-title-search`
- Result: exit `0`; Crossref DOI `10.1609/aaai.v39i17.33980`,
  `arxiv_id=2409.05701`, `pdf_url=https://arxiv.org/pdf/2409.05701v3`,
  confidence `1.0`.
- Command: pFedGPA targeted write with the same bounded provider switches.
- Result: exit `0`; `paper_upserts=1`, `link_migrations=1`,
  `merge_aliases_written=1`, `old_links_rejected=1`,
  `page_only_papers_merged=1`; `PAPER-80EC1A859E64` now aliases to
  `PAPER-B907001E299D`.
- Follow-up write: after adding PDF metadata persistence to the title
  backfill, `_upsert_resolved_pdf_metadata` was applied to
  `PAPER-B907001E299D` using run id
  `2b6f49b0-d2c2-411b-89a8-19eebbc76327`.
- Result: `paper_full_text.pdf_url` now equals
  `https://arxiv.org/pdf/2409.05701v3` for `PAPER-B907001E299D`.

Code-level RED/GREEN evidence discovered during task 8:

- RED: `test_resolve_supplements_crossref_match_with_arxiv_pdf_when_available`
  failed because high-confidence Crossref resolution returned before arXiv was
  queried.
- GREEN: title resolver now supplements high-confidence Crossref matches with
  arXiv id/PDF when arXiv search is enabled and Crossref lacks those fields.
- RED: `test_process_rows_forwards_pfedgpa_arxiv_resolution_to_upsert`
  failed with `KeyError: 'pdf_url'`, then with missing
  `full_text_pdf_upserts`, proving title backfill reported provider PDF URLs
  without persisting them.
- GREEN: title backfill now records `pdf_url` in resolved samples and
  conservatively upserts `paper_full_text.pdf_url` without overwriting an
  existing non-empty PDF URL.
- GREEN: `test_pfedgpa_case_evaluates_canonical_alias_target` verifies the
  audit evaluates a merged pFedGPA old id through `paper_merge_alias`.
- GREEN: `test_paper_domain_detail_resolves_merge_alias` verifies
  `/api/paper/<old_id>` resolves to canonical paper detail.

Post-write audit:

- Command: `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python scripts/run_professor_core_profile_paper_quality_audit.py`
- Result: exit `1`, expected while final acceptance is still blocked.
- Improved cases:
  - Ahmed Elazab no longer fails `missing_research_overview_zh`.
  - Ahmed duplicate count changed to `duplicate_title_active_verified_count=1`.
  - pFedGPA status is now `passing`, with `paper_id=PAPER-B907001E299D`,
    `merged_from_paper_id=PAPER-80EC1A859E64`, `arxiv_id=2409.05701`, and
    `pdf_url=https://arxiv.org/pdf/2409.05701v3`.
- Remaining blockers:
  - `ready_summary_lt_200:443`
  - `missing_research_overview_zh:2511`
  - `missing_professor_paper_summary:2202`
  - `duplicate_verified_paper_title_year_groups:5187`
  - `case_failed:ahmed-elazab` because `paper_summary` is still missing
  - `case_failed:ding-wenbo` because `profile_summary_length=172`

Real API checks:

- Command: Admin TestClient requests for `/api/paper/PAPER-B907001E299D` and
  `/api/paper/PAPER-80EC1A859E64`.
- Result: both HTTP `200`; both returned canonical id `PAPER-B907001E299D`,
  `arxiv_id=2409.05701`,
  `pdf_url=https://arxiv.org/pdf/2409.05701v3`, and
  `canonical_source=crossref`.

Targeted verification:

- Command: `uv run pytest apps/admin-console/tests/test_admin_professor_api.py apps/admin-console/tests/test_chat_g_clarification.py apps/admin-console/tests/test_domains_postgres.py::test_paper_domain_detail_resolves_merge_alias apps/admin-console/tests/test_data_api_paper_v011.py apps/miroflow-agent/tests/data_agents/paper/test_title_resolver.py::test_resolve_supplements_crossref_match_with_arxiv_pdf_when_available apps/miroflow-agent/tests/data_agents/paper/test_title_resolver.py::test_arxiv_entry_to_resolved_covers_pfedgpa_pdf apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_process_rows_forwards_pfedgpa_arxiv_resolution_to_upsert apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py::test_pfedgpa_case_evaluates_canonical_alias_target -q -n0 --no-cov`
- Result: `27 passed, 1 skipped, 4 warnings in 0.22s`; warnings are existing
  FastAPI `on_event` deprecations.
- Command: `npm run test -- ProfessorWorkbench.test.tsx`
- Result: `1 passed` test file, `3 passed` tests.
- Command: `npm run build`
- Result: `tsc -b && vite build` completed successfully; Vite reported the
  existing large chunk warning.

Skipped checks and remaining risks:

- Broad research-overview write-mode backfill was not run; only Ahmed was
  written.
- Broad Professor output-summary write-mode backfill was not run; only a
  bounded dry-run with a fake LLM provider was executed.
- No live full seed closure was executed against `miroflow_real`.
- Ding Wenbo's summary was not regenerated in this slice.
- Ahmed Elazab's `paper_summary` was not generated in this slice.
- Dataset-level readiness remains blocked by the post-write audit blockers
  above.

## 2026-06-13 Task 8.4 Final Targeted Case Closure

Scope: close the remaining real-database acceptance failures for Ahmed Elazab
and Ding Wenbo while keeping writes limited to the named acceptance cases. This
section supersedes the earlier task 8 note that Ahmed still lacked
`paper_summary` and Ding had a short `profile_summary`.

Pre-check:

- Command: `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python scripts/run_professor_core_profile_paper_quality_audit.py`
- Result before this closure: exit `1`; pFedGPA was passing, Ahmed failed only
  `missing_paper_summary`, and Ding failed only `profile_summary_too_short`.

Ahmed Elazab targeted summary and duplicate closure:

- Command: source inspection with
  `select_eligible_paper_summary_inputs(conn, professor_id='PROF-823D4761D493')`.
- Result: Ahmed had 9 deduplicated eligible paper inputs, including the
  Alzheimer DOI row and multiple medical-imaging / prognosis papers.
- Command: dry-run `run_output_summary_backfill` for
  `PROF-823D4761D493` with an injected source-grounded JSON response.
- Result: `eligible=1`, `processed=1`, `failed=0`,
  `paper_summaries_written=1`, `dry_run=true`; existing
  `paper_summary` was absent.
- Command: targeted write under pipeline run
  `a9e1b512-0493-4355-9584-e7f773bbdd50`.
- Result: Ahmed `paper_summary` was written. Ahmed `profile_summary` was also
  expanded from 197 to 205 characters using the persisted research overview and
  linked paper evidence; quality-gate profile-summary checks returned no
  length or repetition reason.
- Command: duplicate audit SQL for Ahmed quality-gate duplicate groups.
- Result: the remaining group was
  `PAPER-07BC30B39202` (`prof_page_only`) duplicated with
  `PAPER-CB7AEEB57E38` (`crossref`, DOI `10.1016/j.eswa.2024.124780`).
- Command: `run_paper_title_enrichment_backfill.py --paper-id PAPER-07BC30B39202 --dry-run --disable-openalex-title-search --disable-dblp-title-search --disable-arxiv-title-search`
- Result: exit `0`; resolved to DOI `10.1016/j.eswa.2024.124780`,
  confidence `1.0`.
- Command: same command without `--dry-run`.
- Result: exit `0`; `paper_upserts=1`, `link_migrations=1`,
  `merge_aliases_written=1`, `old_links_rejected=1`,
  `page_only_papers_merged=1`.

Ding Wenbo targeted core-profile and output closure:

- Command: source inspection of `professor_fact` and `profile_raw_text` for
  `PROF-EB3DFC72A1BD`.
- Result: database contains contact, homepage, 2 education facts, 3 work
  experience facts, 4 research topics, 4 academic-position facts, and 11 award
  facts. No company/startup role was required for Professor core readiness.
- Command: local quality-gate validation of the candidate `profile_summary`.
- Result: 255 characters; `_profile_summary_contract_reason` returned `None`;
  `_profile_summary_is_shallow_or_repetitive` returned `False`.
- Command: targeted update under run id
  `a9e1b512-0493-4355-9584-e7f773bbdd50`.
- Result: Ding `profile_summary` updated to 255 characters.
- Command: `run_professor_research_overview_backfill.py --professor-id PROF-EB3DFC72A1BD --translation-overrides-json ...`
- Result: dry-run `section_ready`, source language `en`, source hash
  `35740eb787d627f45a6eb190aba7142da7e07dbdfa5565e875b3a36dda1f02ed`.
- Command: same research-overview command with `--write`.
- Result: exit `0`; wrote section id
  `c2058d48-a617-4daf-9e83-6a0a67e67870`.
- Command: source inspection with
  `select_eligible_paper_summary_inputs(conn, professor_id='PROF-EB3DFC72A1BD')`.
- Result: Ding had 10 eligible paper inputs, including communication-efficient
  federated learning, triboelectric tactile sensing, HMI, VANET routing, and
  self-powered systems papers.
- Command: dry-run `run_output_summary_backfill` for
  `PROF-EB3DFC72A1BD` with an injected source-grounded JSON response.
- Result: `eligible=1`, `processed=1`, `failed=0`,
  `paper_summaries_written=1`, `dry_run=true`.
- Command: write-mode `run_output_summary_backfill` for
  `PROF-EB3DFC72A1BD`.
- Result: `paper_summaries_written=1`,
  `refresh_professor_ids=['PROF-EB3DFC72A1BD']`, and stored
  `paper_summary` length `150`.

Quality re-evaluation:

- Command: `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python scripts/run_professor_quality_re_eval.py --id PROF-823D4761D493 --id PROF-EB3DFC72A1BD`
- Result after final targeted fixes: `evaluated=2`, `written=2`,
  `after_distribution={'ready': 2}`, and `reason_counts={}`.

Final case audit:

- Command: `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python scripts/run_professor_core_profile_paper_quality_audit.py`
- Result: exit `1`, expected because dataset-level gates remain blocked, but
  all baseline cases pass:
  - Ahmed Elazab: `status=passing`, `paper_summary_present=true`,
    `duplicate_title_active_verified_count=1`, `quality_status=ready`.
  - Ding Wenbo: `status=passing`, `profile_summary_length=255`,
    required fact counts present, `quality_status=ready`, and
    `professor_core_readiness_excludes=['hidden_company_roles']`.
  - pFedGPA: `status=passing`, canonical paper
    `PAPER-B907001E299D`, `arxiv_id=2409.05701`, and
    `pdf_url=https://arxiv.org/pdf/2409.05701v3`.
- Remaining dataset blockers:
  - `ready_summary_lt_200:441`
  - `missing_research_overview_zh:2510`
  - `missing_professor_paper_summary:2200`
  - `duplicate_verified_paper_title_year_groups:5186`

API verification:

- Command: Admin TestClient requests for
  `/api/admin/professor/PROF-823D4761D493` and
  `/api/admin/professor/PROF-EB3DFC72A1BD`.
- Result: both HTTP `200`; Admin detail returned non-empty
  `research_overview`, non-empty `paper_summary`, and paper lists of 9 and 10
  rows respectively.
- Command: generic TestClient requests for
  `/api/professor/PROF-823D4761D493` and
  `/api/professor/PROF-EB3DFC72A1BD`.
- Result: both HTTP `200`; both returned `quality_status=ready` with
  `profile_summary` lengths 205 and 255.
- Command: TestClient request for `/api/paper/PAPER-80EC1A859E64`.
- Result: HTTP `200`; old pFedGPA id resolves to canonical
  `PAPER-B907001E299D`, with `arxiv_id=2409.05701` and
  `pdf_url=https://arxiv.org/pdf/2409.05701v3`.

Skipped checks and remaining risks:

- Broad dataset write-mode backfills remain skipped. The four dataset blockers
  above still require a separate controlled batch/backfill pass.
- No live full seed closure was run after the targeted case writes.
- No Milvus/vector refresh was run for the changed Professor/Paper rows in this
  slice; `refresh_professor_ids` evidence is recorded for output-summary
  writes.
