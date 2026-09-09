# Change Log: prof-admin-workbench-ui

## 2026-05-14 — Child scaffolded

- Created the child OpenSpec artifact set from the
  `prof-admin-workbench` parent.
- Sequenced this child after the backend quality rework and fact
  backfill so the UI can render both diagnosis and populated canonical
  facts where available.
- Added explicit API-test-first and child-spec review gates.

## 2026-05-23 — Review gate decisions recorded

- Re-reviewed this child after the upstream quality, fact-extraction,
  lifecycle, and schema changes were archived and `miroflow_real` was upgraded
  to V032.
- Confirmed actor source for marking actions: explicit request-body `actor`
  with default `admin-console` until auth exists.
- Confirmed frontend route strategy: keep `/:domain/:id`, render the professor
  workbench for `domain === "professor"`, and keep generic detail for other
  domains.

## 2026-05-23 — Real-schema walkthrough repair

- Browser preflight against a migrated V032 Postgres database found that
  `/api/admin/professor/{id}` selected a nonexistent physical
  `professor.email` column.
- Repaired the detail query to derive contact email from active
  `professor_fact` rows with `fact_type = 'contact'`, matching the canonical
  writer contract.
- Added a migrated-schema regression covering detail, marking audit rows, and
  generic professor quality-edit bypass rejection.
