# Verification: prof-blocked-seed-source-remediation

## 2026-05-25 Change Creation

Scope:
- Create the P5 OpenSpec change for blocked seed source remediation.
- No crawler/runtime code has been changed in this section.

Commands:

```bash
openspec new change prof-blocked-seed-source-remediation
openspec status --change prof-blocked-seed-source-remediation --json
```

Result:
- Change scaffold created at
  `openspec/changes/prof-blocked-seed-source-remediation/`.
- Schema: `spec-driven`.
- `proposal`, `design`, and `specs` were created before `tasks.md`.

Pending P5 verification:
- Source audit for seed ids 5 and 25-28.
- UESTC yjsjy adapter tests and preview/sample E2E.
- SZU CSSE official replacement audit or refreshed blocked evidence.
- P5 row-level E2E matrix.
- OpenSpec strict validation after tasks are complete.

## 2026-05-25 Source Audit

Scope:
- Complete tasks 1.1-1.3 with read-only external fetch diagnostics.
- Do not mutate `miroflow_real`.

Current seed URL diagnostic command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  python <inline source-audit script>
```

Result:

| seed_id | URL family | status | chars | Chinese chars | anchors | token markers | usable roster |
|---:|---|---:|---:|---:|---:|---|---|
| 5 | SZU CSSE current URL | 412 | 15,570 | 0 | 0 | yes | no |
| 25 | SIAS 电子信息 current URL | 202 | 2,408 | 0 | 0 | yes | no |
| 26 | SIAS 计算机技术 current URL | 202 | 2,459 | 0 | 0 | yes | no |
| 27 | SIAS 软件工程 current URL | 202 | 2,500 | 0 | 0 | yes | no |
| 28 | SIAS 机械 current URL | 202 | 2,484 | 0 | 0 | yes | no |

Browser probe for seed 5:

```bash
agent-browser --session p5-szu-csse open 'https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1'
agent-browser --session p5-szu-csse close
```

Result:
- Navigation failed with `net::ERR_CONNECTION_CLOSED`.
- Browser session closed after the probe.

UESTC yjsjy official-source diagnostic:

| seed_id | department | yjsjy query | status | Chinese chars | anchors | mentor links | first detail examples |
|---:|---|---|---:|---:|---:|---:|---|
| 25 | 电子信息 | `yxsh=28&zydm=085400` | 200 | 1,419 | 185 | 157 | 10137 张波, 10177 文岐业, 10196 方健 |
| 26 | 计算机技术 | `yxsh=28&zydm=085404` | 200 | 1,123 | 72 | 44 | 10364 张小松, 10368 蒲晓蓉, 11276 汪小芬 |
| 27 | 软件工程 | `yxsh=28&zydm=085405` | 200 | 1,030 | 35 | 7 | 10237 王治国, 11835 殷光强, 12057 李晓瑜 |
| 28 | 机械 | `yxsh=28&zydm=085500` | 200 | 1,040 | 39 | 11 | 20492 孙勇, 20493 张东星, 20494 贾沛沛 |

Representative yjsjy detail probe:
- URL:
  `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/10364?yxsh=28`
- Result: HTTP 200, title `导师个人信息 - 电子科大研招网`, 16,607 chars,
  1,106 Chinese chars.
- Text includes `电子科技大学（深圳）高等研究院`, `导师代码：10364`,
  `导师姓名：张小松`, and `职称：教授`.

SZU official candidate audit:

| Candidate | Status | Evidence | Decision |
|---|---:|---|---|
| `https://www.szu.edu.cn/szdw/jsjj.htm` | 200 | Official SZU teacher index; contains `计算机与软件学院` but only links to `https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1` | Rejected as a gateway, not a roster replacement |
| `https://aisc.szu.edu.cn/AISC/Faculty.htm` | 200 | Official AISC faculty page; 12 person detail links | Rejected as partial research-center roster, not full CSSE roster |
| `https://aisc.szu.edu.cn/` | 200 | Official AISC home; news and center navigation | Rejected as not a roster replacement |
| `https://hr.szu.edu.cn/` | 200 | Official HR page; no CSSE roster | Rejected as not a roster replacement |

Task updates:
- Tasks 1.1, 1.2, 1.3, and 1.4 marked complete in `tasks.md`.
- Source audit matrix added to `acceptance.md`.

## 2026-05-25 UESTC Adapter Implementation

Scope:
- Complete tasks 2.1-2.4 for seed ids 25-28.
- Add a named yjsjy adapter and a deterministic SIAS-to-yjsjy runtime replacement.
- Run unit checks and bounded real preview E2E against `miroflow_real`.

RED test command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/professor/test_adapter_resolution.py::test_resolves_uestc_yjsjy_mentor_roster_url_to_named_adapter \
  tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_uses_uestc_yjsjy_adapter_for_mentor_list \
  tests/postgres/test_run_single_seed.py::test_resolves_uestc_sias_seed_to_official_yjsjy_replacement \
  tests/postgres/test_run_single_seed.py::test_run_single_seed_uses_official_yjsjy_replacement_for_uestc_sias_seed
```

RED result:
- 3 failed as expected:
  - yjsjy resolver returned `None`.
  - yjsjy roster HTML fell through to the site-specific fallback.
  - `resolve_uestc_yjsjy_replacement_seed` did not exist.
- 1 skipped because neither `DATABASE_URL_TEST` nor `DATABASE_URL` was set
  for the Postgres integration fixture.

Additional RED command for original SIAS resolver coverage:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/professor/test_adapter_resolution.py::test_resolves_uestc_sias_seed_url_to_yjsjy_named_adapter
```

Additional RED result:
- Failed as expected because original SIAS URLs did not resolve to
  `uestc-yjsjy-mentor-roster`.

GREEN commands:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/professor/test_adapter_resolution.py \
  tests/data_agents/professor/test_roster_validation.py \
  tests/postgres/test_run_single_seed.py

uv run ruff check \
  src/data_agents/professor/adapter_resolution.py \
  src/data_agents/professor/roster.py \
  src/data_agents/professor/seed_runner.py \
  tests/data_agents/professor/test_adapter_resolution.py \
  tests/data_agents/professor/test_roster_validation.py \
  tests/postgres/test_run_single_seed.py
```

GREEN result:
- `124 passed, 12 skipped`.
- Skipped tests were Postgres integration tests requiring
  `DATABASE_URL_TEST` or `DATABASE_URL`.
- Ruff returned `All checks passed!`.

Real preview E2E command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python <inline run_single_seed preview script for seed ids 25-28>
```

Real preview E2E result:

| seed_id | replacement_url | resolver_result | run_id | terminal_status | diagnostic_profile_count | items processed/failed | pipeline_run_status | issue outcome |
|---:|---|---|---|---|---:|---:|---|---|
| 25 | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085400` | `uestc-yjsjy-mentor-roster` | `34c2f743-d463-4afa-8cc8-4cb040daae9f` | success | 2 | 0/0 | succeeded | historical `fetch_blocked` issue `878d0341-1de6-4b0a-aa68-3a90e032022e` retained; no new issue |
| 26 | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085404` | `uestc-yjsjy-mentor-roster` | `c5b85c83-13c2-44bc-b1b9-bc9bb2947117` | success | 2 | 0/0 | succeeded | historical `fetch_blocked` issue `588f35d0-2756-471a-a414-c1462b5e96a1` retained; no new issue |
| 27 | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085405` | `uestc-yjsjy-mentor-roster` | `93bb0708-ea6d-4520-8460-ebf43872aa22` | success | 2 | 0/0 | succeeded | historical `fetch_blocked` issue `399136c7-4a77-4b53-9896-a7b9351be8db` retained; no new issue |
| 28 | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085500` | `uestc-yjsjy-mentor-roster` | `fcee5847-5f14-4a71-a657-7d1a8fcfabeb` | success | 2 | 0/0 | succeeded | historical `fetch_blocked` issue `9efd935b-4ed7-4cbe-a720-70471dd2ac2b` retained; no new issue |

Coverage guard command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python scripts/audit_professor_seed_adapter_coverage.py
```

Coverage guard result:
- Exit code 0.
- Seed ids 25-28 now show:
  `resolver_result=uestc-yjsjy-mentor-roster`,
  `coverage_state=resolver_covered`,
  `diagnostic_status=adapter:uestc-yjsjy-mentor-roster`,
  `last_run_status=success`.
- Seed id 5 still requires the P5 SZU CSSE decision; it is not counted as
  complete by this UESTC section.

Unsupported command attempted before checking script arguments:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python scripts/audit_professor_seed_adapter_coverage.py --fail-on-missing
```

Result:
- Exit code 2.
- The script does not support `--fail-on-missing`; rerun without the flag
  produced the successful guard result above.

Task updates:
- Tasks 2.1, 2.2, 2.3, and 2.4 marked complete in `tasks.md`.
- UESTC rows in the P5 E2E matrix updated in `acceptance.md`.

## 2026-05-25 SZU CSSE Remediation And P5 Matrix

Scope:
- Complete tasks 3.1-3.4 and 4.1-4.4.
- Keep seed id 5 blocked because no official full CSSE replacement source was
  accepted.
- Refresh seed id 5 evidence and prove the open issue no longer keeps stale
  run evidence.

Pattern-repair diagnosis:
- Reported symptom: a fresh seed 5 preview run returned `fetch_blocked`, but
  the open `pipeline_issue` still showed an older run id and limit.
- Expected invariant: repeated seed-runner failures may deduplicate open
  issues, but the open issue evidence must refresh to the latest run id, mode,
  limit, and diagnostic payload.
- Defect class: L6 evidence/provenance violation plus C1 test-matrix gap.
- Sibling search: `seed_runner._file_pipeline_issue` used
  `ON CONFLICT DO NOTHING`; `quality_gate._upsert_quality_gate_issue` already
  refreshed existing evidence; other one-off issue writers are out of P5 scope.
- Fix level: Level 2 local seed-runner helper behavior.

RED commands:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/postgres/test_run_single_seed.py::test_file_pipeline_issue_refreshes_existing_open_seed_issue_evidence

uv run pytest -n0 \
  tests/postgres/test_run_single_seed.py::test_szu_csse_fetch_blocked_issue_includes_source_remediation_context
```

RED result:
- The evidence-refresh test failed because no `UPDATE pipeline_issue` call was
  made.
- The source-remediation-context test failed because seed 5 `fetch_blocked`
  evidence had no `source_remediation` payload.

GREEN commands:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/postgres/test_run_single_seed.py::test_file_pipeline_issue_refreshes_existing_open_seed_issue_evidence \
  tests/postgres/test_run_single_seed.py::test_szu_csse_fetch_blocked_issue_includes_source_remediation_context

uv run pytest -n0 \
  tests/data_agents/professor/test_adapter_resolution.py \
  tests/data_agents/professor/test_roster_validation.py \
  tests/postgres/test_run_single_seed.py

uv run ruff check \
  src/data_agents/professor/adapter_resolution.py \
  src/data_agents/professor/roster.py \
  src/data_agents/professor/seed_runner.py \
  tests/data_agents/professor/test_adapter_resolution.py \
  tests/data_agents/professor/test_roster_validation.py \
  tests/postgres/test_run_single_seed.py
```

GREEN result:
- The two focused regression tests passed.
- The targeted professor suite returned `126 passed, 12 skipped`.
- Skipped tests were Postgres integration tests requiring env DSN in the
  pytest fixture; real `miroflow_real` E2E was run separately.
- Ruff returned `All checks passed!`.

Seed 5 preview E2E command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python <inline run_single_seed preview script for seed id 5>
```

Seed 5 preview E2E result:
- `run_id=49cbea16-617e-4d25-bf6c-b10db1c3f6bb`
- `resolver_result=szu-teacher-family`
- `terminal_status=failure`
- `failure_class=fetch_blocked`
- `items_processed=0`
- `items_failed=1`
- `pipeline_run_status=failed`
- Refreshed open issue:
  `3a2f2a33-7ab9-4f1f-bed7-977cbbd23663`
- Refreshed issue evidence now contains:
  - `run_id=49cbea16-617e-4d25-bf6c-b10db1c3f6bb`
  - `trigger_mode=preview`
  - `limit=2`
  - `source_remediation.decision=official_replacement_not_found`
  - rejected candidates:
    `https://www.szu.edu.cn/szdw/jsjj.htm`,
    `https://aisc.szu.edu.cn/AISC/Faculty.htm`,
    `https://hr.szu.edu.cn/`

P5 final row-level matrix:

| seed_id | original_url | replacement_url | resolver_result | trigger_mode | terminal_status | candidate_count | items processed/failed | pipeline_run_status | issue outcome |
|---:|---|---|---|---|---|---:|---:|---|---|
| 5 | `https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1` | none accepted | `szu-teacher-family` | preview, limit 2 | failure / `fetch_blocked` | 0 | 0/1 | failed | refreshed issue `3a2f2a33-7ab9-4f1f-bed7-977cbbd23663`; source remediation context present |
| 25 | `https://sias.uestc.edu.cn/rcpy/dsjs1/dzxx2.htm` | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085400` | `uestc-yjsjy-mentor-roster` | preview, limit 2 | success | 157 source links; 2 diagnostic profiles | 0/0 | succeeded | historical `fetch_blocked` issue retained; no new issue |
| 26 | `https://sias.uestc.edu.cn/rcpy/dsjs1/jsjjs/jsjjs.htm` | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085404` | `uestc-yjsjy-mentor-roster` | preview, limit 2 | success | 44 source links; 2 diagnostic profiles | 0/0 | succeeded | historical `fetch_blocked` issue retained; no new issue |
| 27 | `https://sias.uestc.edu.cn/rcpy/dsjs1/rjgc/rjgc.htm` | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085405` | `uestc-yjsjy-mentor-roster` | preview, limit 2 | success | 7 source links; 2 diagnostic profiles | 0/0 | succeeded | historical `fetch_blocked` issue retained; no new issue |
| 28 | `https://sias.uestc.edu.cn/rcpy/dsjs1/jx/gyhlwyznzz.htm` | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085500` | `uestc-yjsjy-mentor-roster` | preview, limit 2 | success | 11 source links; 2 diagnostic profiles | 0/0 | succeeded | historical `fetch_blocked` issue retained; no new issue |

Coverage guard command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python scripts/audit_professor_seed_adapter_coverage.py
```

Coverage guard result:
- Exit code 0.
- All 20 current seed rows are `resolver_covered`.
- Seed 5 remains `last_run_status=failure` with
  `resolver_result=szu-teacher-family`.
- Seed ids 25-28 are `last_run_status=success` with
  `resolver_result=uestc-yjsjy-mentor-roster`.

Admin seed API commands:

```bash
cd apps/admin-console
uv run pytest -n0 tests/test_seeds_api.py

UV_INDEX_URL='https://pypi.org/simple' uv run pytest tests/test_seeds_api.py

UV_INDEX_URL='https://pypi.org/simple' \
  DATABASE_URL_TEST='postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock' \
  uv run pytest tests/test_seeds_api.py
```

Admin seed API results:
- First command failed before collection because uv could not fetch `hatchling`
  from the configured SUSTech mirror (`tls handshake eof`).
- Second command built successfully from official PyPI, but all 27 tests
  skipped because no test DSN was set.
- Third command ran against `miroflow_test_mock` and passed:
  `27 passed, 6 warnings`.

Task updates:
- Tasks 3.1, 3.2, 3.3, and 3.4 marked complete in `tasks.md`.
- Tasks 4.1, 4.2, 4.3, and 4.4 marked complete in `tasks.md`.
- Seed 5 and final P5 matrix evidence updated in `acceptance.md`.

## 2026-05-25 Final Validation

Commands:

```bash
openspec validate prof-blocked-seed-source-remediation --strict

openspec instructions apply --change prof-blocked-seed-source-remediation --json
```

Result:
- `openspec validate` returned:
  `Change 'prof-blocked-seed-source-remediation' is valid`.
- `openspec instructions apply` showed `16/20` complete before marking final
  validation tasks.
- Tasks 5.1, 5.2, 5.3, and 5.4 marked complete after confirming:
  - final OpenSpec validation passed;
  - targeted professor tests passed (`126 passed, 12 skipped`);
  - admin seed API tests passed against `miroflow_test_mock` (`27 passed`);
  - ruff passed for touched professor code/tests;
  - `tasks.md`, `acceptance.md`, and this verification file contain current
    P5 evidence.
