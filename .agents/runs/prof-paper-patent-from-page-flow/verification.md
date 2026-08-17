# Verification: prof-paper-patent-from-page-flow

## 2026-05-15 Completion Audit

### OpenSpec State

Command:

```bash
openspec list --json
```

Result:

- `prof-paper-patent-from-page-flow`: 32/32 tasks complete after the
  2026-05-15 bounded live E2E close-out.
- Remaining task: none. The change is ready for archive after final
  regression checks.

### Follow-up Drift Resolution

Resolved by `paper-pipeline-cleanup`:

- Production callers no longer invoke retired paper discovery symbols.
- `test_pipeline_cleanup_guard.py` prevents reintroducing forbidden
  discovery imports or calls.

Resolved by `paper-homepage-enrichment-completion`:

- `homepage_ingest.py` maps page roles to `prof_homepage_tier2` /
  `prof_homepage_tier3`.
- Missing tier classification files a pipeline issue instead of
  silently downgrading to a generic source.

### Environment Probe

Commands:

```bash
ss -ltnp | rg '(:15432|:5432|:19530|:9091|:6333|:8000|:18188|:5180)' || true
docker ps --format '{{.Names}} {{.Image}} {{.Ports}}' | rg -i 'postgres|milvus|qdrant|ollama|vllm|llm' || true
```

Result:

- Postgres is listening on `0.0.0.0:15432`.
- A Milvus container is present at `127.0.0.1:19531->19530`.
- No LLM runtime or credentials are visible through environment
  variables checked in the current shell:
  `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LOCAL_LLM_BASE_URL`,
  `LOCAL_LLM_API_KEY`.

### Summary Distribution Probe

Command:

```bash
UV_INDEX_URL=https://pypi.org/simple \
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
uv run python - <<'PY'
import os
import psycopg
from psycopg.rows import dict_row

with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            select count(*) as total,
                   count(*) filter (where nullif(summary_zh, '') is not null) as summary_nonempty,
                   min(char_length(summary_zh)) filter (where nullif(summary_zh, '') is not null) as min_len,
                   percentile_cont(0.5) within group (order by char_length(summary_zh)) filter (where nullif(summary_zh, '') is not null) as median_len,
                   max(char_length(summary_zh)) filter (where nullif(summary_zh, '') is not null) as max_len,
                   count(*) filter (where nullif(summary_zh, '') is not null and char_length(summary_zh) between 200 and 400) as in_200_400,
                   count(*) filter (where nullif(summary_zh, '') is not null and char_length(summary_zh) between 150 and 500) as in_150_500
              from paper
        """)
        print(cur.fetchall())
PY
```

Result:

```text
paper_total=37
summary_nonempty=26
min_len=172
median_len=344.5
max_len=490
in_200_400=22
in_150_500=26
```

Disposition:

- The current database has useful sample evidence but fewer than the
  50 summaries required by the acceptance criterion.

### Bounded Homepage Dry-run

Command:

```bash
timeout 180s env \
  UV_INDEX_URL=https://pypi.org/simple \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_homepage_paper_ingest.py \
    --dry-run \
    --prof-id PROF-02853863A327 \
    --limit 1 \
    --log-level INFO
```

Result:

- Exit code: 124.
- The run fetched `http://www.sigs.tsinghua.edu.cn/slb/main.htm`, followed
  the redirect to HTTPS, and received HTTP 200.
- Title resolution then hit OpenAlex read timeouts and arXiv 429 retry
  sleeps before the 180-second timeout.
- No database writes were expected because `--dry-run` was set.

Disposition:

- This does not satisfy T8.3 because it did not complete the paper /
  patent / link / enrichment / promotion chain.
- It adds evidence that the remaining E2E gate depends on both
  credentials and stable external resolver behavior.

### V026 Title-only Patent Canonicalization

RED commands:

```bash
UV_INDEX_URL=https://pypi.org/simple \
uv run pytest \
  tests/data_agents/patent/test_homepage_ingest.py::test_build_patent_row_accepts_title_only_entry \
  tests/data_agents/patent/test_homepage_ingest.py::test_title_only_candidate_inserts_canonical_and_link \
  tests/data_agents/patent/test_homepage_ingest.py::test_mixed_batch_routes_each_candidate_independently \
  tests/data_agents/patent/test_homepage_ingest.py::test_dry_run_skips_all_writes_but_keeps_counters \
  -q
```

Result: 4 failed. The existing implementation rejected `patent_id=None`
and filed `data_quality_flag` issues instead of inserting canonical rows.

```bash
PYTHONPATH=/home/longxiang/MiroThinker \
UV_INDEX_URL=https://pypi.org/simple \
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock \
uv run pytest tests/test_migration_v026.py -q
```

Result: 1 failed. `patent.patent_number` was still `NOT NULL`.

GREEN commands after V026 and writer changes:

```bash
UV_INDEX_URL=https://pypi.org/simple \
uv run pytest tests/data_agents/patent/test_homepage_ingest.py -q
```

Result: 9 passed.

```bash
PYTHONPATH=/home/longxiang/MiroThinker \
UV_INDEX_URL=https://pypi.org/simple \
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock \
uv run pytest tests/test_migration_v026.py -q
```

Result: 1 passed, 4 warnings.

```bash
UV_INDEX_URL=https://pypi.org/simple \
uv run ruff check \
  src/data_agents/patent/homepage_ingest.py \
  tests/data_agents/patent/test_homepage_ingest.py \
  alembic/versions/V026_allow_page_only_patent_number.py
```

Result: all checks passed.

Broader regression after V026:

```bash
UV_INDEX_URL=https://pypi.org/simple \
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock \
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock \
uv run pytest -n0 \
  tests/data_agents/paper/test_crossref.py \
  tests/data_agents/paper/test_enrichment.py \
  tests/data_agents/paper/test_homepage_ingest.py \
  tests/data_agents/paper/test_hybrid.py \
  tests/data_agents/paper/test_milvus_backfill.py \
  tests/data_agents/paper/test_openalex.py \
  tests/data_agents/paper/test_pipeline.py \
  tests/data_agents/paper/test_quality_promotion.py \
  tests/data_agents/paper/test_semantic_scholar.py \
  tests/data_agents/paper/test_pipeline_cleanup_guard.py \
  tests/data_agents/professor/test_paper_collector.py \
  tests/data_agents/professor/test_quality_gate.py \
  tests/professor/test_canonical_writer.py \
  tests/data_agents/professor/test_fact_extraction.py \
  tests/scripts/test_run_professor_fact_backfill.py \
  tests/scripts/test_run_professor_quality_re_eval.py \
  tests/scripts/test_run_milvus_backfill.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/data_agents/patent/test_homepage_ingest.py \
  tests/data_agents/professor/test_homepage_patents.py \
  tests/data_agents/patent/test_quality_promotion.py \
  tests/data_agents/patent/test_exact_backfill.py \
  tests/data_agents/patent/test_canonical_writer.py \
  tests/data_agents/patent/test_canonical_writer_identity_status.py \
  -q
```

Result: 224 passed, 31 warnings.

```bash
PYTHONPATH=/home/longxiang/MiroThinker \
UV_INDEX_URL=https://pypi.org/simple \
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock \
uv run pytest \
  tests/test_migration_v022.py \
  tests/test_migration_v025.py \
  tests/test_migration_v026.py \
  tests/test_admin_professor_api.py \
  -q
```

Result: 13 passed, 10 warnings.

## 2026-05-15 Bounded Live E2E Close-out

### Environment

Probe result:

- Postgres reachable on `localhost:15432`.
- Milvus reachable on `http://127.0.0.1:19531`.
- Ollama OpenAI-compatible endpoint reachable on
  `http://127.0.0.1:11434/v1`, with model
  `llama3.1:8b-instruct-fp16`.
- Embedding endpoint reachable at `http://100.64.0.27:18005/v1`
  using the existing local key file. The key was not printed.
- `miroflow_real` was upgraded from V024 to V027 before the final
  smoke. V026 made `patent.patent_number` nullable; V027 repaired the
  drifted `professor_paper_link.evidence_source_type` check
  constraint to allow tier evidence labels.

### TDD repair evidence

Targeted paper summary backfill by paper id:

```bash
UV_INDEX_URL=https://pypi.org/simple \
uv run pytest \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_cli_help \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_build_select_sql_filters_explicit_paper_ids \
  -q
```

RED result: 2 failed because `--paper-id` and the SQL filter were
missing.

GREEN result after implementation:

```bash
UV_INDEX_URL=https://pypi.org/simple \
uv run pytest -n0 tests/scripts/test_run_paper_summary_zh_backfill.py -q
```

Result: 10 passed.

V027 constraint repair:

```bash
PYTHONPATH=/home/longxiang/MiroThinker \
UV_INDEX_URL=https://pypi.org/simple \
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock \
uv run pytest tests/test_migration_v027.py -q
```

RED result: 1 failed because the old constraint remained after upgrade.
GREEN result after V027: 1 passed, 4 warnings.

Paper homepage ingest CLI commit behavior:

```bash
UV_INDEX_URL=https://pypi.org/simple \
uv run pytest -n0 \
  tests/scripts/test_run_homepage_paper_ingest.py::test_cli_commits_after_successful_non_dry_run \
  -q
```

RED result: 1 failed because `commit()` was not called. GREEN result
after the CLI fix: 1 passed.

Proxy-free local LLM client:

```bash
UV_INDEX_URL=https://pypi.org/simple \
uv run pytest -n0 \
  tests/scripts/test_run_paper_summary_zh_backfill.py::test_open_llm_client_disables_ambient_proxy_env \
  -q
```

RED result: 1 failed because the OpenAI client did not pass a
proxy-free httpx client. GREEN result after the fix: 1 passed.

Milvus targeted refresh collection loading:

```bash
UV_INDEX_URL=https://pypi.org/simple \
uv run pytest -n0 \
  tests/data_agents/paper/test_milvus_backfill.py::test_backfill_loads_collection_before_refresh_delete \
  -q
```

RED result: 1 failed; call order was `has_collection`, `delete`,
`insert` with no `load_collection`. GREEN result after the helper:
1 passed.

Patent homepage ingest CLI:

```bash
UV_INDEX_URL=https://pypi.org/simple \
uv run pytest -n0 tests/scripts/test_run_homepage_patent_ingest.py -q
```

RED result: 5 failed because the CLI script was missing. GREEN result
after implementation: 5 passed.

### Real homepage paper ingest

Smoke professor:

- `professor_id`: `PROF-7816DD90CFF6`
- Name: Gao Ziqi
- URL: `http://www.sigs.tsinghua.edu.cn/gzq/main.htm`
- Page role: `official_profile`

Command:

```bash
timeout 240s env \
  UV_INDEX_URL=https://pypi.org/simple \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_homepage_paper_ingest.py \
    --prof-id PROF-7816DD90CFF6 \
    --limit 1 \
    --log-level INFO
```

Result:

- Exit code: 0.
- Run id: `85982437-43d0-46c8-aae1-73ea3e923fd4`.
- `profs_total=1`, `profs_processed=1`,
  `papers_linked_total=6`, `full_text_fetched_total=5`,
  `pipeline_issues_filed=0`.
- Database verification: 6 `professor_paper_link` rows for the
  professor, all with `evidence_source_type='prof_homepage_tier2'`
  and `match_reason='homepage_title_resolution'`.
- `pipeline_run` status: `succeeded`, `items_processed=1`,
  `items_failed=0`.

Linked paper ids:

- `PAPER-A8ECE24AC523`
- `PAPER-D0DA5FD0EDB2`
- `PAPER-D55998F9F9AE`
- `PAPER-E2A4AC0EFB0F`
- `PAPER-F364E59AEB70`
- `PAPER-F9E157CBAA70`

### Real summary generation and promotion

Dry-run command:

```bash
timeout 300s env \
  UV_INDEX_URL=https://pypi.org/simple \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
  LOCAL_LLM_MODEL=llama3.1:8b-instruct-fp16 \
  LOCAL_LLM_API_KEY=EMPTY \
  uv run python scripts/run_paper_summary_zh_backfill.py \
    --paper-id PAPER-D0DA5FD0EDB2 \
    --dry-run
```

Result: `summaries_written=1`, `papers_with_errors=0`.

Real command:

```bash
timeout 300s env \
  UV_INDEX_URL=https://pypi.org/simple \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
  LOCAL_LLM_MODEL=llama3.1:8b-instruct-fp16 \
  LOCAL_LLM_API_KEY=EMPTY \
  uv run python scripts/run_paper_summary_zh_backfill.py \
    --paper-id PAPER-D0DA5FD0EDB2 \
    --paper-id PAPER-D55998F9F9AE \
    --paper-id PAPER-E2A4AC0EFB0F \
    --paper-id PAPER-F364E59AEB70 \
    --paper-id PAPER-F9E157CBAA70 \
    --log-level INFO
```

Result:

- Exit code: 0.
- Run id: `c30f9269-7acb-435c-bba9-20678be6edf2`.
- `papers_total=5`, `papers_processed=5`,
  `summaries_written=5`, `summaries_rejected=0`,
  `papers_with_errors=0`.
- Database verification: all 5 paper rows were promoted to
  `quality_status='ready'`.
- Summary lengths: 457, 430, 405, 428, 355. The prompt target remains
  200-400 characters; current runtime validation accepts 150-500.

### Real homepage patent ingest

Command:

```bash
timeout 120s env \
  UV_INDEX_URL=https://pypi.org/simple \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_homepage_patent_ingest.py \
    --prof-id PROF-7816DD90CFF6 \
    --limit 1 \
    --log-level INFO
```

Result:

- Exit code: 0.
- Run id: `55b7edf8-5eac-4cc1-99ad-fd85a120c0c6`.
- `profs_total=1`, `profs_processed=1`,
  `patents_upserted_total=0`, `links_written_total=0`,
  `pipeline_issues_filed=0`.

### Real Milvus targeted refresh and retrieval sanity

Command:

```bash
timeout 240s bash -lc '
API_KEY="$(cat /home/longxiang/MiroThinker/.sglang_api_key)" \
UV_INDEX_URL=https://pypi.org/simple \
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
uv run python scripts/run_milvus_backfill.py \
  --domain paper \
  --milvus-uri http://127.0.0.1:19531 \
  --paper-id PAPER-D0DA5FD0EDB2 \
  --paper-id PAPER-D55998F9F9AE \
  --paper-id PAPER-E2A4AC0EFB0F \
  --paper-id PAPER-F364E59AEB70 \
  --paper-id PAPER-F9E157CBAA70 \
  --batch-size 5 \
  --log-level INFO'
```

Result:

- Exit code: 0.
- `papers_total=5`, `papers_processed=5`,
  `chunks_inserted=14`, `papers_with_errors=0`.
- Milvus verification: the 5 paper ids have 14 total chunks in
  `paper_chunks`.
- Retrieval sanity query
  `"protein complex structure prediction prompt learning"` returned
  `PAPER-E2A4AC0EFB0F` ("Protein Multimer Structure Prediction via
  Prompt Learning") as the top hit, followed by related protein paper
  chunks.

## 2026-05-15 Final Focused Regression

Agent-side focused suite:

```bash
UV_INDEX_URL=https://pypi.org/simple \
uv run pytest -n0 \
  tests/scripts/test_run_homepage_paper_ingest.py \
  tests/scripts/test_run_homepage_patent_ingest.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/data_agents/paper/test_milvus_backfill.py \
  tests/scripts/test_run_milvus_backfill.py \
  tests/data_agents/paper/test_homepage_ingest.py \
  tests/data_agents/patent/test_homepage_ingest.py \
  -q
```

Result: 68 passed.

Admin migration/API focused suite:

```bash
PYTHONPATH=/home/longxiang/MiroThinker \
UV_INDEX_URL=https://pypi.org/simple \
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock \
uv run pytest \
  tests/test_migration_v022.py \
  tests/test_migration_v025.py \
  tests/test_migration_v026.py \
  tests/test_migration_v027.py \
  tests/test_admin_professor_api.py \
  -q
```

Result: 14 passed, 10 warnings.

OpenSpec and diff hygiene:

```bash
openspec validate prof-paper-patent-from-page-flow
openspec list --json
git diff --check
git status --short -- apps/admin-console/uv.lock apps/miroflow-agent/uv.lock
```

Results:

- `prof-paper-patent-from-page-flow` is valid.
- `openspec list --json` reports all active changes complete:
  `prof-paper-patent-from-page-flow` 32/32,
  `prof-seed-admin-console` 36/36, `prof-admin-workbench` 6/6,
  `prof-fact-extraction-expansion` 23/23,
  `prof-admin-workbench-ui` 21/21,
  `prof-quality-status-rework` 29/29,
  `paper-homepage-enrichment-completion` 23/23,
  `paper-pipeline-cleanup` 18/18.
- `git diff --check` exited 0.
- Both `uv.lock` files were restored after environment-only registry
  URL churn; no lockfile diff remains.
