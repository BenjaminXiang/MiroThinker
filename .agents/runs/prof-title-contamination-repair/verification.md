# Verification: prof-title-contamination-repair

## 2026-05-25 Change Creation

Scope:
- Create the OpenSpec change needed to repair the P9 blocker reported by P8.
- No parser implementation, real-data update, publish refresh, RAG index
  refresh, duplicate merge, cleanup, deletion, or schema migration has been
  executed in this section.

Commands:

```bash
openspec new change prof-title-contamination-repair
openspec status --change prof-title-contamination-repair --json
openspec instructions proposal --change prof-title-contamination-repair --json
openspec instructions design --change prof-title-contamination-repair --json
openspec instructions specs --change prof-title-contamination-repair --json
openspec instructions tasks --change prof-title-contamination-repair --json
```

Result:
- Active change scaffold created at
  `openspec/changes/prof-title-contamination-repair/`.
- Proposal, design, specs, tasks, and acceptance skeleton were created.

Pending verification:
- OpenSpec strict validation.
- Root-cause baseline and sibling search evidence.
- RED/GREEN parser regression tests.
- Real BRESAR row remediation and P8 audit recheck.

## 2026-05-25 Baseline Tasks 1.1-1.5

Commands:

```bash
openspec validate prof-title-contamination-repair --strict
openspec instructions apply --change prof-title-contamination-repair --json
```

Results:
- Strict validation passed.
- Apply reported 23 total tasks, 0 complete, state `ready`.

Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline BRESAR and title-marker query>
```

Results:
- BRESAR, Miha row confirmed:
  `professor_id=PROF-6553974C5393`,
  `source_page.url=https://sds.cuhk.edu.cn/teacher/2238`.
- `professor_affiliation.title` is contaminated with reader metadata and body
  sections; expected title is `助理教授`.
- Sibling DB counts:
  `URL Source=19`, `Published Time=15`, `Markdown Content=19`,
  `教育背景=11`, `个人简介=17`, `学术著作=10`,
  `length(title)>80=26`, `canonical_name='教育经历'=3`.

Code path evidence:
- `profile.py` line 11 includes English `Title` in `_TITLE_LABELS`.
- `profile.py` lines 254-260 choose the first labeled title value before
  bounded site-specific fallbacks.
- `profile.py` lines 453-461 accept any text starting with a label and return
  the remainder.
- `seed_runner.py` line 566 passes `profile.title` into canonical writes.

Task updates:
- Marked tasks 1.1 through 1.5 complete after recording this evidence.

## 2026-05-25 RED Regression Tests

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_bounds_cuhk_sds_reader_markdown_title tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_rejects_reader_metadata_title_without_clean_role tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_keeps_bounded_compound_title_candidate -q
```

Result:
- Exit code 1.
- Two expected failures:
  - CUHK(SZ) SDS BRESAR reader Markdown title extracted the full metadata/body
    blob instead of `助理教授`.
  - Reader metadata without a clean role extracted the full metadata blob
    instead of `None`.
- One positive control passed:
  - Bounded compound title `教授，博士生导师` remains accepted.

Task updates:
- Marked tasks 2.1 through 2.4 complete after recording this RED evidence.

## 2026-05-25 Title Boundary GREEN

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_profile_extraction.py -q
```

Result:
- Exit code 0.
- 17 tests passed.
- The BRESAR reader Markdown fixture extracts `profile.title == "助理教授"`.
- Reader metadata without a clean role leaves `profile.title is None`.
- CUHK(SZ) SDS heading fallback works when the reader `Title:` label is
  stripped.
- Navigation headings such as `荣休教授` are ignored before the real profile
  heading.
- Compound title `教授，博士生导师` remains accepted.

Task coverage:
- 3.1, 3.2, 3.3, and 3.4.

## 2026-05-25 Writer State Regression RED/GREEN

RED command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST='postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock' \
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock' \
  uv run --no-sync pytest \
  tests/professor/test_canonical_writer.py::test_corrected_primary_affiliation_supersedes_stale_current_title_variant \
  -q --no-cov -n0
```

RED result:
- Exit code 1.
- Expected assertion failure: after writing the corrected title, both the
  corrected `助理教授` row and the stale contaminated title row were still
  `is_current=true`.

GREEN command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST='postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock' \
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock' \
  uv run --no-sync pytest \
  tests/professor/test_canonical_writer.py::test_corrected_primary_affiliation_supersedes_stale_current_title_variant \
  -q --no-cov -n0
```

GREEN result:
- Exit code 0.
- 1 test passed.
- `write_professor_bundle()` now supersedes stale current same-source primary
  title variants by setting them to `is_current=false`; it does not delete
  historical rows.

Task coverage:
- 3.5.

## 2026-05-25 Real Data Remediation

Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline run_single_seed seed_id=7 trigger_mode=full timeout=45.0>
```

Result:
- Exit code 0.
- `run_id=fa5df945-ec54-4c74-8623-28cd339884b0`.
- `status=success`.
- `failure_class=success`.
- `items_processed=98`.
- `items_failed=0`.
- `adapter_name=cuhk_teacher_search`.
- `error=None`.

Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline BRESAR affiliation query>
```

Result:
- Exit code 0.
- BRESAR, Miha has exactly one current affiliation row:
  `title=助理教授`, `is_primary=true`, `is_current=true`,
  `run_id=fa5df945-ec54-4c74-8623-28cd339884b0`,
  `source_url=https://sds.cuhk.edu.cn/teacher/2238`.
- The old `教授` row and old 7619-character contaminated row remain present
  but are now `is_current=false`.

Skipped direct page fetch:
- Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  uv run --no-sync python <inline urllib fetch and extract for https://sds.cuhk.edu.cn/teacher/2238>
```

- Result: exit code 1, `SSLV3_ALERT_HANDSHAKE_FAILURE`.
- Confidence impact: direct urllib fetch is unavailable, but the project seed
  runner crawler successfully fetched and wrote the same source page, and the
  real database row was verified after that run.

Task coverage:
- 4.1 and 4.2.

## 2026-05-25 P8 Post-Full Audit E2E

Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/run_professor_post_full_quality_audit.py
```

Result:
- Exit code 0.
- `canonical_total=2344`.
- Seed 7 latest full run is
  `fa5df945-ec54-4c74-8623-28cd339884b0`, covered, `items_processed=98`,
  `items_failed=0`.
- Known field defect `cuhk-sds-bresar-title` is `resolved`.
- `current_value_preview=助理教授`.
- `contamination_markers=[]`.
- `p9_blockers=[]`.
- `p9_readiness=ready`.

Remaining findings intentionally not fixed in this change:
- `blocked_seed_carryover=[5]` remains recorded but no longer blocks P9 in
  this audit.
- Duplicate identity risk groups remain reported.
- Open pipeline issue counts remain:
  `professor_quality_gate:affiliation:low=409`,
  `professor_quality_gate:coverage:low=2340`,
  `professor_quality_gate:research_directions:low=1757`,
  `professor_seed_runner:adapter_missing:medium=3`,
  `professor_seed_runner:discovery:high=8`.

Skipped operations:
- Publish refresh.
- RAG index refresh.
- Milvus refresh.
- Duplicate merge.
- Broad historical cleanup.
- Deletion.
- Schema migration.
- Seed-management behavior changes.

Task coverage:
- 4.3 and 4.4.

## 2026-05-25 Final Targeted Tests And Lint

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_profile_extraction.py \
  tests/data_agents/professor/test_post_full_quality_audit.py \
  tests/scripts/test_run_professor_post_full_quality_audit.py \
  tests/data_agents/professor/test_controlled_full_recollection.py \
  tests/data_agents/professor/test_recollection_readiness.py -q
```

Result:
- Exit code 0.
- 31 tests passed.

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST='postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock' \
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock' \
  uv run --no-sync pytest tests/professor/test_canonical_writer.py \
  tests/postgres/test_run_single_seed.py -q --no-cov -n0
```

Result:
- Exit code 0.
- 31 tests passed.
- 30 existing Pydantic deprecation warnings from
  `tests/professor/test_canonical_writer.py:204`.

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check \
  src/data_agents/professor/profile.py \
  src/data_agents/professor/canonical_writer.py \
  src/data_agents/professor/post_full_quality_audit.py \
  scripts/run_professor_post_full_quality_audit.py \
  tests/data_agents/professor/test_profile_extraction.py \
  tests/professor/test_canonical_writer.py \
  tests/data_agents/professor/test_post_full_quality_audit.py \
  tests/scripts/test_run_professor_post_full_quality_audit.py
```

Result:
- Exit code 0.
- All checks passed.

Task coverage:
- 5.1, 5.2, 5.3, 5.4, and 5.5.

## 2026-05-25 OpenSpec Validation

Command:

```bash
openspec validate prof-title-contamination-repair --strict
```

Result:
- Exit code 0.
- Change is valid.

Command:

```bash
openspec instructions apply --change prof-title-contamination-repair --json
```

Result before marking task 5.6:
- Exit code 0.
- 24 total tasks, 23 complete, 1 remaining.
- Remaining task was 5.6, the OpenSpec validation task itself.

Command after marking task 5.6:

```bash
openspec validate prof-title-contamination-repair --strict
openspec instructions apply --change prof-title-contamination-repair --json
```

Result:
- Exit code 0 for both commands.
- Strict validation passed.
- Apply reported 24 total tasks, 24 complete, 0 remaining, `state=all_done`.

Task coverage:
- 5.6.
