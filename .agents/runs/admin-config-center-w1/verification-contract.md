# Verification contract: add-admin-config-center (W1)

Created before production-code edits, per `openspec/config.yaml` and AGENTS.md §4 (TDD boundary).
This is a platform/operations slice: no RAG, routing, prompt, or answer behavior changes, so the
RED artifacts are unit + API-contract tests on the real route graph. A browser-level check replaces
the replay requirement because retrieval is untouched (documented as a deliberate deviation, with
the reasoning, in `.agents/runs/admin-config-center-w1/verification.md`).

## Deliverables under verification

| ID | Deliverable |
|---|---|
| D1 | `managed_config.py` — whitelist schema, defaults, atomic write, audit, env precedence |
| D2 | `GET/PATCH /api/canonical-v2/admin/config` |
| D3 | `GET /api/canonical-v2/admin/system-status` |
| D4 | `POST /api/canonical-v2/admin/providers/health-check` |
| D5 | `GET /api/canonical-v2/admin/status` repaired (no 500) |
| D6 | `admin.html` + `/admin` route + `/logs` nav link |
| D7 | `scripts/settings_status.py` consumer |

## RED artifacts (must fail before the implementation, pass after)

| ID | Artifact | Locks |
|---|---|---|
| R1 | `tests/test_managed_settings_store.py::test_defaults_when_file_missing` | D1 defaults |
| R2 | `tests/test_managed_settings_store.py::test_unknown_and_secret_keys_are_rejected` | D1 whitelist + secret rejection |
| R3 | `tests/test_managed_settings_store.py::test_atomic_write_leaves_no_residue` | D1 atomicity |
| R4 | `tests/test_managed_settings_store.py::test_audit_records_before_after_and_operator` | D1 audit |
| R5 | `tests/test_managed_settings_store.py::test_env_overrides_file` | D1 precedence |
| R6 | `tests/test_canonical_v2_admin_config_api.py::test_get_patch_get_round_trip` | D2 round trip |
| R7 | `tests/test_canonical_v2_admin_config_api.py::test_patch_rejects_unknown_and_secret_fields` | D2 4xx (422) |
| R8 | `tests/test_canonical_v2_admin_config_api.py::test_system_status_reports_degradable_blocks` | D3 |
| R9 | `tests/test_canonical_v2_admin_config_api.py::test_health_check_never_echoes_key_material` | D4 + AC5 |
| R10 | `tests/test_canonical_v2_admin_status_repair.py::test_status_degrades_without_list_for_admin` | D5 (reported defect) |
| R11 | `tests/test_canonical_v2_admin_status_repair.py::test_status_keeps_page_when_capable` | D5 no regression |
| R12 | `tests/test_canonical_v2_admin_config_api.py::test_admin_page_served` | D6 route |
| R13 | scratch-port HTTP smoke (18288) | D2/D3/D6 end-to-end |

## Oracle strength and mock boundaries

- R6–R12 exercise the **real** FastAPI route graph via `TestClient` on the app factory; only the
  *release runtime* is a test double (the same shape the existing
  `test_canonical_v2_consumer_migration.py` uses), because the live runtime requires a 5 GB serving
  pack and a running Milvus child. The double is not a mock of the code under test.
- R10 reproduces the live failure as a constructed scenario: a `gap_operations` object with
  `record`/`apply_remediation` and no `list_for_admin`, exactly like
  `_EphemeralKnowledgeGapFeedback`.
- R1–R5 run against a real temporary directory; atomicity is asserted by listing the directory and
  by patching `os.replace` to observe the call.
- The scratch smoke (R13) talks to a real uvicorn process over HTTP on port **18288**; 18188 is
  never started, restarted, or reconfigured.
- **Secret-leak oracle**: every API test asserts that the serialized response body contains no part
  of a sentinel credential longer than 4 characters, and the sentinel is generated in-process (never
  a real key).

## Explicitly out of scope for verification

- The operator CLI is exercised by running it (evidence transcript), not by a unit test, because its
  value is the end-to-end read of the real file.
- Live 18188 behavior change: the deployed service is not restarted. The before/after contrast for
  D5 is (a) the reproduced live 500 traceback from `journalctl` as *before* evidence and (b) the new
  test plus the scratch smoke as *after* evidence. Restarting the live service is forbidden by the
  slice constraints, so "the number on 18188 changes today" is **not** claimed.

## Exit criteria

- All RED artifacts pass.
- The pre-existing `apps/admin-console` suite result is captured before and after; any red is named
  and attributed (pre-existing vs introduced).
- Scratch smoke transcript and CLI transcript are stored under `.agents/runs/admin-config-center-w1/`.
- `verification.md` states, honestly, which claims are not verified (live 18188 runtime restart).
