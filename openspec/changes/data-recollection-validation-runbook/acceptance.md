# Acceptance: data-recollection-validation-runbook

## 1. Spec validation

- [x] `openspec validate data-recollection-validation-runbook` exits 0
- [x] `proposal.md`, `design.md`, `specs/`, and `tasks.md` are present
- [x] Each requirement in `specs/data-recollection-validation/spec.md`
  has at least one `#### Scenario:` block

## 2. Cleanup safety

- [x] Cleanup preview runs without deleting rows by default
- [x] Cleanup preview prints target database fingerprint, Alembic
  revision, affected tables, and affected row counts
- [x] Destructive cleanup refuses to run without explicit target
  confirmation
- [x] Cleanup scope excludes source backfills, seed definitions, schema
  history, and archived OpenSpec evidence

## 3. Bounded recollection

- [x] Sample seed batch requires explicit seed ids
- [x] Sample seed batch supports at least one limit control
- [x] Full recollection run is blocked until sample evidence exists
- [ ] Run workspace records seed ids, run ids, elapsed time, status
  transitions, counts, and failure reasons

## 4. Evidence report

- [x] Report includes seed status summary and pipeline issue taxonomy
- [x] Report includes professor quality, fact, and profile-summary
  coverage sections
- [x] Report includes paper/patent link evidence sections
- [x] Report includes paper summary readiness and promotion sections
- [x] Report includes Milvus refresh and retrieval sanity sections
- [x] Report includes final verdict separating code-path success from
  data-readiness success

## 5. Non-goals not violated

- [x] No collection semantics changed
- [x] No database schema changed
- [x] No Milvus collection schema changed
- [x] No legacy verification rows treated as authoritative quality
  evidence

## 6. Evidence

- Unit tests: `uv run pytest tests/scripts/test_run_data_recollection_validation.py -n0`
  passed with 11 tests.
- Lint: `uv run ruff check scripts/run_data_recollection_validation.py
  tests/scripts/test_run_data_recollection_validation.py` passed.
- Format: `uv run ruff format --check
  scripts/run_data_recollection_validation.py
  tests/scripts/test_run_data_recollection_validation.py` passed after
  formatting the new script.
- Run workspace:
  `.agents/runs/data-recollection-validation-runbook/20260517Tdata-recollection-apply/`
- DB cleanup dry-run against a real local verification DB is still
  blocked because `DATABASE_URL` / `DATABASE_URL_TEST` was not present
  in the verification shell.
