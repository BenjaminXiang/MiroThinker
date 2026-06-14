# Verification: prof-paper-patent-from-page-flow

## 2026-05-13 — Real seed sample E2E

### Scope

- Database: `miroflow_real`
- Seed: `professor_seed.id=9`, Southern University of Science and
  Technology faculty index, `https://www.sustech.edu.cn/zh/letter/`
- Sampling rule: read-only pre-scan first, then persist only 3 selected
  professor profiles with Publications sections. The `/api/seeds/{id}/trigger`
  endpoint was not used because it has no sample-size cap and would run the
  full seed.
- Selected profiles:
  - `PROF-ABBDE6D18E0E`, Wu Ri,
    `https://www.sustech.edu.cn/zh/faculties/riwu.html`
  - `PROF-B2A805F9D077`, Yang Zhenlin,
    `https://www.sustech.edu.cn/zh/faculties/zhenlinyang.html`
  - `PROF-A76E75D037D2`, Yang Yang,
    `https://www.sustech.edu.cn/zh/faculties/yangyang-2.html`

### Environment

- `DATABASE_URL` was not set in the shell, so commands used the explicit local
  DSN `postgresql://miroflow:miroflow@localhost:15432/miroflow_real`.
- Provider credentials were absent in the shell:
  `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LOCAL_LLM_BASE_URL`,
  `LOCAL_LLM_API_KEY`, `SERPER_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`, and
  `CROSSREF_MAILTO`.
- Milvus environment was absent in the shell:
  `MILVUS_URI`, `MILVUS_HOST`, and `MILVUS_PORT`.

### Preflight

- `professor_seed`: 15 rows, all `never_run`.
- `miroflow_real` Alembic version before the first run: `V023`.
- SUSTech seed discovery returned 988 professor profiles.
- First 40 profile-page pre-scan found 3 publication-bearing sample profiles
  and no patent sections among the selected sample.

### Runtime issue found

The first paper ingest attempt exposed a real schema/runtime drift:

```text
psycopg.errors.CheckViolation:
new row for relation "paper" violates check constraint "ck_paper_canonical_source"
canonical_source=prof_page_only
```

Root cause: `paper.homepage_ingest` now writes page-only publications with
`canonical_source='prof_page_only'`, but the V004 database check constraint only
allowed `openalex`, `semantic_scholar`, `crossref`, `official_page`, and
`manual`.

Fix added in this slice:

- `apps/miroflow-agent/alembic/versions/V024_extend_paper_canonical_source_page_flow.py`
  extends `ck_paper_canonical_source` to allow `prof_page_only`, `arxiv`, and
  `web_search`.
- `apps/miroflow-agent/tests/storage/test_v024_migration.py` verifies the
  revision chain and insert behavior.

Verification:

```bash
cd apps/miroflow-agent
DB=miroflow_test_v024_$(date +%s)
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/$DB \
  uv run --no-sync pytest tests/storage/test_v024_migration.py -q -n0
```

Result: `2 passed in 2.75s`.

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check \
  alembic/versions/V024_extend_paper_canonical_source_page_flow.py \
  tests/storage/test_v024_migration.py \
  src/data_agents/canonical/paper.py
```

Result: `All checks passed!`.

Applied to real DB:

```bash
cd apps/miroflow-agent
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run --no-sync alembic upgrade head
```

Result: `V023 -> V024`; verified `alembic_version = V024` and
`ck_paper_canonical_source` includes `prof_page_only`, `arxiv`, and
`web_search`.

### Final sample results

Summary artifact:
`/tmp/prof-paper-patent-sample-e2e-20260513-final-summary.json`

Counts after the sample run:

| Table / metric | Count |
|---|---:|
| `professor` | 3 |
| `paper` | 31 |
| `patent` | 0 |
| `professor_paper_link` | 31 |
| `professor_patent_link` | 0 |
| `paper_full_text` | 31 |
| `pipeline_run` | 10 |
| `pipeline_issue` | 2 |
| `source_page` | 5 |

Paper status distribution:

| `quality_status` | `identity_status` | `canonical_source` | Count |
|---|---|---|---:|
| `needs_enrichment` | `confirmed` | `openalex` | 23 |
| `needs_enrichment` | `unverified` | `prof_page_only` | 8 |

Paper links by professor:

| Professor | Links |
|---|---:|
| Wu Ri | 13 |
| Yang Zhenlin | 11 |
| Yang Yang | 7 |

Patent result:

- The selected 3 professor pages had no patent sections.
- `patent=0`, `professor_patent_link=0`, and no sample-specific
  `pipeline_issue` rows were created.
- This does not validate the canonical patent-with-number path or the
  title-only patent `data_quality_flag` path against live SUSTech data.

Summary/promotion result:

- `paper.total=31`, `summary_zh.with_summary=0`.
- No paper promoted to `ready` because no LLM credentials were present and the
  summary backfill was not run.
- The sample validates professor roster write, homepage publication extraction,
  paper canonical insert, `paper_full_text` insert, and
  `professor_paper_link` writeback. It does not close the full T8.3 acceptance
  item for summary generation, promotion-to-ready, Milvus, or end-user RAG.

### Pipeline run audit

- Failed setup attempt retained for audit:
  `28bf92b1-a40d-4c59-88b3-f2050f2b46ae`. It rolled back due to a local
  script `row_factory=dict_row` mismatch before professor rows persisted.
- Successful professor sample run:
  `7a62f067-6472-4d40-92a4-22e0edbf107e`.
- Successful paper/patent per-professor runs:
  - `cf42b88c-0131-4e52-8fc3-3b3be7547ba4` paper, Wu Ri
  - `a1b0f460-78cb-4149-b67a-f0a8957c7c86` patent, Wu Ri
  - `25484a47-92ef-4e5c-8533-828f246351f1` paper, Yang Zhenlin
  - `1f022304-206c-4a74-a5fe-3b1e778fdf07` patent, Yang Zhenlin
  - `9c699414-f18c-4f8d-8e4d-dd3121c11474` paper, Yang Yang
  - `e066db5a-c937-415b-b4e2-26c21086a155` patent, Yang Yang

All successful per-professor runs recorded `status='succeeded'`,
`items_processed=1`, and `items_failed=0`.

### Remaining verification gaps

- Run a sample seed with a visible Patents section to measure
  with-registration-number success rate and title-only failure modes before
  deciding `patent-page-only-canonical`.
- Run summary backfill with LLM credentials, then measure the 50-row
  `summary_zh` character distribution and promotion-to-ready behavior.
- Run Milvus / RAG verification after canonical rows have summaries and
  embeddings.
- Add a bounded trigger/sample mode to the admin seed trigger if operators need
  safe partial runs from the frontend.

## 2026-05-13 — SUSTech profile and paper repair verification

### Profile Repair

Pre-repair DB query:

- Target professor IDs:
  - `PROF-ABBDE6D18E0E`
  - `PROF-B2A805F9D077`
  - `PROF-A76E75D037D2`
- Result: all three rows had `profile_raw_text IS NULL`,
  `profile_summary IS NULL`, and no primary affiliation department/title.

Code-level checks:

- `uv run --no-sync pytest tests/data_agents/professor/test_profile_extraction.py tests/data_agents/professor/test_enrichment.py -q`
  - Result: `18 passed`.
- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_profile_raw_text DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_profile_raw_text uv run --no-sync pytest tests/professor/test_canonical_writer.py -q -n0`
  - Result: `9 passed, 30 warnings`.

Real DB backfill:

- Command: targeted Python backfill using `extract_profile_record`,
  `write_professor_bundle`, and fallback profile summaries.
- Run id: `3899267b-a8d1-4806-a9a4-777282b85788`.
- Result: `status='succeeded'`, `items_processed=3`, `items_failed=0`.
- Post-repair query:
  - `3/3` rows have `profile_raw_text`.
  - `3/3` rows have `profile_summary`.
  - `3/3` rows have department and title.
  - Each official profile URL maps to exactly one professor row.
  - Three stale empty primary affiliation rows were demoted.
  - Each target professor now has exactly one primary affiliation, and that
    row has department and title.

### Paper Repair

Root cause:

- Official professor-page links were already verified, but paper rows remained
  `needs_enrichment` because metadata and summaries were missing.
- Several SUSTech homepage author-list fragments were parsed as titles.
- `scripts/run_homepage_paper_ingest.py` returned success without committing
  the DB transaction.

Code-level checks:

- `uv run --no-sync pytest tests/data_agents/professor/test_homepage_publications.py -q`
  - Result: `80 passed`.
- `uv run --no-sync pytest tests/scripts/test_run_paper_summary_zh_backfill.py tests/scripts/test_run_homepage_paper_ingest.py -q`
  - Result: `19 passed`.
- `uv run --no-sync ruff check scripts/run_paper_summary_zh_backfill.py scripts/run_homepage_paper_ingest.py tests/scripts/test_run_paper_summary_zh_backfill.py tests/scripts/test_run_homepage_paper_ingest.py src/data_agents/professor/homepage_publications.py tests/data_agents/professor/test_homepage_publications.py src/data_agents/professor/profile.py src/data_agents/professor/models.py src/data_agents/professor/enrichment.py src/data_agents/professor/seed_runner.py src/data_agents/professor/canonical_writer.py tests/data_agents/professor/test_profile_extraction.py tests/data_agents/professor/test_enrichment.py tests/professor/test_canonical_writer.py`
  - Result: `All checks passed!`.

Real DB execution:

- Paper summary backfill with DOI enrichment:
  - Run `60adcf4a-5459-44b8-8bf8-165c9eafa7df` wrote `20`
    summaries and enriched `6` DOI metadata rows.
  - Run `f9867d6a-bc60-43dd-80a8-5ca18e8809f0` wrote `6`
    additional summaries and enriched `1` DOI metadata row.
- Homepage paper ingest after commit fix:
  - Wu Ri: `13` links, `2` full-text rows, `0` issues.
  - Yang Zhenlin: `10` links, `2` full-text rows, `0` issues.
  - Yang Yang: `7` links, `1` full-text row, `0` issues.
- Bad title cleanup:
  - Seven false fragment papers were set to `quality_status='rejected'`.
  - Matching links were set to `link_status='rejected'` and
    `rejected_reason='homepage_publication_parser_false_title_fragment'`.

Final verified-link distribution:

| Status | Count |
|---|---:|
| `ready` | 26 |
| `partial` | 3 |
| `needs_enrichment` | 1 |

Remaining non-ready rows:

- `1` page-only row with no DOI/abstract available from the current resolver.
- `3` DOI/OpenAlex rows without abstracts, so `summary_zh` cannot be generated
  by the current abstract-based summary path.

## 2026-05-14 - Professor profile summary boilerplate repair

### Root Cause

- `profile_summary` is both user-visible text and retrieval/vector input.
- The fallback summary generator padded sparse profiles with operator/meta
  language about evidence coverage, retrieval, and manual review.
- The quality gate did not reject those phrases, so the text was accepted and
  shown in the admin record detail page.

### Code Verification

- `uv run --no-sync pytest tests/data_agents/professor/test_vectorizer_metrics.py tests/scripts/test_run_milvus_backfill.py tests/data_agents/professor/test_summary_generator.py tests/data_agents/professor/test_release.py tests/data_agents/professor/test_quality_gate.py tests/scripts/test_run_quality_gate_reassess.py -q -n0`
  - Result: `63 passed`.
- `uv run --no-sync ruff check src/data_agents/professor/profile_summary_contract.py src/data_agents/professor/summary_generator.py src/data_agents/professor/release.py src/data_agents/professor/vectorizer.py src/data_agents/storage/milvus_collections.py scripts/run_milvus_backfill.py tests/data_agents/professor/test_summary_generator.py tests/data_agents/professor/test_release.py tests/data_agents/professor/test_vectorizer_metrics.py tests/scripts/test_run_milvus_backfill.py`
  - Result: `All checks passed!`.

### Real Runtime Verification

- Rewrote the three target SUSTech `profile_summary` rows in `miroflow_real`
  from official profile text.
- Post-repair DB query found `0` professor summaries containing the banned
  operator/meta phrases.
- Targeted real Milvus Lite backfill:
  - `MILVUS_USE_REAL_CLIENT=1 DATABASE_URL=postgresql://... uv run --no-sync python scripts/run_milvus_backfill.py --domain professor --id PROF-ABBDE6D18E0E --id PROF-B2A805F9D077 --id PROF-A76E75D037D2 --batch-size 3 --milvus-uri /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db`
  - Result: `profs_total=3`, `profs_processed=3`, `profs_skipped=0`,
    `profs_with_errors=0`.
- Direct Milvus vector search for mass-spectrometry / biomolecular-structure
  terms returned Wu Ri first with the repaired summary text.
- Restarted admin backend on `0.0.0.0:18188`; API
  `/api/professor/PROF-ABBDE6D18E0E` returns the repaired summary.

## 2026-05-14 - Profile summary review follow-up

### Review Items Accepted

- Milvus Lite scalar metrics cannot be nullable; comments now document that
  `0` in Milvus means canonical metric is unknown and Postgres is
  authoritative.
- `_coerce_profile_summary` is documented as a defensive backstop; frequent
  hits indicate an upstream generator/fallback regression.
- Fallback summary construction now drops structured fragments containing
  operator/meta language before returning a summary.

### Red / Green Evidence

- RED:
  `uv run --no-sync pytest tests/data_agents/professor/test_summary_generator.py::test_fallback_profile_summary_drops_operator_meta_structured_parts -q -n0`
  failed because fallback copied the meta phrase from `awards`.
- GREEN:
  The same command passed after filtering fallback parts with the shared
  meta-language contract.
- Targeted suite:
  `uv run --no-sync pytest tests/data_agents/professor/test_summary_generator.py tests/data_agents/professor/test_release.py tests/data_agents/professor/test_vectorizer_metrics.py tests/scripts/test_run_milvus_backfill.py -q -n0`
  returned `30 passed`.
- `uv run --no-sync ruff check src/data_agents/professor/summary_generator.py src/data_agents/professor/release.py src/data_agents/professor/vectorizer.py scripts/run_milvus_backfill.py tests/data_agents/professor/test_summary_generator.py`
  returned `All checks passed!`.
- `tests/professor/test_canonical_writer.py` was rerun against isolated
  temporary database `miroflow_test_profile_summary_review` with both
  `DATABASE_URL` and `DATABASE_URL_TEST` set; result: `9 passed, 30 warnings`.

## 2026-05-21 - T8.3 close-out refresh

### Current DB state

- Database: `postgresql://miroflow:miroflow@localhost:15432/miroflow_real`
  (local credentials only; no secret value copied beyond the local DSN already
  used by prior runbooks).
- Alembic version: `V027`.
- Table counts:
  - `professor=495`
  - `paper=43`
  - `company=0`
  - `patent=0`
  - `professor_paper_link=43`
  - `professor_patent_link=0`
- Paper quality distribution:
  - `ready=31`
  - `partial=3`
  - `needs_enrichment=2`
  - `rejected=7`
- Summary distribution:
  - `summary_zh` non-empty: `31/43`
  - within 200-400 chars: `23/31`
  - min length: `172`
  - max length: `490`
  - average length: `350.3`
- Verified professor-paper link quality examples:
  - Wu Ri: 13 links, 12 `ready`
  - Yang Zhenlin: 10 links, 8 `ready`
  - Yang Yang: 7 links, 6 `ready`
  - Gao Ziqi: 6 links, 5 `ready`

### Focused regression suite

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/paper/test_homepage_ingest.py \
  tests/data_agents/paper/test_homepage_ingest_preprint.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/data_agents/patent/test_homepage_ingest.py \
  tests/data_agents/professor/test_homepage_patents.py \
  -q
```

Result: `56 passed in 18.62s`.

### OpenSpec validation

```bash
openspec validate prof-paper-patent-from-page-flow --strict
```

Result: `Change 'prof-paper-patent-from-page-flow' is valid`.

### Paper Milvus backfill

```bash
cd apps/miroflow-agent
MILVUS_USE_REAL_CLIENT=1 \
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
uv run --no-sync python scripts/run_milvus_backfill.py \
  --domain paper \
  --limit 43 \
  --batch-size 16 \
  --milvus-uri /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db
```

Result:

```json
{
  "papers_total": 43,
  "papers_processed": 43,
  "papers_skipped": 0,
  "chunks_inserted": 78,
  "papers_with_errors": 0,
  "duration_seconds": 2.1064411010593176
}
```

### Direct vector search

- Query text: `mass spectrometry peptide structure biomolecular analysis`.
- Embedding: local embedding key from `load_local_api_key()`.
- Collection searched: `paper_chunks`.
- Top results were relevant mass-spectrometry / biomolecular-analysis papers:
  - `PAPER-EB6E2018F841:title:0`, distance `0.723...`, title
    `Adapting a Fourier Transform Ion Cyclotron Resonance Mass Spectrometer for Gas-Phase Fluorescence Spectroscopy Measurement of Trapped Biomolecular Ions`
  - `PAPER-28F1B3C862C8:title:0`, distance `0.706...`
  - `PAPER-8A3F940DA856:title:0`, distance `0.694...`
  - `PAPER-90B27B8BA926:title:0`, distance `0.682...`
  - `PAPER-0E5D6FCEA623:title:0`, distance `0.679...`

### Provider environment

Unset in the shell:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `LOCAL_LLM_BASE_URL`
- `LOCAL_LLM_API_KEY`
- `SERPER_API_KEY`
- `SEMANTIC_SCHOLAR_API_KEY`
- `CROSSREF_MAILTO`

The local embedding key was available through the existing local key loader.

### Patent-section scan

- Source-page scan checked cached `clean_text_path` entries for patent-section
  terms.
- Result: `pages_scanned=0`, `keyword_or_entries_pages=0`, `matches=[]`.
- Disposition: current DB has no cached live source page that can measure a
  real Patents section. Live patent-section success rates and title-only patent
  canonical behavior remain assigned to `patent-page-only-canonical`.

### Close-out conclusion

- Core paper E2E evidence is now refreshed: live Postgres rows exist,
  summaries exist, at least one paper has promoted to `ready`, focused tests
  pass, paper Milvus backfill succeeds for all 43 live papers, and direct vector
  search returns relevant chunks.
- The strict 50-paper summary distribution remains unavailable because the
  current DB has only 31 non-empty summaries.
- Async enrichment was not independently proven in this refresh; the verified
  promotion path is the summary/backfill path.
- Live patent-section measurement remains a follow-up because no suitable
  cached source page exists in the current DB.
