# Verification: paper-pdf-fulltext-ingest

## 2026-05-23 - T1 PDF Discovery

Scope:
- T1.1: Extend professor publication parsing to preserve direct PDF links.
- T1.2: Attach PDF links to page-discovered paper candidates.
- T1.3: Add tests for relative, absolute, and DOI-adjacent PDF links.

Current slice evidence:
- `HomepagePublication` now carries `pdf_url`.
- Professor homepage publication parsing extracts direct `.pdf` anchors from
  list, paragraph, table, and definition-list publication entries.
- Relative PDF links are resolved against the professor page URL.
- DOI anchors remain `source_anchor` while adjacent PDF anchors become
  `pdf_url`.
- Homepage paper ingest attaches professor-page `pdf_url` to resolved/page-only
  paper candidates before full-text fetch.

Commands:

- `uv run --no-sync pytest tests/data_agents/professor/test_homepage_publications.py tests/data_agents/paper/test_homepage_ingest_preprint.py tests/data_agents/paper/test_homepage_ingest.py -q -n0`
  - Result: passed, `109 passed in 6.17s`.
  - Coverage: parser extraction, page-only synthesis, homepage ingest PDF
    propagation, and existing homepage ingest regressions.

- `uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_pdf_t1_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.execute(f'CREATE DATABASE {name}'); conn.close(); print(name)"`
  - Result: passed; created temporary DB
    `miroflow_test_paper_pdf_t1_codex`.

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_pdf_t1_codex uv run --no-sync pytest tests/postgres/test_homepage_paper_ingest_tier_evidence.py -q -n0`
  - Result: passed, `4 passed in 5.55s`.
  - E2E coverage: Alembic V001-V030 migration setup, homepage paper ingest,
    professor-page PDF URL propagation into full-text fetch, and
    `paper_full_text.pdf_url/source` persistence using a mocked PDF extraction
    boundary.

- `uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_pdf_t1_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.close(); print('dropped ' + name)"`
  - Result: passed; dropped temporary DB
    `miroflow_test_paper_pdf_t1_codex`.

- `uv run --no-sync ruff check src/data_agents/professor/homepage_publications.py src/data_agents/paper/homepage_ingest.py tests/data_agents/professor/test_homepage_publications.py tests/data_agents/paper/test_homepage_ingest.py tests/data_agents/paper/test_homepage_ingest_preprint.py tests/postgres/test_homepage_paper_ingest_tier_evidence.py`
  - Result: passed, `All checks passed!`.

Checkpoint note:
- T4 final full-text verification is completed in the final section below.

## 2026-05-23 - T4 Final Verification

Scope:
- T4.1: Run paper full-text tests.
- T4.2: Run homepage ingest tests affected by PDF links.
- T4.3: Run a bounded sample with direct professor-page PDF links.

Commands:

- `uv run --no-sync pytest tests/data_agents/paper/test_full_text_fetcher.py tests/data_agents/paper/test_raw_pdf_store.py tests/storage/test_paper_full_text_writer.py tests/storage/test_v031_migration.py tests/storage/test_alembic_revision_lineage.py -q -n0`
  - Result: passed, `66 passed, 3 skipped in 29.45s`.
  - Skips: DB integration writer tests skipped because this command did not
    set `DATABASE_URL_TEST`; the bounded Postgres command below covers the
    migrated DB path.

- `uv run --no-sync pytest tests/data_agents/professor/test_homepage_publications.py tests/data_agents/paper/test_homepage_ingest_preprint.py tests/data_agents/paper/test_homepage_ingest.py -q -n0`
  - Result: passed, `111 passed in 6.75s`.

- `uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_pdf_t4_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.execute(f'CREATE DATABASE {name}'); conn.close(); print(name)"`
  - Result: passed; created temporary DB
    `miroflow_test_paper_pdf_t4_codex`.

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_pdf_t4_codex uv run --no-sync pytest tests/postgres/test_homepage_paper_ingest_tier_evidence.py -q -n0`
  - Result: passed, `6 passed in 5.71s`.
  - Bounded sample coverage: Alembic V001-V031 migration setup, direct
    professor-page PDF URL propagation, fetch cap diagnostics, `paper_full_text`
    provenance fields, raw PDF filesystem blob persistence, and duplicate PDF
    bytes deduped to one sha-addressed object.

- `uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_pdf_t4_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.close(); print('dropped ' + name)"`
  - Result: passed; dropped temporary DB
    `miroflow_test_paper_pdf_t4_codex`.

- `uv run --no-sync ruff check src/data_agents/professor/homepage_publications.py src/data_agents/paper/full_text_fetcher.py src/data_agents/paper/raw_pdf_store.py src/data_agents/paper/homepage_ingest.py src/data_agents/storage/postgres/paper_full_text.py alembic/versions/V031_add_paper_full_text_raw_pdf_provenance.py tests/data_agents/professor/test_homepage_publications.py tests/data_agents/paper/test_full_text_fetcher.py tests/data_agents/paper/test_raw_pdf_store.py tests/data_agents/paper/test_homepage_ingest.py tests/data_agents/paper/test_homepage_ingest_preprint.py tests/postgres/test_homepage_paper_ingest_tier_evidence.py tests/storage/test_paper_full_text_writer.py tests/storage/test_v031_migration.py tests/storage/test_alembic_revision_lineage.py`
  - Result: passed, `All checks passed!`.

- `openspec validate paper-pdf-fulltext-ingest --strict`
  - Result: passed, `Change 'paper-pdf-fulltext-ingest' is valid`.

Completion status:
- T1-T4 tasks are complete for `paper-pdf-fulltext-ingest`.
- All acceptance rows for the change are checked.

## 2026-05-23 - T2 Fetch and Caps

Scope:
- T2.1: Extend full-text fetcher for professor-page PDF URLs.
- T2.2: Enforce byte-size, timeout, content-type, redirect, and per-run caps.
- T2.3: File `pipeline_issue` diagnostics for cap violations.
- T2.4: Add mocked HTTP tests for each cap.

TDD RED evidence:
- `uv run --no-sync pytest tests/data_agents/paper/test_full_text_fetcher.py::test_download_pdf_rejects_disallowed_content_type tests/data_agents/paper/test_full_text_fetcher.py::test_make_http_client_uses_trust_env_false_and_follow_redirects tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_professor_page_pdf_happy_path tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_prefers_direct_professor_page_pdf_over_arxiv tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_professor_page_pdf_timeout_marks_timeout tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_professor_page_pdf_redirect_cap_marks_error tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_professor_page_pdf_bad_content_type_marks_cap_error tests/data_agents/paper/test_homepage_ingest.py::test_professor_page_pdf_fetch_cap_files_issue_and_skips_extra_fetches tests/data_agents/paper/test_homepage_ingest.py::test_professor_page_pdf_cap_violation_files_pipeline_issue -q -n0`
  - Result before implementation: failed during collection because
    `_UnsupportedContentTypeError` did not exist.

- `uv run --no-sync pytest tests/data_agents/paper/test_homepage_ingest.py::test_professor_page_pdf_fetch_cap_files_issue_and_skips_extra_fetches tests/data_agents/paper/test_homepage_ingest.py::test_professor_page_pdf_cap_violation_files_pipeline_issue -q -n0`
  - Result before implementation: `2 failed`.
  - Failure causes: `run_homepage_paper_ingest()` had no
    `prof_page_pdf_fetch_cap` parameter, and fetch cap violations did not
    increment/file pipeline issues.

Implementation evidence:
- `fetch_and_extract_full_text()` now fetches direct professor-page PDF URLs
  with source `prof_page_pdf`, preferring those direct URLs over arXiv when
  both are present.
- `_download_pdf()` rejects disallowed content types, keeps byte-size caps,
  and the HTTP client uses `max_redirects=5`.
- Direct professor-page PDF fetch failures normalize timeout, redirect-cap,
  content-type, size, HTTP, network, and parse outcomes into `fetch_error`
  tags.
- `run_homepage_paper_ingest()` enforces a per-run professor-page PDF fetch
  cap and files `pipeline_issue` diagnostics for cap exceedance and cap
  violation outcomes.

Commands:

- `uv run --no-sync pytest tests/data_agents/paper/test_full_text_fetcher.py::test_download_pdf_rejects_disallowed_content_type tests/data_agents/paper/test_full_text_fetcher.py::test_make_http_client_uses_trust_env_false_and_follow_redirects tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_professor_page_pdf_happy_path tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_prefers_direct_professor_page_pdf_over_arxiv tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_professor_page_pdf_timeout_marks_timeout tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_professor_page_pdf_redirect_cap_marks_error tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_professor_page_pdf_bad_content_type_marks_cap_error tests/data_agents/paper/test_homepage_ingest.py::test_professor_page_pdf_fetch_cap_files_issue_and_skips_extra_fetches tests/data_agents/paper/test_homepage_ingest.py::test_professor_page_pdf_cap_violation_files_pipeline_issue -q -n0`
  - Result after implementation: passed, `9 passed in 5.07s`.

- `uv run --no-sync pytest tests/data_agents/paper/test_full_text_fetcher.py tests/data_agents/paper/test_homepage_ingest.py -q -n0`
  - Result: passed, `72 passed in 29.37s`.
  - Coverage: full-text fetcher regression matrix plus homepage ingest branches
    affected by professor-page PDF fetching and cap diagnostics.

- `uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_pdf_t2_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.execute(f'CREATE DATABASE {name}'); conn.close(); print(name)"`
  - Result: passed; created temporary DB
    `miroflow_test_paper_pdf_t2_codex`.

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_pdf_t2_codex uv run --no-sync pytest tests/postgres/test_homepage_paper_ingest_tier_evidence.py -q -n0`
  - First result: failed, `1 failed, 4 passed`.
  - Finding: `pipeline_issue` persistence used `ON CONFLICT DO NOTHING`; two
    cap-exceeded issues with identical descriptions collapsed into one DB row.
  - Fix: include the affected PDF URL in the cap diagnostic message so every
    skipped URL has a distinct auditable row.

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_pdf_t2_codex uv run --no-sync pytest tests/postgres/test_homepage_paper_ingest_tier_evidence.py -q -n0`
  - Result after fix: passed, `5 passed in 5.43s`.
  - E2E coverage: Alembic V001-V030 migration setup, direct PDF propagation,
    per-run cap enforcement, and persisted `pipeline_issue` rows for skipped
    professor-page PDF URLs.

- `uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_pdf_t2_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.close(); print('dropped ' + name)"`
  - Result: passed; dropped temporary DB
    `miroflow_test_paper_pdf_t2_codex`.

- `uv run --no-sync ruff check src/data_agents/paper/full_text_fetcher.py src/data_agents/paper/homepage_ingest.py tests/data_agents/paper/test_full_text_fetcher.py tests/data_agents/paper/test_homepage_ingest.py tests/postgres/test_homepage_paper_ingest_tier_evidence.py`
  - Result: passed, `All checks passed!`.

Checkpoint note:
- T4 final full-text verification is completed in the final section below.

## 2026-05-23 - T3 Persistence

Scope:
- T3.1: Persist raw PDF by sha256 or approved blob reference.
- T3.2: Write extracted text to `paper_full_text` with provenance.
- T3.3: Dedupe repeated PDF fetches by sha256.
- T3.4: Add persistence tests.

TDD RED evidence:
- `uv run --no-sync pytest tests/data_agents/paper/test_raw_pdf_store.py tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_professor_page_pdf_persists_raw_blob_by_sha tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_reuses_same_raw_blob_for_duplicate_pdf_bytes tests/storage/test_paper_full_text_writer.py::test_upsert_paper_full_text_passes_all_fields tests/storage/test_v031_migration.py tests/storage/test_alembic_revision_lineage.py -q -n0`
  - Result before implementation: failed during collection because
    `src.data_agents.paper.raw_pdf_store` did not exist.

Implementation evidence:
- Added sha-addressed filesystem raw PDF storage in
  `src/data_agents/paper/raw_pdf_store.py`.
- Added Alembic V031 columns on `paper_full_text`:
  `pdf_byte_size` and `raw_pdf_storage_ref`, plus a non-unique
  `pdf_sha256` index for dedupe/audit queries.
- `FullTextExtract` now carries `pdf_byte_size` and
  `raw_pdf_storage_ref` provenance.
- `fetch_and_extract_full_text()` persists raw PDF bytes by sha before
  returning successful PDF-derived extracts.
- Repeated downloads with identical bytes reuse the same sha-addressed blob.
- `upsert_paper_full_text()` writes the new provenance fields.

Commands:

- `uv run --no-sync pytest tests/data_agents/paper/test_raw_pdf_store.py tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_professor_page_pdf_persists_raw_blob_by_sha tests/data_agents/paper/test_full_text_fetcher.py::test_fetch_reuses_same_raw_blob_for_duplicate_pdf_bytes tests/storage/test_paper_full_text_writer.py::test_upsert_paper_full_text_passes_all_fields tests/storage/test_v031_migration.py tests/storage/test_alembic_revision_lineage.py -q -n0`
  - Result after implementation: passed, `8 passed in 5.31s`.

- `uv run --no-sync pytest tests/data_agents/paper/test_full_text_fetcher.py tests/data_agents/paper/test_raw_pdf_store.py tests/storage/test_paper_full_text_writer.py tests/storage/test_v031_migration.py tests/storage/test_alembic_revision_lineage.py -q -n0`
  - First result after enabling sha validation: failed, `8 failed, 58 passed,
    3 skipped`.
  - Finding: older tests mocked `_download_pdf()` with sha values that did not
    match the mocked bytes; raw storage correctly rejected them.
  - Fix: update those mocks to use real `hashlib.sha256(pdf_bytes).hexdigest()`
    and temporary raw-PDF directories where needed.

- `uv run --no-sync pytest tests/data_agents/paper/test_full_text_fetcher.py tests/data_agents/paper/test_raw_pdf_store.py tests/storage/test_paper_full_text_writer.py tests/storage/test_v031_migration.py tests/storage/test_alembic_revision_lineage.py -q -n0`
  - Result after test correction: passed, `66 passed, 3 skipped in 28.92s`.
  - Skips: DB integration writer tests skipped because no
    `DATABASE_URL_TEST` was set in that command.

- `uv run --no-sync pytest tests/data_agents/paper/test_homepage_ingest.py -q -n0`
  - Result: passed, `19 passed in 5.69s`.

- `uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_pdf_t3_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.execute(f'CREATE DATABASE {name}'); conn.close(); print(name)"`
  - Result: passed; created temporary DB
    `miroflow_test_paper_pdf_t3_codex`.

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_pdf_t3_codex uv run --no-sync pytest tests/postgres/test_homepage_paper_ingest_tier_evidence.py tests/storage/test_paper_full_text_writer.py::test_integration_upsert_and_read_back tests/storage/test_paper_full_text_writer.py::test_integration_upsert_is_idempotent tests/storage/test_paper_full_text_writer.py::test_integration_paper_full_text_exists_real_db -q -n0`
  - First result: failed, `1 failed, 6 passed, 2 skipped`.
  - Finding: the new Postgres E2E test used dict-style row access, but this
    fixture returns tuple rows.
  - Fix: update assertions to use tuple indexes.

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_pdf_t3_codex uv run --no-sync pytest tests/postgres/test_homepage_paper_ingest_tier_evidence.py tests/storage/test_paper_full_text_writer.py::test_integration_upsert_and_read_back tests/storage/test_paper_full_text_writer.py::test_integration_upsert_is_idempotent tests/storage/test_paper_full_text_writer.py::test_integration_paper_full_text_exists_real_db -q -n0`
  - Result after fix: passed, `7 passed, 2 skipped in 5.53s`.
  - E2E coverage: Alembic V001-V031 migration setup, homepage ingest with
    direct PDF links, raw PDF blob persistence, three `paper_full_text` rows
    sharing one sha-addressed `raw_pdf_storage_ref`, and one filesystem PDF
    object for duplicate bytes.
  - Skips: two writer integration tests skipped because the temp DB had no
    pre-existing `paper` rows outside the homepage-ingest scenario.

- `uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_pdf_t3_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.close(); print('dropped ' + name)"`
  - Result: passed; dropped temporary DB
    `miroflow_test_paper_pdf_t3_codex`.

- `uv run --no-sync ruff check src/data_agents/paper/full_text_fetcher.py src/data_agents/paper/raw_pdf_store.py src/data_agents/paper/homepage_ingest.py src/data_agents/storage/postgres/paper_full_text.py alembic/versions/V031_add_paper_full_text_raw_pdf_provenance.py tests/data_agents/paper/test_full_text_fetcher.py tests/data_agents/paper/test_raw_pdf_store.py tests/data_agents/paper/test_homepage_ingest.py tests/postgres/test_homepage_paper_ingest_tier_evidence.py tests/storage/test_paper_full_text_writer.py tests/storage/test_v031_migration.py tests/storage/test_alembic_revision_lineage.py`
  - Result: passed, `All checks passed!`.

Checkpoint note:
- T4 final full-text verification is completed in the final section below.
