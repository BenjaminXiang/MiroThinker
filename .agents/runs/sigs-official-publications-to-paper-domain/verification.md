# Verification

## Commands Passed

- `uv run --no-sync pytest tests/data_agents/professor/test_homepage_publications_sigs.py tests/data_agents/professor/test_homepage_publications.py tests/data_agents/paper/test_homepage_ingest.py tests/scripts/test_run_homepage_paper_ingest.py tests/scripts/test_run_paper_summary_zh_backfill.py tests/scripts/test_run_sigs_rollout_report.py tests/data_agents/paper/test_title_resolver.py tests/storage/test_alembic_revision_lineage.py -q -n0 --no-cov`
  - Result: 302 passed on 2026-06-09 during checkpoint slicing.
- `uv run --no-sync pytest tests/data_agents/providers/test_openalex.py tests/data_agents/paper/test_arxiv.py tests/data_agents/paper/test_enrichment.py tests/data_agents/paper/test_openalex.py tests/data_agents/paper/test_full_text_fetcher.py tests/data_agents/paper/test_raw_pdf_store.py tests/data_agents/paper/test_milvus_backfill.py tests/scripts/test_run_milvus_backfill.py tests/storage/test_paper_full_text_writer.py tests/storage/test_milvus_collections.py -q -n0 --no-cov`
  - Result: 132 passed, 3 skipped on 2026-06-09 during checkpoint slicing. The skipped tests require `DATABASE_URL_TEST` or `DATABASE_URL` for Postgres integration checks.
- `uv run --no-sync pytest tests/storage/test_alembic_revision_lineage.py tests/storage/test_v025_migration.py tests/storage/test_v026_migration.py tests/storage/test_v028_migration.py tests/storage/test_v029_migration.py tests/storage/test_v030_migration.py tests/storage/test_v031_migration.py tests/storage/test_v032_migration.py tests/storage/test_v033_migration.py tests/storage/test_v034_migration.py tests/storage/test_v035_migration.py tests/storage/test_v036_migration.py tests/storage/test_v037_migration.py tests/storage/test_v038_migration.py tests/storage/test_v039_migration.py -q -n0 --no-cov`
  - Result: 23 passed, 14 skipped on 2026-06-09 during checkpoint slicing. The skipped tests require `DATABASE_URL_TEST` or `DATABASE_URL` for Postgres integration checks.
- `uv run --no-sync pytest tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/storage/test_milvus_collections.py tests/scripts/test_run_milvus_backfill.py -q -n0 --no-cov`
  - Result: 29 passed on 2026-06-09 during checkpoint slicing.
- `uv run pytest tests/data_agents/professor/test_homepage_publications_sigs.py tests/data_agents/professor/test_homepage_publications.py tests/data_agents/paper/test_homepage_ingest.py -q -n0 --no-cov`
  - Result: 110 passed.
- `uv run pytest tests/data_agents/professor/test_homepage_publications_sigs.py tests/data_agents/professor/test_homepage_publications.py tests/data_agents/paper/test_homepage_ingest.py tests/scripts/test_run_homepage_paper_ingest.py -q -n0 --no-cov`
  - Result: 130 passed, including cross-institution source-grounded LLM fallback tests, CLI extractor wiring, and residual author-prefix contaminated title regressions.
- `uv run pytest tests/scripts/test_run_paper_summary_zh_backfill.py -q -n0 --no-cov`
  - Result: 13 passed.
- `uv run pytest tests/scripts/test_run_milvus_backfill.py -q -n0 --no-cov`
  - Result: 14 passed.
- `uv run ruff check src/data_agents/professor/homepage_publications.py src/data_agents/paper/homepage_ingest.py tests/data_agents/professor/test_homepage_publications_sigs.py tests/data_agents/professor/test_homepage_publications.py tests/data_agents/paper/test_homepage_ingest.py`
  - Result: passed.
- `git diff --check -- apps/miroflow-agent/src/data_agents/professor/homepage_publications.py apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications_sigs.py apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications.py apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py openspec/changes/sigs-official-publications-to-paper-domain`
  - Result: passed.
- `openspec validate sigs-official-publications-to-paper-domain --strict`
  - Result: passed.

## Runtime Evidence

- SIGS rollout report checkpoint:
  - Real DB Alembic version: `V040 (head)`.
  - Read-only report command: `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/run_sigs_rollout_report.py --sample-limit 3`.
  - Read-only report result: 254 SIGS professors, 4669 linked papers, 2148 papers with English abstracts, 4 papers with `summary_zh`, 2144 abstract-bearing summary gaps, and `v040_applied=true`.
  - Full SIGS rerun after V040: not run.
  - Random SIGS sample write validation after V040: not run.
- Ahmed live parser probe:
  - URL: `https://www.sigs.tsinghua.edu.cn/Ahmed%20Elazab/main.psp`
  - Result: 9 parsed publications; all 9 titles were paper titles after parser fixes.
- Ahmed homepage paper ingest dry-run:
  - Result: 1 professor processed, 9 candidate papers linked, 0 pipeline issues, 7 resolver hits, 2 page-only fallbacks, 1 abstract-bearing paper.
  - External provider notes: arXiv fallback timed out or returned 429 for two titles.
- Ahmed real paper/link bridge:
  - Run id: `608af669-8278-4e32-97b7-7cb9c0402e55`
  - Before: 0 professor-paper links.
  - After: 9 links, 9 verified links, 9 officially listed links, 1 abstract-bearing paper, 0 summaries.
- Ahmed admin detail API:
  - URL: `http://127.0.0.1:5180/api/admin/professor/PROF-823D4761D493`
  - Result: `sections.research_output.papers` length was 9.
- Gemma4 health probe:
  - Result: three minimal chat-completion attempts returned HTTP 200 with `content='OK'`.
- Ahmed summary backfill:
  - Command: `DATABASE_URL=... uv run python scripts/run_paper_summary_zh_backfill.py --professor-id PROF-823D4761D493 --enrich-doi-metadata --log-level INFO`
  - Run id: `a9d58961-9ec3-47d0-9a0b-5eec844c8400`
  - Result: 7 candidate papers, 3 processed, 4 skipped, 3 summaries written, 0 summaries rejected, 6 metadata-enriched papers, 0 identifier contradictions, 0 pipeline issues, 0 paper errors.
  - Post-run DB check: Ahmed has 9 verified linked papers, 3 papers with `abstract_clean`, and 3 papers with `summary_zh`.
- Ahmed targeted paper Milvus refresh:
  - Command: `DATABASE_URL=... uv run python scripts/run_milvus_backfill.py --domain paper --paper-id PAPER-1E0220FE9EFB --paper-id PAPER-40DACB370EBB --paper-id PAPER-BD9B11B392C0 --batch-size 3 --milvus-uri /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db --log-level INFO`
  - Result: 3 papers processed, 6 chunks inserted, 0 errors.
- Cross-institution parser quality audit:
  - Scope: 80 official professor pages sampled through `source_page` and `professor_affiliation`.
  - Result: SUSTech sample fetched 38/38 pages, parsed 320 entries, and found 35 suspicious title candidates. Shenzhen University sample fetched 19/19 pages, parsed 304 entries, and found 22 suspicious title candidates. SIGS sample fetched 7/7 pages, parsed 122 entries, and found 2 suspicious title candidates. This confirms the parser defect class is cross-institution.
- Cross-institution read-only Gemma4 fallback probe:
  - Scope: Jiang Yuelu / SIGS, Zhang Xi / Shenzhen University, and Zhao Yan / SUSTech official pages. No database writes.
  - Result: Jiang Yuelu changed from 26 rule publications with 1 suspicious title to 39 fallback publications with 0 suspicious titles. Zhang Xi changed from 24 rule publications with 10 suspicious titles to 27 fallback publications with 0 suspicious titles. Zhao Yan changed from 13 rule publications with 1 suspicious title to 14 fallback publications with 0 suspicious titles.
- Deterministic 10-professor SIGS parser/fallback sample:
  - Scope: `md5(professor_id || 'sigs-sample-20260527')`, excluding Ahmed, institution `清华大学深圳国际研究生院`. No database writes.
  - Result: fetched 10/10 pages; 9/10 pages had publications; fallback parsed 131 clean candidates; fallback suspicious titles 0; malformed titles 0.
  - Per-professor fallback counts: Su Ping 13, Kang Feiyu 0, Peng Deli 7, Qiu Hengjia 14, Lin Lin 21, Chen Shengli 40, Vijay Kumar Pandey 8, Tan Chunyan 10, Guan Tian 10, Guo Chengyang 8.
- Partial read-only resolver dry-run for the same deterministic sample:
  - Scope completed before stop: 4/10 professors. No database writes.
  - Result: Su Ping 13 candidates / 13 resolver hits / 11 abstracts; Kang Feiyu 0 candidates and `no_publications_extracted`; Peng Deli 7 candidates / 6 resolver hits / 1 page-only fallback / 3 abstracts; Qiu Hengjia 14 candidates / 11 resolver hits / 3 page-only fallbacks / 9 abstracts.
  - Stop reason: external resolver latency plus arXiv timeout / 429 responses made the unbounded full-sample dry-run unsuitable for this interactive cleanup pass. No bad titles entered resolver after the final parser guard hardening.

## Blocked / Skipped

- Random SIGS sample resolver/write rollout:
  - Still not accepted. Parser/fallback sample is clean, but only 4/10 resolver dry-run rows completed and no real random-sample paper/link write was run.
- Full SIGS 250-professor rollout:
  - Skipped until bounded sample resolver/write validation passes and a resume checkpoint is prepared.
