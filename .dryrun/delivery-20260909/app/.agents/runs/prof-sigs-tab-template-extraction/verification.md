# Verification

## Commands

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_reads_sigs_tab_research_paragraph tests/data_agents/professor/test_homepage_crawler.py::test_crawl_homepage_extracts_sigs_tab_sections_without_llm_facts -q -n0
```

Result: failed before implementation, with empty SIGS research directions in both profile and homepage extraction.

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check src/data_agents/professor/profile.py src/data_agents/professor/homepage_crawler.py tests/data_agents/professor/test_profile_extraction.py tests/data_agents/professor/test_homepage_crawler.py
```

Result: passed.

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_profile_extraction.py tests/data_agents/professor/test_homepage_crawler.py -q -n0
```

Result: passed, 81 tests.

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy uv run --no-sync python <live SIGS sample script>
```

Result: passed. The script fetched Ahmed Elazab plus four randomly sampled SIGS pages and printed extracted title, email, tab sections, research directions, education/work counts, awards, academic positions, and paper signals.

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_homepage_crawler.py::test_extract_sigs_tab_homepage_output_parses_chinese_date_fact_lines \
  tests/data_agents/professor/test_homepage_crawler.py::test_extract_sigs_tab_homepage_output_splits_compound_sigs_fact_lines \
  tests/data_agents/professor/test_homepage_crawler.py::test_extract_sigs_tab_homepage_output_parses_degree_first_fact_lines \
  tests/data_agents/professor/test_homepage_crawler.py::test_extract_sigs_tab_homepage_output_parses_tilde_and_adjacent_date_ranges \
  tests/data_agents/professor/test_homepage_crawler.py::test_extract_official_publication_signals_sigs_author_prefix_yields_title \
  tests/data_agents/professor/test_homepage_crawler.py::test_extract_official_publication_signals_sigs_author_period_lines_yield_titles \
  tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_sigs_english_research_keeps_atomic_topics \
  tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_sigs_chinese_research_field_variants \
  tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_sigs_chinese_keyword_research_topic \
  tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_sigs_chinese_research_stops_before_metrics \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_encodes_unicode_profile_url_before_request \
  -q -n0
```

Result: passed. These tests cover the second quality pass regressions.

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check \
  src/data_agents/professor/profile.py \
  src/data_agents/professor/homepage_crawler.py \
  src/data_agents/professor/discovery.py \
  tests/data_agents/professor/test_profile_extraction.py \
  tests/data_agents/professor/test_homepage_crawler.py \
  tests/data_agents/professor/test_roster_validation.py
```

Result: passed.

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_profile_extraction.py \
  tests/data_agents/professor/test_homepage_crawler.py \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_encodes_unicode_profile_url_before_request \
  -q -n0
```

Result: passed, 92 tests.

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy uv run --no-sync python <25-page live SIGS sample audit>
```

Result: passed. Summary: `sample_size=25`, `fetch_error=0`, `no_sections=0`, `missing_title=0`, `title_contamination=0`, `missing_research=6`, `research_fragments=1`, `missing_education=1`, `missing_work=1`, `suspicious_education_or_work=1`, `paper_signal_suspicious=0`.

## 2026-05-27 Reopened Verification

The change was reopened after a full SIGS recollection exposed a sibling parser defect: SIGS tab headings could be selected as professor names. This caused unrelated profiles to merge and made official page fields appear missing downstream.

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_name_selection.py::test_is_obvious_non_person_name_recognizes_sigs_tab_section_titles \
  tests/data_agents/professor/test_name_selection.py::test_select_canonical_name_falls_back_to_roster_name_when_extracted_is_nav_noise \
  tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_uses_sigs_top_name_before_tab_section_heading \
  -q -n0
```

Result before fix: failed. SIGS section headings such as `教育经历` were not rejected as non-person names, and the SIGS profile parser could select a tab heading instead of the top-layout professor name.

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_name_selection.py::test_is_obvious_non_person_name_recognizes_sigs_tab_section_titles \
  tests/data_agents/professor/test_name_selection.py::test_select_canonical_name_falls_back_to_roster_name_when_extracted_is_nav_noise \
  tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_uses_sigs_top_name_before_tab_section_heading \
  -q -n0
```

Result after fix: passed, 8 tests.

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_enrichment.py::test_extract_profile_record_carries_sigs_tab_structured_fields \
  tests/postgres/test_run_single_seed.py::test_merged_to_enriched_builds_deterministic_profile_summary \
  -q -n0
```

Result: passed. These tests verify deterministic SIGS tab structured fields survive enrichment and seed-import conversion, and that seed-import summaries can be generated from official structured fields.

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check \
  src/data_agents/professor/models.py \
  src/data_agents/professor/enrichment.py \
  src/data_agents/professor/seed_runner.py \
  src/data_agents/professor/profile.py \
  src/data_agents/professor/name_selection.py \
  tests/data_agents/professor/test_enrichment.py \
  tests/data_agents/professor/test_profile_extraction.py \
  tests/data_agents/professor/test_name_selection.py \
  tests/postgres/test_run_single_seed.py
```

Result: passed.

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_enrichment.py \
  tests/data_agents/professor/test_profile_extraction.py \
  tests/data_agents/professor/test_name_selection.py \
  tests/data_agents/professor/test_homepage_crawler.py \
  tests/data_agents/professor/test_roster_validation.py \
  tests/postgres/test_run_single_seed.py \
  -q -n0
```

Result: passed, 299 tests passed and 12 skipped. The skipped tests require `DATABASE_URL_TEST` or `DATABASE_URL` for PostgreSQL integration coverage and did not fail.

## 2026-05-27 SIGS Seed 8 Data Refresh

Runtime database: `postgresql://miroflow:miroflow@localhost:15432/miroflow_real`.

Seed:

- `seed_id=8`
- `school=清华大学深圳国际研究生院`
- `seed_url=https://www.sigs.tsinghua.edu.cn/7644/list.htm`
- `adapter=sigs_teacher_api`

Before destructive cleanup, the existing SIGS rows were backed up to:

```text
.agents/runs/prof-sigs-tab-template-extraction/sigs-purge-backup-20260527T091511Z.json
```

The user explicitly requested deleting the old SIGS data before the fixed recollection. This refresh deleted current SIGS canonical rows and associated source/fact/issue rows for seed 8, then ran a full seed recollection.

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <run_single_seed seed_id=8 trigger_mode=full timeout=45.0>
```

Result:

```text
run_id=390698fd-5043-4d42-85d5-ccd82f027039
status=success
items_processed=250
items_failed=0
adapter_name=sigs_teacher_api
failure_class=success
```

Metadata note: admin single-seed runs currently keep `pipeline_run.seed_id` empty and store the seed identity in `pipeline_run.run_scope.seed_id`. A direct run-history query confirmed `run_scope.seed_id=8`, `status=succeeded`, `items_processed=250`, and `items_failed=0` for this run.

Database validation for primary current SIGS affiliation:

```text
professor_count=250
primary_current_affiliation_count=250
missing_name=0
missing_raw_text=0
missing_title=4
long_title=0
with_contact=246
with_homepage=250
with_research_topics=173
with_education=218
with_work=215
with_awards=195
with_academic_positions=181
with_profile_summary=250
avg_summary_len=243.2
ready=172
needs_enrichment=78
needs_review=0
low_confidence=0
suspicious_canonical_names=0
unresolved_pipeline_issues=0
```

Canonical fact coverage:

```text
homepage: 250 facts, 250 professors
contact: 246 facts, 246 professors
research_topic: 951 facts, 173 professors
education: 610 facts, 218 professors
work_experience: 958 facts, 215 professors
award: 1303 facts, 195 professors
academic_position: 857 facts, 181 professors
```

Key-profile checks:

```text
Ahmed Elazab:
  quality_status=ready
  title=助理教授，博士生导师
  summary_len=197
  research_topic=10
  education=3
  work_experience=4
  award=4
  academic_position=4

Ercan Engin Kuruoğlu:
  quality_status=ready
  research_topic=11
  education=1
  work_experience=14
  award=1
  academic_position=0

Xiaodong CHEN（陈晓东）:
  quality_status=ready
  research_topic=1
  education=3
  work_experience=6
  award=15
  academic_position=7
```

Random sample for user review after recollection:

```text
张成萍: ready, summary_len=226, research=1, education=3, work=3, award=3, academic_position=0
黄儒麒: ready, summary_len=294, research=1, education=3, work=3, award=0, academic_position=1
刘厚德: needs_enrichment, summary_len=171, research=0, education=3, work=4, award=7, academic_position=2
马岚: needs_enrichment, summary_len=257, research=0, education=4, work=3, award=4, academic_position=5
Parvej Alam: ready, summary_len=232, research=18, education=3, work=2, award=6, academic_position=0
曹顺翔: ready, summary_len=239, research=14, education=2, work=2, award=4, academic_position=1
沈欣炜: needs_enrichment, summary_len=300, research=0, education=3, work=7, award=7, academic_position=7
Ercan Engin Kuruoğlu: ready, summary_len=197, research=11, education=1, work=14, award=1, academic_position=0
胡振中: ready, summary_len=264, research=4, education=2, work=4, award=13, academic_position=6
毛献忠: ready, summary_len=233, research=4, education=3, work=4, award=0, academic_position=1
```

Remaining SIGS gaps:

- `78/250` profiles remain `needs_enrichment`; this is now mostly because the official page did not yield a canonical `research_topic` under the current conservative parser and quality gate.
- `4/250` profiles still miss a title.
- These are not the prior section-heading name merge defect; `suspicious_canonical_names=0` and primary current affiliation coverage is 250/250.

## 2026-05-27 Final Check

```bash
openspec validate prof-sigs-tab-template-extraction --strict
```

Result: passed. The change is valid.

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_name_selection.py::test_is_obvious_non_person_name_recognizes_sigs_tab_section_titles \
  tests/data_agents/professor/test_name_selection.py::test_select_canonical_name_falls_back_to_roster_name_when_extracted_is_nav_noise \
  tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_uses_sigs_top_name_before_tab_section_heading \
  tests/data_agents/professor/test_enrichment.py::test_extract_profile_record_carries_sigs_tab_structured_fields \
  tests/postgres/test_run_single_seed.py::test_merged_to_enriched_builds_deterministic_profile_summary \
  -q -n0
```

Result: passed, 10 tests.
