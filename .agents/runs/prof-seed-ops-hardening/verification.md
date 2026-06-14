# Verification: prof-seed-ops-hardening

## 2026-05-23 P3 close-out

### Scope

- Change: `openspec/changes/prof-seed-ops-hardening/`
- Capability: `professor-seed-ops-hardening`
- Runtime DB: `postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock`
- Temporary backend: `http://127.0.0.1:18190`
- Temporary frontend: `http://127.0.0.1:5181`

### RED checks

- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q -n0`
  in `apps/miroflow-agent` failed before implementation with missing
  `failure_class` and missing `trigger_mode` / `limit` parameters.
- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_seeds_api.py -q -k trigger`
  in `apps/admin-console` failed before implementation because scheduler
  calls did not include `trigger_mode` / `limit` and invalid sample limits
  were accepted.

### Automated verification

- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q -n0`
  in `apps/miroflow-agent`: `9 passed`.
- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_seeds_api.py tests/test_seed_cron.py -q`
  in `apps/admin-console`: `30 passed`.
- `uv run --no-sync ruff check src/data_agents/professor/seed_runner.py tests/postgres/test_run_single_seed.py`
  in `apps/miroflow-agent`: `All checks passed`.
- `uv run --no-sync ruff check backend/api/seeds.py backend/storage/seeds.py tests/test_seeds_api.py tests/test_seed_cron.py`
  in `apps/admin-console`: `All checks passed`.
- `just frontend-fresh` in `apps/admin-console`: TypeScript and Vite
  production build succeeded. Vite emitted the existing large chunk warning.
- `openspec validate prof-seed-ops-hardening --strict`: valid.

### Real bounded run E2E

Runtime setup:

- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync alembic upgrade head`
  in `apps/miroflow-agent`.
- Temporary backend:
  `ADMIN_PROFESSOR_SEED_CRON_ENABLED=0 DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync uvicorn backend.main:app --host 127.0.0.1 --port 18190`
  in `apps/admin-console`.
- Temporary frontend:
  `VITE_API_PROXY_TARGET=http://127.0.0.1:18190 npm run dev -- --host 127.0.0.1 --port 5181`
  in `apps/admin-console/frontend`.

API sample trigger:

- Seed: `id=1`, `school=SUSTech`,
  `seed_url=https://www.sustech.edu.cn/zh/letter/`.
- Request: `POST /api/seeds/1/trigger` with `{"mode":"sample","limit":3}`.
- Run: `40a81953-9252-47b2-b218-a47e3aaff08f`.
- Final DB state: `pipeline_run.status=succeeded`,
  `items_processed=3`, `items_failed=0`, `professor_rows_for_run=3`,
  `elapsed_seconds=0.068098`.
- Scope evidence: `run_scope.trigger_mode="sample"`, `run_scope.limit=3`,
  `run_scope.failure_class="success"`,
  `run_scope.written_profile_count=3`,
  `run_scope.diagnostic_profile_count=3`.

Browser sample trigger:

- Browser opened `http://127.0.0.1:5181/seeds`.
- Trigger modal opened with `sample` checked and `limit=3`.
- Switching to `full` displayed an unchecked `确认执行 full run` checkbox
  and `确认 full run` submit text.
- Screenshot: `/tmp/mirothinker-p3-seed-trigger-modal.png`.
- Clicking the sample start path created latest run
  `2175cc6e-bcdf-465c-a9b4-79144b5fc0b4`.
- Final DB state: `pipeline_run.status=succeeded`,
  `items_processed=3`, `items_failed=0`, `professor_rows_for_run=3`,
  `elapsed_seconds=0.023199`.
- Scope evidence: `run_scope.trigger_mode="sample"`, `run_scope.limit=3`,
  `run_scope.failure_class="success"`.
- UI returned to one success row after polling.
- Screenshot: `/tmp/mirothinker-p3-seeds-sample-trigger.png`.

### Cleanup

- Browser session closed with `agent-browser close`.
- Temporary backend and frontend processes were stopped.
