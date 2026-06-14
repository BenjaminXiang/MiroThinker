# Tasks: prof-seed-ops-hardening

## 1. Trigger contract

- [x] T1.1: Add `SeedTriggerRequest` with `mode` and `limit` to
  `apps/admin-console/backend/api/seeds.py`.
- [x] T1.2: Preserve empty-body compatibility as `mode="full"`.
- [x] T1.3: Reject `sample` without `limit` and reject non-positive or
  excessive limits with HTTP 422.
- [x] T1.4: Add endpoint tests for full, sample, preview, invalid
  limit, and backward-compatible empty body.

## 2. Pipeline wiring

- [x] T2.1: Pass trigger mode and limit from admin-console scheduling
  into the professor single-seed runner.
- [x] T2.2: Ensure `preview` performs fetch/parse diagnostics without
  canonical writes.
- [x] T2.3: Ensure `sample` writes at most `limit` professor bundles and
  records the selected sample scope.
- [x] T2.4: Store `trigger_mode` and `limit` in
  `pipeline_run.run_scope`.
- [x] T2.5: Add runner tests proving bounded modes do not execute an
  unbounded full crawl.

## 3. Failure taxonomy

- [x] T3.1: Classify missing adapter as `adapter_missing`.
- [x] T3.2: Classify HTTP 403/412, WAF, JavaScript challenge, browser
  connection closed, and equivalent fetch blockers as `fetch_blocked`.
- [x] T3.3: Classify successful fetch with unusable parser output as
  `parser_low_quality`.
- [x] T3.4: Classify uncaught exceptions as `pipeline_exception`.
- [x] T3.5: Persist `failure_class`, seed identity, mode, limit, and
  diagnostic sample in `pipeline_issue.evidence_snapshot`.
- [x] T3.6: Add unit tests for each failure class.

## 4. UI

- [x] T4.1: Update `apps/admin-console/frontend/src/api.ts` so
  `triggerSeed` accepts a request body.
- [x] T4.2: Add a trigger modal/popover on the Seeds page with
  `preview`, `sample`, and `full` choices.
- [x] T4.3: Default to bounded `sample` mode in the UI.
- [x] T4.4: Surface latest `failure_class` in the row status copy when
  available.
- [x] T4.5: Add frontend tests or a browser walkthrough covering sample
  trigger and full trigger confirmation.

## 5. Verification

- [x] T5.1: Run admin-console seed API tests.
- [x] T5.2: Run professor seed-runner tests.
- [x] T5.3: Run a real preview or sample trigger against a large seed
  and record that it does not run full-crawl cardinality.
- [x] T5.4: Record evidence in `acceptance.md` and
  `.agents/runs/prof-seed-ops-hardening/`.
