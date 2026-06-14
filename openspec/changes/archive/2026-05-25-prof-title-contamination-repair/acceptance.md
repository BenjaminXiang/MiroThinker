# Acceptance: prof-title-contamination-repair

## Status

| Requirement | Status | Evidence |
|---|---|---|
| Professor title fields are bounded academic role phrases | Verified | Profile extraction regression tests passed; real seed 7 rerun extracted and wrote `助理教授`. |
| Contaminated title candidates are rejected before canonical writes | Verified | RED/GREEN profile tests passed; writer regression proves stale current title variants are superseded. |
| Known title blocker is re-verified against real data | Verified | `miroflow_real` has one current BRESAR affiliation and its title is exactly `助理教授`. |
| P8 known field defects can be rechecked after remediation | Verified | P8 post-full audit reports `cuhk-sds-bresar-title` resolved and `p9_blockers=[]`. |

## Scope Boundary

This change may repair Professor title/position extraction and run targeted
real-data remediation for BRESAR, Miha. It must not perform publish refresh,
RAG index refresh, duplicate merge, broad historical cleanup, deletion, schema
migration, or seed-management behavior changes.

## Pending Evidence

- Active change and root-cause baseline.
- RED title-contamination regression tests.
- GREEN profile extraction and audit tests.
- Targeted real-row verification for BRESAR, Miha.
- P8 post-full audit recheck showing `cuhk-sds-bresar-title` resolved.

## 2026-05-25 Baseline And Root-Cause Evidence

Commands:

```bash
openspec validate prof-title-contamination-repair --strict
openspec instructions apply --change prof-title-contamination-repair --json
```

Results:
- Strict validation passed.
- Apply reported 23 total tasks, 0 complete, state `ready`.

Real data baseline command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline BRESAR and title-marker query>
```

Results:
- BRESAR, Miha exists as `PROF-6553974C5393`.
- `source_page.url=https://sds.cuhk.edu.cn/teacher/2238`.
- `professor_affiliation.title` is contaminated with the reader page title,
  `URL Source`, `Published Time`, `Markdown Content`, navigation text,
  `教育背景`, `学术领域`, `研究领域`, `个人简介`, and `学术著作`.
- Current expected title remains `助理教授`.

Sibling data findings:
- `professor_affiliation.title` rows containing `URL Source`: 19.
- Rows containing `Published Time`: 15.
- Rows containing `Markdown Content`: 19.
- Rows containing `教育背景`: 11.
- Rows containing `个人简介`: 17.
- Rows containing `学术著作`: 10.
- Rows with title length greater than 80 characters: 26.
- `professor.canonical_name='教育经历'`: 3 rows.

Root-cause path:
- `profile.py` defines `_TITLE_LABELS = ("职位", "职称", "Title")`.
- `extract_professor_profile()` selects
  `_extract_first_labeled_value(text_samples, _TITLE_LABELS)` as the first
  title source before SUSTech/SIGS bounded fallbacks.
- `_extract_labeled_value()` accepts any normalized text that starts with the
  label and returns `_clean_value(normalized[len(label):])`.
- Reader Markdown metadata can start with `Title: ... URL Source: ...
  Published Time: ... Markdown Content: ...`, so the English metadata title can
  be promoted into `profile.title`.
- `seed_runner._merged_to_enriched()` passes `profile.title` through to the
  canonical writer, which then persists it as `professor_affiliation.title`.

Pattern classification:
- Defect class: L3 Missing Shared Helper / Boundary Guard + C1 Test-Matrix Gap.
- Fix level remains Level 3: shared Professor title boundary guard plus
  extractor integration.

## 2026-05-25 RED Regression Evidence

Command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_bounds_cuhk_sds_reader_markdown_title \
  tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_rejects_reader_metadata_title_without_clean_role \
  tests/data_agents/professor/test_profile_extraction.py::test_extract_professor_profile_keeps_bounded_compound_title_candidate -q
```

RED result:
- `test_extract_professor_profile_bounds_cuhk_sds_reader_markdown_title`
  failed because the extracted title was the reader metadata and full Markdown
  body instead of `助理教授`.
- `test_extract_professor_profile_rejects_reader_metadata_title_without_clean_role`
  failed because the extracted title was the reader metadata blob instead of
  `None`.
- `test_extract_professor_profile_keeps_bounded_compound_title_candidate`
  passed, proving the positive compound-title expectation is already covered
  and must remain green after the guard.

## 2026-05-25 GREEN Implementation Evidence

Commands:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_profile_extraction.py -q
```

Result:
- Exit code 0.
- 17 profile extraction tests passed, including:
  - CUHK(SZ) SDS BRESAR reader Markdown title is exactly `助理教授`.
  - Reader metadata without a clean bounded role leaves `profile.title` empty.
  - CUHK(SZ) SDS title is found when the reader `Title:` label is stripped.
  - Navigation text such as `荣休教授` is ignored before the real profile
    heading.
  - Bounded compound title `教授，博士生导师` remains valid.

Writer state RED command:

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
- The test failed because both the corrected title `助理教授` and the stale
  contaminated title variant were still `is_current=true`.

Writer state GREEN command:

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
- The writer now keeps the corrected primary affiliation current and marks the
  stale same-source contaminated variant non-current.

## 2026-05-25 Real Data Remediation And P8 E2E

Targeted real seed rerun command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline run_single_seed seed_id=7 trigger_mode=full timeout=45.0>
```

Result:
- Exit code 0.
- `run_id=fa5df945-ec54-4c74-8623-28cd339884b0`.
- `status=success`, `failure_class=success`.
- `items_processed=98`, `items_failed=0`.
- `adapter_name=cuhk_teacher_search`.

Real row verification command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline BRESAR affiliation query>
```

Result:
- BRESAR, Miha has 3 affiliation rows for the CUHK(SZ) SDS source page.
- Exactly one row is current:
  - `title=助理教授`
  - `is_primary=true`
  - `is_current=true`
  - `run_id=fa5df945-ec54-4c74-8623-28cd339884b0`
  - `source_url=https://sds.cuhk.edu.cn/teacher/2238`
- The old `教授` row and the old 7619-character contaminated row remain as
  historical rows with `is_current=false`.

P8 post-full audit E2E command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/run_professor_post_full_quality_audit.py
```

Result:
- Exit code 0.
- `known_field_defects[0].defect_id=cuhk-sds-bresar-title`.
- `known_field_defects[0].status=resolved`.
- `current_value_preview=助理教授`.
- `contamination_markers=[]`.
- `p9_blockers=[]`.
- `p9_readiness=ready`.
- Seed 7 latest full run is
  `fa5df945-ec54-4c74-8623-28cd339884b0` with `items_processed=98` and
  `items_failed=0`.

Remaining P8 audit findings:
- `blocked_seed_carryover=[5]` remains historical carryover, not a P9 blocker
  in the post-full audit.
- Duplicate identity risk groups remain reported, including
  `canonical_name=教育经历`; this change does not merge duplicates.
- Open issue counts remain:
  - `professor_quality_gate:affiliation:low=409`
  - `professor_quality_gate:coverage:low=2340`
  - `professor_quality_gate:research_directions:low=1757`
  - `professor_seed_runner:adapter_missing:medium=3`
  - `professor_seed_runner:discovery:high=8`

Skipped by scope:
- Publish refresh.
- RAG index refresh.
- Milvus refresh.
- Duplicate merge.
- Broad historical cleanup.
- Deletion.
- Schema migration.
- Seed-management behavior changes.

Direct page fetch note:
- A direct `urllib` fetch of `https://sds.cuhk.edu.cn/teacher/2238` failed with
  `SSLV3_ALERT_HANDSHAKE_FAILURE`; confidence comes from the project seed
  runner's successful crawler path plus real `miroflow_real` row verification.

## 2026-05-25 Final Targeted Verification

Commands:

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
