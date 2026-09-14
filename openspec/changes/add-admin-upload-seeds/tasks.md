# Tasks: add-admin-upload-seeds

## 0. Contract and evidence

- [x] 0.1 Create `.agents/runs/add-admin-upload-seeds/verification-contract.md` **before** any
      production-code edit, naming RED artifacts R1–R6 and the acceptance smoke.
      → verify: the file exists and is committed in the same commit as (or before) the first code edit.
- [x] 0.2 Record the W3 first technical verification point (legacy subprocess inside the V2 shell) in
      `.agents/runs/add-admin-upload-seeds/current-state.md` with the probe transcript.
      → verify: probe cases A–F and the orphan finding are in the file with raw JSON kept on disk.

## 1. Gate reuse (no second gate)

- [x] 1.1 Add server-resolved opaque token parameters to `JobTask` (`token_params`), with shape
      validation, resolver failure as `JobParameterError`, and refusal of a name declared in both maps.
      → verify: R1 — an injected, malformed or unknown token never yields an argv.
- [x] 1.2 Declare the W3 tasks in `JOB_TASKS` (`upload-{company,patent,professor}-import`,
      `professor-seed-refresh`) with fixed argv, cwd, timeout, gate flags and closed parameter sets.
      → verify: R1 — every declared script path exists and every argv token is fixed or a declared parameter.
- [x] 1.3 Fix the spawn helper so a timeout kills the whole process group
      (`start_new_session=True` + `os.killpg`), leaving no orphan grandchild.
      → verify: R5 — a timed-out `uv run` child leaves no surviving process.

## 2. Upload front door

- [x] 2.1 `canonical_v2/uploads.py`: `UploadStore` (SQLite ledger, schema `canonical-v2-uploads-v1`),
      newest-first listing with domain filter, bounded summary, no content/env stored.
      → verify: R2.
- [x] 2.2 `UploadRuntime.register`: domain white list, `.xlsx` + empty + size checks, sha256, reuse
      `JobLock` for the `(domain, sha256)` advisory lock, ledger dedup (409 + original id), legacy PG
      dedup when reachable, staged path under the existing upload root, ledger row.
      → verify: R3 — including concurrent admission against a held lock and the failed-then-retry case.
- [x] 2.3 Dispatch through the gate: `JobRuntime.trigger` with the upload token; record `run_id`;
      reflect `skipped` and `failed` in the ledger; do not mark succeeded before the run finishes.
      → verify: R4 — the gate's codes propagate; a switch-off upload is recorded as skipped.
- [x] 2.4 Dry-run: parse and report without writing, with no quota consumption.
      → verify: R3 — dry-run leaves the import batch count unchanged and schedules nothing.
- [x] 2.5 `apps/admin-console/scripts/run_admin_upload_import.py`: read the ledger, re-validate the
      staged path, delegate to the legacy chain per domain, emit one `{"job_summary": …}` line and
      close the ledger row.
      → verify: real-interaction smoke — a committed upload reaches `succeeded` with a parse summary.

## 3. Professor seed surface

- [x] 3.1 `apps/miroflow-agent/scripts/run_admin_seed_refresh.py`: thin CLI over `run_single_seed`
      with `--seed-id/--trigger-mode/--limit/--operator`, emitting `{"job_summary": …}`.
      → verify: R6 and the preview trigger in the real-interaction smoke.
- [x] 3.2 `canonical_v2_seeds.py`: list/read/create/update/delete reusing `backend/storage/seeds.py`,
      with the unique-URL 409 and the PG probe.
      → verify: R6.
- [x] 3.3 Seed trigger through the gate with mode/limit validation, plus run polling from the gate's
      run history.
      → verify: R6 — an unmounted mode or a missing `sample` limit is refused; the run appears in history.

## 4. Pages and wiring

- [x] 4.1 `upload.html`: domain picker, file input, dry-run/commit, upload list, upload detail with
      gate run + company batch progress; hides the commit control and explains why when PG is absent.
      → verify: served-markup assertions + the browser-free smoke.
- [x] 4.2 `seeds.html`: seed table, create/edit/delete, trigger with mode, run history.
      → verify: served-markup assertions + the smoke.
- [x] 4.3 Register routers and pages in `backend/main.py`; add the two links to the nav block of
      `browse.html`, `logs.html`, `admin.html`, `jobs.html`.
      → verify: R7 — every page carries all six links.

## 5. Verification

- [x] 5.1 New tests R1–R7 pass.
- [x] 5.2 Full `apps/admin-console` suite before/after with a failure-set diff; zero new failures.
- [x] 5.3 Real-interaction smoke on **18292** with a scratch Postgres and scratch storage: upload →
      batch status → duplicate rejected → seed CRUD → preview trigger → run visible → no-PG
      degradation; then stop the service and confirm 18292 is free.
- [x] 5.4 Record quota actually spent (expected 0 web-search / 0 LLM calls).
- [x] 5.5 `openspec validate add-admin-upload-seeds --strict` passes.

## 6. Documentation

- [x] 6.1 Register the change in `openspec/change-ledger.md`.
- [x] 6.2 `docs/plans/2026-09-14-upload-seeds-log.md` (Chinese round log) and one appended line in
      `docs/plans/index.md`.
- [x] 6.3 `.agents/runs/add-admin-upload-seeds/verification.md` with layered evidence and any gap.
