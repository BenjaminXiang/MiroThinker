# Verification: patent-page-only-canonical

## 2026-05-23 - T1 Storage Decision

Scope:
- T1.1 choose storage strategy.
- T1.2 record rationale in `design.md` before production behavior edits.
- T1.3 verify the reversible migration for the chosen strategy.

Decision:
- Use nullable canonical patent rows.
- Keep `patent_number` unique for numbered patents.
- Allow `patent_number=NULL` for page-only title evidence.
- V026 downgrade backfills NULL `patent_number` with `patent_id` before
  restoring NOT NULL.

Commands:
- `uv run --no-sync pytest apps/miroflow-agent/tests/storage/test_v026_migration.py -q -n0`
  - Result: failed before collection.
  - Reason: command was run from `apps/miroflow-agent` with a repository-root
    relative path.
  - Evidence: `ERROR: file or directory not found:
    apps/miroflow-agent/tests/storage/test_v026_migration.py`.
- `uv run --no-sync pytest tests/storage/test_v026_migration.py -q -n0`
  - Result: `1 passed, 3 skipped in 3.18s`.
  - Reason for skipped checks: `DATABASE_URL_TEST` and `DATABASE_URL` unset.
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_patent_v026_codex uv run --no-sync pytest tests/storage/test_v026_migration.py -q -n0`
  - Setup: created temporary database `miroflow_test_patent_v026_codex`.
  - Result: `4 passed in 4.23s`.
  - Teardown: dropped temporary database `miroflow_test_patent_v026_codex`.
- `uv run --no-sync ruff check tests/storage/test_v026_migration.py`
  - Result: `All checks passed!`
- `openspec validate patent-page-only-canonical --strict`
  - Result: `Change 'patent-page-only-canonical' is valid`.

Artifacts updated:
- `openspec/changes/patent-page-only-canonical/design.md`
- `openspec/changes/patent-page-only-canonical/tasks.md`
- `openspec/changes/patent-page-only-canonical/acceptance.md`
- `openspec/changes/patent-page-only-canonical/change-log.md`
- `apps/miroflow-agent/tests/storage/test_v026_migration.py`

Status:
- T1.1-T1.3 complete.
- T2 writer behavior remains pending.

## 2026-05-23 - T2 Writer Behavior

Scope:
- T2.1 persist title-only page patent candidates without losing evidence.
- T2.2 initialize title-only rows as `needs_enrichment`.
- T2.3 preserve numbered patent hard matching by `patent_number`.
- T2.4 prove repeated page ingest is idempotent.

RED:
- `uv run --no-sync pytest tests/data_agents/patent/test_homepage_ingest.py -q -n0`
  - Result: `5 failed, 5 passed in 4.30s`.
  - Expected failures:
    - `_build_patent_row` rejected the new `professor_id` argument for
      title-only row synthesis.
    - title-only entries still produced
      `patent_missing_registration_number` issues instead of canonical rows.
    - no `INSERT INTO patent` occurred for title-only entries.
    - mixed/dry-run counters still treated title-only entries as skipped.

GREEN:
- `uv run --no-sync pytest tests/data_agents/patent/test_homepage_ingest.py -q -n0`
  - Result: `10 passed in 3.76s`.
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_patent_t2_codex uv run --no-sync pytest tests/data_agents/patent/test_homepage_ingest.py tests/postgres/test_homepage_patent_ingest.py -q -n0`
  - Setup: created temporary database `miroflow_test_patent_t2_codex`.
  - Result: `11 passed in 4.40s`.
  - Teardown: dropped temporary database `miroflow_test_patent_t2_codex`.
- `uv run --no-sync ruff check src/data_agents/patent/homepage_ingest.py tests/data_agents/patent/test_homepage_ingest.py tests/postgres/test_homepage_patent_ingest.py tests/storage/test_v026_migration.py`
  - Result: `All checks passed!`
- `uv run --no-sync pytest tests/storage/test_v026_migration.py tests/data_agents/patent/test_homepage_ingest.py -q -n0`
  - Result: `11 passed, 3 skipped in 4.28s`.
  - Skips are DB-backed V026 scenarios with no `DATABASE_URL_TEST`; they were
    covered earlier by the temporary DB T1 command.

Evidence URL correction:
- While preparing T3, the current DB schema was rechecked against the spec
  requirement that title-only rows persist the evidence URL. The first T2
  implementation only used `source_url/source_anchor` in the title-only
  synthetic `patent_id` hash and did not expose the evidence URL in a queryable
  table column.
- RED:
  - `uv run --no-sync pytest tests/data_agents/patent/test_homepage_ingest.py::test_title_only_candidate_inserts_canonical_and_link tests/storage/test_v032_migration.py::test_v032_revision_chain -q -n0`
  - Result: `2 failed in 4.25s`.
  - Expected failures: link SQL lacked `evidence_url` / `evidence_anchor`;
    `V032_add_professor_patent_link_evidence_url.py` did not exist.
- GREEN:
  - `uv run --no-sync pytest tests/data_agents/patent/test_homepage_ingest.py::test_title_only_candidate_inserts_canonical_and_link tests/storage/test_v032_migration.py::test_v032_revision_chain tests/storage/test_alembic_revision_lineage.py -q -n0`
  - Result: `3 passed in 4.21s`.
  - `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_patent_t2_evidence_codex uv run --no-sync pytest tests/storage/test_v026_migration.py tests/storage/test_v032_migration.py tests/data_agents/patent/test_homepage_ingest.py tests/postgres/test_homepage_patent_ingest.py -q -n0`
  - Setup: created temporary database `miroflow_test_patent_t2_evidence_codex`.
  - Result: `17 passed in 7.02s`.
  - Teardown: dropped temporary database
    `miroflow_test_patent_t2_evidence_codex`.
- `uv run --no-sync ruff check src/data_agents/patent/homepage_ingest.py src/data_agents/canonical/relations.py tests/data_agents/patent/test_homepage_ingest.py tests/postgres/test_homepage_patent_ingest.py tests/storage/test_v026_migration.py tests/storage/test_v032_migration.py tests/storage/test_alembic_revision_lineage.py`
  - Result: `All checks passed!`
- `openspec validate patent-page-only-canonical --strict`
  - Result: `Change 'patent-page-only-canonical' is valid`.

Artifacts updated:
- `apps/miroflow-agent/src/data_agents/patent/homepage_ingest.py`
- `apps/miroflow-agent/src/data_agents/canonical/relations.py`
- `apps/miroflow-agent/alembic/versions/V032_add_professor_patent_link_evidence_url.py`
- `apps/miroflow-agent/tests/data_agents/patent/test_homepage_ingest.py`
- `apps/miroflow-agent/tests/postgres/test_homepage_patent_ingest.py`
- `apps/miroflow-agent/tests/storage/test_v032_migration.py`
- `apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py`
- `openspec/changes/patent-page-only-canonical/tasks.md`
- `openspec/changes/patent-page-only-canonical/acceptance.md`

Status:
- T2.1-T2.4 complete.
- T3 promotion/merge remains pending.

## 2026-05-23 - T3 Promotion / Malformed Diagnostics

Scope:
- T3.1 define promotion / merge semantics in `design.md`.
- T3.2 add promotion / merge tests.
- T3.3 keep malformed candidates diagnostic-only.

RED:
- `uv run --no-sync pytest tests/data_agents/patent/test_homepage_ingest.py::test_blank_title_candidate_files_issue_and_skips_canonical -q -n0`
  - Result: `1 failed in 3.84s`.
  - Expected failure: blank-title candidate was inserted as a canonical row.
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_patent_t3_red_codex uv run --no-sync pytest tests/postgres/test_homepage_patent_ingest.py::test_homepage_patent_ingest_promotes_title_only_when_number_appears -q -n0`
  - Setup: created temporary database `miroflow_test_patent_t3_red_codex`.
  - Result: `1 failed in 4.62s`.
  - Expected failure: later numbered page ingest inserted a new numbered row
    and left the old title-only row unmerged.
  - Teardown: dropped temporary database `miroflow_test_patent_t3_red_codex`.

GREEN:
- `uv run --no-sync pytest tests/data_agents/patent/test_homepage_ingest.py -q -n0`
  - Result: `11 passed in 3.79s`.
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_patent_t3_codex uv run --no-sync pytest tests/postgres/test_homepage_patent_ingest.py::test_homepage_patent_ingest_promotes_title_only_when_number_appears -q -n0`
  - Setup: created temporary database `miroflow_test_patent_t3_codex`.
  - Result: `1 passed in 4.30s`.
  - Teardown: dropped temporary database `miroflow_test_patent_t3_codex`.
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_patent_t3_full_codex uv run --no-sync pytest tests/storage/test_v026_migration.py tests/storage/test_v032_migration.py tests/storage/test_alembic_revision_lineage.py tests/data_agents/patent/test_homepage_ingest.py tests/postgres/test_homepage_patent_ingest.py -q -n0`
  - Setup: created temporary database `miroflow_test_patent_t3_full_codex`.
  - Result: `20 passed in 7.03s`.
  - Teardown: dropped temporary database `miroflow_test_patent_t3_full_codex`.
- `uv run --no-sync ruff check src/data_agents/patent/homepage_ingest.py src/data_agents/canonical/relations.py tests/data_agents/patent/test_homepage_ingest.py tests/postgres/test_homepage_patent_ingest.py tests/storage/test_v026_migration.py tests/storage/test_v032_migration.py tests/storage/test_alembic_revision_lineage.py`
  - Result: `All checks passed!`
- `openspec validate patent-page-only-canonical --strict`
  - Result: `Change 'patent-page-only-canonical' is valid`.

Artifacts updated:
- `openspec/changes/patent-page-only-canonical/design.md`
- `openspec/changes/patent-page-only-canonical/tasks.md`
- `openspec/changes/patent-page-only-canonical/acceptance.md`
- `openspec/changes/patent-page-only-canonical/change-log.md`
- `apps/miroflow-agent/src/data_agents/patent/homepage_ingest.py`
- `apps/miroflow-agent/tests/data_agents/patent/test_homepage_ingest.py`
- `apps/miroflow-agent/tests/postgres/test_homepage_patent_ingest.py`

Status:
- T3.1-T3.3 complete.
- T4 verification remains pending.

## 2026-05-23 - T4 Final Verification

Scope:
- T4.1 run patent homepage ingest tests.
- T4.2 run migration/schema tests.
- T4.3 run a bounded page sample containing title-only patents.

Commands:
- `uv run --no-sync pytest tests/data_agents/professor/test_homepage_patents.py tests/data_agents/patent/test_homepage_ingest.py -q -n0`
  - Result: `23 passed in 3.94s`.
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_patent_t4_codex uv run --no-sync pytest tests/storage/test_v026_migration.py tests/storage/test_v032_migration.py tests/storage/test_alembic_revision_lineage.py tests/postgres/test_homepage_patent_ingest.py -q -n0`
  - Setup: created temporary database `miroflow_test_patent_t4_codex`.
  - Result: `9 passed in 6.84s`.
  - Teardown: dropped temporary database `miroflow_test_patent_t4_codex`.
- `uv run --no-sync ruff check src/data_agents/patent/homepage_ingest.py src/data_agents/canonical/relations.py tests/data_agents/professor/test_homepage_patents.py tests/data_agents/patent/test_homepage_ingest.py tests/postgres/test_homepage_patent_ingest.py tests/storage/test_v026_migration.py tests/storage/test_v032_migration.py tests/storage/test_alembic_revision_lineage.py`
  - Result: `All checks passed!`

Bounded sample note:
- T4.3 used the synthetic bounded homepage sample in
  `tests/postgres/test_homepage_patent_ingest.py`, including title-only patent
  evidence and later numbered promotion. This is not claimed as a live external
  crawl.

Status:
- T4.1-T4.3 complete.
