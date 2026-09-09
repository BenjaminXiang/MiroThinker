# Acceptance: prof-seed-ops-hardening

## Spec validation

- [x] `openspec validate prof-seed-ops-hardening --strict` exits 0.

## Trigger contract

- [x] Empty request body remains accepted and behaves as `mode="full"`.
- [x] `mode="sample"` requires `limit`.
- [x] `mode="preview"` does not write canonical professor rows.
- [x] `mode="sample"` writes at most `limit` professor bundles.
- [x] `pipeline_run.run_scope` records `trigger_mode` and `limit`.

## Failure taxonomy

- [x] Missing adapter maps to `failure_class="adapter_missing"` and
  compatibility `last_run_status="adapter_missing"`.
- [x] HTTP 412 / WAF / JavaScript challenge maps to
  `failure_class="fetch_blocked"` and compatibility
  `last_run_status="failure"`.
- [x] Parser output below threshold maps to
  `failure_class="parser_low_quality"`.
- [x] Uncaught exception maps to `failure_class="pipeline_exception"`.
- [x] UI distinguishes the failure classes in row status copy.

## Real bounded run

- [x] A large real seed can be triggered in `preview` or `sample` mode
  without starting an unbounded full crawl.
- [x] Evidence records seed id, mode, limit, run id, final status,
  failure class if any, and elapsed time.

## Evidence

### 2026-05-23 P3 implementation verification

- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q -n0`
  in `apps/miroflow-agent`: `9 passed`.
- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_seeds_api.py tests/test_seed_cron.py -q`
  in `apps/admin-console`: `30 passed`.
- `uv run --no-sync ruff check src/data_agents/professor/seed_runner.py tests/postgres/test_run_single_seed.py`
  in `apps/miroflow-agent`: passed.
- `uv run --no-sync ruff check backend/api/seeds.py backend/storage/seeds.py tests/test_seeds_api.py tests/test_seed_cron.py`
  in `apps/admin-console`: passed.
- `just frontend-fresh` in `apps/admin-console`: TypeScript and Vite production build succeeded; Vite emitted the existing large chunk warning.
- Runtime setup for E2E: `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync alembic upgrade head`,
  then temporary backend on `127.0.0.1:18190` with cron disabled and temporary frontend on `127.0.0.1:5181`.
- API sample E2E: created seed `id=1`, `school=SUSTech`, `seed_url=https://www.sustech.edu.cn/zh/letter/`;
  triggered `POST /api/seeds/1/trigger` with `{"mode":"sample","limit":3}`.
  Run `40a81953-9252-47b2-b218-a47e3aaff08f` finished `succeeded`,
  `items_processed=3`, `items_failed=0`, `professor_rows_for_run=3`,
  `elapsed_seconds=0.068098`, `run_scope.trigger_mode="sample"`,
  `run_scope.limit=3`, `run_scope.failure_class="success"`.
- Browser walkthrough: `/seeds` trigger modal opened with `sample` selected and `limit=3`;
  choosing `full` displayed the unchecked `确认执行 full run` checkbox and `确认 full run` submit text.
  Screenshot: `/tmp/mirothinker-p3-seed-trigger-modal.png`.
- Browser sample trigger: clicked the modal's sample start path for the same seed. Latest run
  `2175cc6e-bcdf-465c-a9b4-79144b5fc0b4` finished `succeeded`,
  `items_processed=3`, `items_failed=0`, `professor_rows_for_run=3`,
  `elapsed_seconds=0.023199`, `run_scope.trigger_mode="sample"`,
  `run_scope.limit=3`, `run_scope.failure_class="success"`.
  Screenshot: `/tmp/mirothinker-p3-seeds-sample-trigger.png`.
- `openspec validate prof-seed-ops-hardening --strict`: valid.
