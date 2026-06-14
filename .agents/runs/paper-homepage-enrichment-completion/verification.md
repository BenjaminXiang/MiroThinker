# Verification: paper-homepage-enrichment-completion

## 2026-05-23 T1 Tier Evidence

### Scope

- Implemented T1.1-T1.4 only.
- Source page `page_role` now flows into `paper.homepage_ingest`.
- Page roles `official_profile` and `official_publication_page` map to
  `prof_homepage_tier2`.
- Page roles `personal_homepage` and `lab_homepage` map to
  `prof_homepage_tier3`.
- Missing or unmappable page roles file `pipeline_issue` with
  `stage="paper_attribution"` and do not write a generic
  `personal_homepage` professor-paper link.

### RED checks

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/paper/test_homepage_ingest.py -q -n0
```

Result: failed as expected before implementation.

Evidence:

- `test_official_profile_evidence_source_type_is_tier2` failed because
  current code emitted `personal_homepage`.
- `test_personal_homepage_evidence_source_type_is_tier3` failed because
  current code emitted `personal_homepage`.
- `test_missing_homepage_tier_files_issue_without_generic_link` failed
  because current code still linked one paper instead of filing only the
  missing-tier issue.

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/test_professor_paper_link_tier_contract.py -q -n0
```

Result: failed as expected before enum/policy update.

Evidence:

- `ProfessorPaperLink` rejected `prof_homepage_tier2`.
- `PROFESSOR_PAPER_LINK_PROMOTION.allowed_evidence_sources` did not
  include `prof_homepage_tier2`.

### GREEN checks

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/paper/test_homepage_ingest.py -q -n0
```

Result: passed, `16 passed`.

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/test_professor_paper_link_tier_contract.py tests/data_agents/paper/test_homepage_ingest.py -q -n0
```

Result: passed, `18 passed`.

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/scripts/test_run_homepage_paper_ingest.py -q -n0
```

Result: passed, `8 passed`.

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/test_run_id_wiring.py tests/professor/test_canonical_writer.py -q -n0
```

Result: passed with database-gated skips, `16 passed, 14 skipped`.

Skipped tests:

- `tests/professor/test_canonical_writer.py` Postgres integration tests
  skipped because neither `DATABASE_URL_TEST` nor `DATABASE_URL` was set
  for that command.

### Bounded E2E

Temporary database:

```text
postgresql://miroflow:miroflow@localhost:15432/miroflow_test_homepage_tier_codex
```

Setup command:

```bash
cd apps/miroflow-agent
uv run --no-sync python -c "import psycopg; name='miroflow_test_homepage_tier_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.execute(f'CREATE DATABASE {name}'); conn.close(); print(name)"
```

Result: created `miroflow_test_homepage_tier_codex`.

E2E command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_homepage_tier_codex uv run --no-sync pytest tests/postgres/test_homepage_paper_ingest_tier_evidence.py -q -n0
```

Result: passed, `3 passed`.

Coverage:

- Migrated a fresh Postgres database from base through V030.
- Ran real `run_homepage_paper_ingest`.
- Wrote real `paper` and `professor_paper_link` rows for
  `official_profile -> prof_homepage_tier2`.
- Wrote real `paper` and `professor_paper_link` rows for
  `personal_homepage -> prof_homepage_tier3`.
- Wrote real `pipeline_issue` with `stage="paper_attribution"` and
  `issue_type="missing_homepage_tier"` for an unmappable `unknown`
  page role.

Cleanup command:

```bash
cd apps/miroflow-agent
uv run --no-sync python -c "import psycopg; name='miroflow_test_homepage_tier_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.close(); print('dropped ' + name)"
```

Result: dropped `miroflow_test_homepage_tier_codex`.

### Spec validation

Command:

```bash
openspec validate paper-homepage-enrichment-completion --strict
```

Result: passed, `Change 'paper-homepage-enrichment-completion' is valid`.

## 2026-05-23 T3 Identifier Contradictions

### Scope

- Implemented T3.1-T3.5.
- Added structured `PaperIdentifierContradiction` metadata.
- Enrichment now detects DOI and arXiv id mismatches without
  overwriting the canonical identifier.
- Summary backfill writes open `pipeline_issue` rows with existing
  stage value `paper_quality`.
- Rows with unresolved identifier contradictions are written as
  `needs_review`, blocking automatic `ready` promotion for that run.

### RED checks

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/paper/test_enrichment.py tests/scripts/test_run_paper_summary_zh_backfill.py -q -n0
```

Result: failed as expected before implementation.

Evidence:

- `tests/data_agents/paper/test_enrichment.py` could not import
  `PaperIdentifierContradiction`.

### GREEN checks

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/paper/test_enrichment.py tests/scripts/test_run_paper_summary_zh_backfill.py -q -n0
```

Result: passed, `29 passed`.

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/paper/test_openalex.py tests/data_agents/paper/test_crossref.py tests/data_agents/paper/test_semantic_scholar.py tests/data_agents/paper/test_arxiv.py tests/data_agents/paper/test_enrichment.py tests/scripts/test_run_paper_summary_zh_backfill.py -q -n0
```

Result: passed, `43 passed`.

### Bounded E2E

Temporary database:

```text
postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_t3_codex
```

Setup command:

```bash
cd apps/miroflow-agent
uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_t3_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.execute(f'CREATE DATABASE {name}'); conn.close(); print(name)"
```

Result: created `miroflow_test_paper_t3_codex`.

E2E command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_t3_codex uv run --no-sync pytest tests/postgres/test_paper_summary_arxiv_enrichment_e2e.py -q -n0
```

Result: passed, `2 passed`.

Coverage:

- Migrated a fresh Postgres database from base through V030.
- Verified the arXiv-only metadata enrichment sample still writes real
  `abstract_clean`, `venue`, and `summary_zh`.
- Triggered a DOI identifier contradiction through the summary backfill
  CLI main flow.
- Verified a real `pipeline_issue` row with
  `stage="paper_quality"`, `issue_type="identifier_contradiction"`,
  and the conflicting source value in `evidence_snapshot`.
- Verified the paper row was not promoted to `ready`; it ended as
  `quality_status="needs_review"`.

Cleanup command:

```bash
cd apps/miroflow-agent
uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_t3_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.close(); print('dropped ' + name)"
```

Result: dropped `miroflow_test_paper_t3_codex`.

### Lint

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check src/data_agents/paper/enrichment.py src/data_agents/paper/arxiv.py src/data_agents/paper/models.py src/data_agents/paper/openalex.py src/data_agents/paper/crossref.py src/data_agents/paper/semantic_scholar.py scripts/run_paper_summary_zh_backfill.py tests/data_agents/paper/test_enrichment.py tests/scripts/test_run_paper_summary_zh_backfill.py tests/postgres/test_paper_summary_arxiv_enrichment_e2e.py
```

Result: passed, `All checks passed!`.

## 2026-05-23 T4/T5 Summary-to-Milvus Refresh

### Scope

- Implemented T4.1-T4.4 and T5.1-T5.5.
- Chosen refresh signal contract:
  - `run_paper_summary_zh_backfill.py` writes `paper.summary_zh` and
    updates `paper.updated_at = now()`.
  - `run_milvus_backfill.py --domain paper --changed-since <timestamp>`
    selects paper rows by `paper.updated_at`.
  - `run_milvus_backfill.py --domain paper --paper-id <paper_id>` can
    refresh exact affected rows.
- No schema migration or pending-marker table was introduced.

### RED checks

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/paper/test_milvus_backfill.py tests/scripts/test_run_milvus_backfill.py tests/postgres/test_paper_summary_milvus_refresh_e2e.py -q -n0
```

Result: failed as expected before implementation.

Evidence:

- `test_backfill_can_target_specific_paper_ids` failed with
  `TypeError: backfill_paper_chunks() got an unexpected keyword argument
  'paper_ids'`.
- `test_backfill_can_select_papers_changed_since_updated_at` failed with
  `TypeError: backfill_paper_chunks() got an unexpected keyword argument
  'changed_since'`.
- `test_cli_help_exits_zero` failed because `--paper-id` was missing
  from CLI help.
- `test_cli_passes_paper_ids_and_changed_since_to_paper_backfill`
  failed because argparse rejected `--paper-id` and `--changed-since`.
- The Postgres E2E in this first RED command skipped because no
  `DATABASE_URL_TEST` or `DATABASE_URL` was set for that command.

### GREEN checks

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/paper/test_milvus_backfill.py tests/scripts/test_run_milvus_backfill.py -q -n0
```

Result: passed, `26 passed`.

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/paper/test_openalex.py tests/data_agents/paper/test_crossref.py tests/data_agents/paper/test_semantic_scholar.py tests/data_agents/paper/test_arxiv.py tests/data_agents/paper/test_enrichment.py tests/scripts/test_run_paper_summary_zh_backfill.py tests/data_agents/paper/test_milvus_backfill.py tests/scripts/test_run_milvus_backfill.py -q -n0
```

Result: passed, `69 passed`.

Coverage:

- Focused paper enrichment providers and hybrid merge tests.
- Paper summary backfill unit/CLI tests.
- Paper Milvus backfill worker tests.
- `run_milvus_backfill.py` CLI routing tests for paper, professor,
  company, and patent paths.

### Bounded E2E

Temporary database:

```text
postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_t4_codex
```

Setup command:

```bash
cd apps/miroflow-agent
uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_t4_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.execute(f'CREATE DATABASE {name}'); conn.close(); print(name)"
```

Result: created `miroflow_test_paper_t4_codex`.

E2E command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_t4_codex uv run --no-sync pytest tests/postgres/test_paper_summary_milvus_refresh_e2e.py -q -n0
```

Result: passed, `1 passed`.

Coverage:

- Migrated a fresh Postgres database from base through V030.
- Inserted a paper row with English abstract and no `summary_zh`.
- Ran the real summary backfill CLI main flow with patched LLM calls.
- Verified `summary_zh` was written and `paper.updated_at` was at or
  after the pre-write refresh timestamp.
- Ran `backfill_paper_chunks(..., changed_since=<refresh_floor>)`.
- Verified the affected paper was selected, old Milvus chunks were
  deleted by `paper_id`, and the new abstract chunk text contained the
  new Chinese summary.

Cleanup command:

```bash
cd apps/miroflow-agent
uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_t4_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.close(); print('dropped ' + name)"
```

Result: dropped `miroflow_test_paper_t4_codex`.

Combined bounded E2E temporary database:

```text
postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_t5_codex
```

Setup command:

```bash
cd apps/miroflow-agent
uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_t5_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.execute(f'CREATE DATABASE {name}'); conn.close(); print(name)"
```

Result: created `miroflow_test_paper_t5_codex`.

E2E command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_t5_codex uv run --no-sync pytest tests/postgres/test_paper_summary_arxiv_enrichment_e2e.py tests/postgres/test_paper_summary_milvus_refresh_e2e.py -q -n0
```

Result: passed, `3 passed`.

Coverage:

- Re-ran arXiv enrichment E2E.
- Re-ran identifier contradiction E2E.
- Re-ran summary-to-Milvus targeted refresh E2E.

Cleanup command:

```bash
cd apps/miroflow-agent
uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_t5_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.close(); print('dropped ' + name)"
```

Result: dropped `miroflow_test_paper_t5_codex`.

### Lint

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check src/data_agents/paper/milvus_backfill.py scripts/run_milvus_backfill.py scripts/run_paper_summary_zh_backfill.py tests/data_agents/paper/test_milvus_backfill.py tests/scripts/test_run_milvus_backfill.py tests/scripts/test_run_paper_summary_zh_backfill.py tests/postgres/test_paper_summary_arxiv_enrichment_e2e.py tests/postgres/test_paper_summary_milvus_refresh_e2e.py
```

Result: passed, `All checks passed!`.

### Rebuild order

1. Run page-first paper ingest.
2. Run paper metadata enrichment and `summary_zh` generation.
3. Let paper quality promotion evaluate enriched rows.
4. Run paper Milvus refresh with `--paper-id` for exact rows or
   `--changed-since` from the pre-summary/enrichment timestamp.
5. Run retrieval validation against refreshed paper chunks.

### Final artifact checks

Command:

```bash
openspec validate paper-homepage-enrichment-completion --strict
```

Result: passed, `Change 'paper-homepage-enrichment-completion' is valid`.

Command:

```bash
openspec instructions apply --change paper-homepage-enrichment-completion --json
```

Result: `progress.total=23`, `progress.complete=23`,
`progress.remaining=0`, `state="all_done"`.

Command:

```bash
git diff --check -- apps/miroflow-agent/src/data_agents/paper/milvus_backfill.py apps/miroflow-agent/scripts/run_milvus_backfill.py apps/miroflow-agent/tests/data_agents/paper/test_milvus_backfill.py apps/miroflow-agent/tests/scripts/test_run_milvus_backfill.py apps/miroflow-agent/tests/postgres/test_paper_summary_milvus_refresh_e2e.py openspec/changes/paper-homepage-enrichment-completion/tasks.md openspec/changes/paper-homepage-enrichment-completion/acceptance.md .agents/runs/paper-homepage-enrichment-completion/verification.md
```

Result: passed with exit code 0 and no whitespace errors reported.

### Spec validation

Command:

```bash
openspec validate paper-homepage-enrichment-completion --strict
```

Result: passed, `Change 'paper-homepage-enrichment-completion' is valid`.

Final artifact update re-check:

```bash
openspec validate paper-homepage-enrichment-completion --strict
```

Result: passed, `Change 'paper-homepage-enrichment-completion' is valid`.

### Lint

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check src/data_agents/paper/homepage_ingest.py src/data_agents/canonical/common.py src/data_agents/quality/threshold_config.py tests/data_agents/paper/test_homepage_ingest.py tests/data_agents/test_professor_paper_link_tier_contract.py tests/postgres/test_homepage_paper_ingest_tier_evidence.py
```

Result: passed, `All checks passed!`.

### Spec validation

Command:

```bash
openspec validate paper-homepage-enrichment-completion --strict
```

Result: passed, `Change 'paper-homepage-enrichment-completion' is valid`.

## 2026-05-23 T2 Enrichment Fallback

### Scope

- Implemented T2.1-T2.5.
- Added arXiv metadata enrichment by arXiv id.
- Extended `PaperMetadataEnrichment` with structured author metadata.
- Merged authors by source priority while preserving ORCID-bearing
  identities from stronger sources.
- Kept `citation_count` OpenAlex-only across Crossref, Semantic
  Scholar, and arXiv fallback.
- Updated summary backfill selection so arXiv-only paper rows can use
  metadata enrichment before summary generation.

### RED checks

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/paper/test_enrichment.py tests/data_agents/paper/test_arxiv.py tests/scripts/test_run_paper_summary_zh_backfill.py -q -n0
```

Result: failed as expected before implementation.

Evidence:

- `tests/data_agents/paper/test_enrichment.py` could not import
  `PaperAuthorMetadata`.
- `tests/data_agents/paper/test_arxiv.py` could not import
  `src.data_agents.paper.arxiv`.

### GREEN checks

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/paper/test_enrichment.py tests/data_agents/paper/test_arxiv.py tests/scripts/test_run_paper_summary_zh_backfill.py -q -n0
```

Result: passed, `27 passed`.

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/paper/test_openalex.py tests/data_agents/paper/test_crossref.py tests/data_agents/paper/test_semantic_scholar.py tests/data_agents/paper/test_doi_enrichment.py tests/data_agents/paper/test_enrichment.py tests/data_agents/paper/test_arxiv.py tests/scripts/test_run_paper_summary_zh_backfill.py -q -n0
```

Result: passed, `42 passed`.

### Bounded E2E

Temporary database:

```text
postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_arxiv_e2e_codex
```

Setup command:

```bash
cd apps/miroflow-agent
uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_arxiv_e2e_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.execute(f'CREATE DATABASE {name}'); conn.close(); print(name)"
```

Result: created `miroflow_test_paper_arxiv_e2e_codex`.

E2E command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_paper_arxiv_e2e_codex uv run --no-sync pytest tests/postgres/test_paper_summary_arxiv_enrichment_e2e.py -q -n0
```

Result: passed, `1 passed`.

Coverage:

- Migrated a fresh Postgres database from base through V030.
- Inserted an arXiv-only paper row with no abstract.
- Ran the summary backfill CLI main flow with DOI/arXiv metadata
  enrichment enabled.
- Wrote real `paper.abstract_clean`, `paper.venue`, and
  `paper.summary_zh` values.
- Verified the resulting paper quality status stayed consistent with
  the current promotion rule (`partial` for this bounded sample).

Cleanup command:

```bash
cd apps/miroflow-agent
uv run --no-sync python -c "import psycopg; name='miroflow_test_paper_arxiv_e2e_codex'; conn=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/postgres', autocommit=True); conn.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'); conn.close(); print('dropped ' + name)"
```

Result: dropped `miroflow_test_paper_arxiv_e2e_codex`.

### Lint

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check src/data_agents/paper/enrichment.py src/data_agents/paper/arxiv.py src/data_agents/paper/models.py scripts/run_paper_summary_zh_backfill.py tests/data_agents/paper/test_enrichment.py tests/data_agents/paper/test_arxiv.py tests/scripts/test_run_paper_summary_zh_backfill.py tests/postgres/test_paper_summary_arxiv_enrichment_e2e.py
```

Result: passed, `All checks passed!`.
