# Acceptance: prof-post-full-quality-audit

## Status

| Requirement | Status | Evidence |
|---|---|---|
| P8 audit report covers post-full Professor data | Verified | Real E2E audit reported canonical totals, quality/source/traceability distributions, duplicate-risk groups, open issues, blocked seed carryover, known defects, and P9 readiness. |
| P8 validates P7 full-run coverage | Verified | Real E2E audit reported all 19 selected P7 seed ids as `covered`. |
| P8 stays read-only unless re-evaluation is explicit | Verified | The default command only ran SELECT-backed audit logic and no quality re-evaluation, cleanup, publish refresh, RAG refresh, deletion, or merge was executed. |
| P8 tracks profile-field extraction defects | Verified | The BRESAR, Miha CUHK(SZ) SDS title defect is reported as unresolved with contamination markers and P9 blocker `field_defect:cuhk-sds-bresar-title`. |
| P8 completion updates required artifacts | Verified | `tasks.md`, this file, and `.agents/runs/prof-post-full-quality-audit/verification.md` contain command evidence; strict validation passed and apply showed only task 4.6 pending before final checkbox update. |
| P7 full results must be audited before P9 | Verified | P9 readiness is `blocked`; publish/index work must wait for the BRESAR title remediation and any chosen duplicate/quality cleanup plan. |

## Scope Boundary

P8 is authorized to run read-only Professor quality audits against
`miroflow_real` and to record remediation candidates. P8 is not authorized to
delete or clean canonical data, merge duplicate Professor rows, refresh publish
collections, refresh RAG indexes, unblock seed 5, or rewrite quality status
unless an explicit re-evaluation task records before/after evidence.

## Pending Evidence

- Active change and P7 handoff baseline.
- Current `miroflow_real` schema and traceability-surface confirmation.
- BRESAR, Miha current-row inspection.
- P8 audit helper RED/GREEN test evidence.
- Real P8 E2E audit report.
- P9 publish/index readiness handoff.

## 2026-05-25 Baseline Evidence

### Active Change State

Commands:

```bash
openspec list --json
openspec status --change prof-post-full-quality-audit --json
openspec instructions apply --change prof-post-full-quality-audit --json
openspec validate prof-post-full-quality-audit --strict
```

Results:
- `prof-post-full-quality-audit` is the only active change.
- The change uses the `spec-driven` schema.
- Initial apply was blocked because `tasks.md` was missing; after creating
  `tasks.md`, `acceptance.md`, and this run verification log, apply reported
  22 total pending tasks and state `ready`.
- Strict validation passed.

### P7 Full-Run Baseline

P7 handoff rows selected for P8 audit:

```text
6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 24, 25, 26, 27, 28
```

Current `miroflow_real` confirmation:
- The 19 selected rows have latest full `pipeline_run` evidence with
  `run_scope.trigger_mode='full'`, `run_scope.failure_class='success'`,
  terminal status `succeeded`, and positive item counts.
- `pipeline_run.seed_id` is currently null for these runs; P8 audit must use
  `run_scope.seed_id` as the primary seed id and only fall back to the physical
  `seed_id` column when present.
- Blocked seed 5 remains a preview-only failed row with
  `failure_class='fetch_blocked'`; it is not a P9 publish-ready full-run row.

### Schema Surface Baseline

The current `professor` table has no `evidence` column. P8 traceability must use
the actual schema surfaces:
- `professor.run_id`
- `professor.primary_official_profile_page_id`
- `source_page`
- `professor_affiliation`
- `professor_fact`
- `pipeline_run.run_scope`
- `pipeline_issue`

The current `pipeline_run` table also has no physical `failure_class` column;
failure classification is stored in `pipeline_run.run_scope->>'failure_class'`.

### Known Field-Extraction Defect Baseline

The CUHK(SZ) SDS BRESAR, Miha row exists in `miroflow_real`:
- `professor_id=PROF-6553974C5393`
- `canonical_name=BRESAR, Miha`
- `quality_status=needs_enrichment`
- `professor.run_id=2b8861c3-fdb8-4091-8532-c32dd848c8be`
- `source_page.url=https://sds.cuhk.edu.cn/teacher/2238`
- `source_page.is_official_source=true`
- `professor_affiliation.title` is contaminated with the source page title,
  reader metadata, navigation text, education content, research fields,
  profile text, and publication text.

Expected title after remediation:

```text
助理教授
```

P8 classification:
- This row is a known profile-field extraction remediation candidate.
- It must not be counted as publish-ready while the title contamination remains
  unresolved.

## 2026-05-25 Audit Implementation Evidence

Files:
- `apps/miroflow-agent/src/data_agents/professor/post_full_quality_audit.py`
- `apps/miroflow-agent/scripts/run_professor_post_full_quality_audit.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_post_full_quality_audit.py`
- `apps/miroflow-agent/tests/scripts/test_run_professor_post_full_quality_audit.py`

RED commands:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_post_full_quality_audit.py -q
uv run --no-sync pytest tests/scripts/test_run_professor_post_full_quality_audit.py -q
```

RED results:
- Initial helper test failed with
  `ModuleNotFoundError: No module named 'src.data_agents.professor.post_full_quality_audit'`.
- CLI test failed with
  `FileNotFoundError: scripts/run_professor_post_full_quality_audit.py`.

GREEN command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/scripts/test_run_professor_post_full_quality_audit.py \
  tests/data_agents/professor/test_post_full_quality_audit.py -q
```

GREEN result:
- 4 passed.

## 2026-05-25 Real P8 E2E Audit

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
- `quality_status_distribution`: `needs_enrichment=2342`, `ready=2`.
- `run_id_coverage`: `with_run_id=2344`, `missing_run_id=0`.
- `official_source_page_coverage`: `with_official_source_page=2344`,
  `missing_official_source_page=0`.
- `primary_affiliation_coverage`: `with_primary_affiliation=2344`,
  `missing_primary_affiliation=0`.
- `fact_coverage`: `with_fact=2344`, `missing_fact=0`.
- P7 full-run coverage: all 19 selected seed ids were `covered`.
- `blocked_seed_carryover`: seed 5.
- Duplicate identity risk groups: 50 groups reported in the deterministic
  report, including suspicious non-name canonical value `教育经历`.
- Open issue counts:
  - `professor_quality_gate:affiliation:low=409`
  - `professor_quality_gate:coverage:low=2340`
  - `professor_quality_gate:research_directions:low=1757`
  - `professor_seed_runner:adapter_missing:medium=3`
  - `professor_seed_runner:discovery:high=8`
- Known field defects: `cuhk-sds-bresar-title` remains `unresolved`; expected
  title is `助理教授`.
- `p9_readiness=blocked`.
- `p9_blockers=["field_defect:cuhk-sds-bresar-title"]`.

Skipped in P8:
- Cleanup and deletion.
- Publish refresh.
- RAG index refresh.
- Automatic quality-status writes.
- Canonical merges or duplicate resolution.
- Seed 5 unblock attempts.

## 2026-05-25 Targeted Verification

Commands:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_post_full_quality_audit.py \
  tests/scripts/test_run_professor_post_full_quality_audit.py \
  tests/data_agents/professor/test_controlled_full_recollection.py \
  tests/data_agents/professor/test_recollection_readiness.py \
  tests/scripts/test_audit_professor_seed_adapter_coverage.py -q
uv run --no-sync ruff check \
  src/data_agents/professor/post_full_quality_audit.py \
  scripts/run_professor_post_full_quality_audit.py \
  tests/data_agents/professor/test_post_full_quality_audit.py \
  tests/scripts/test_run_professor_post_full_quality_audit.py
```

Results:
- Targeted pytest: 16 passed.
- Ruff: all checks passed.

## P9 Handoff

P9 publish/index/RAG refresh work is not ready to execute yet.

Blockers and remediation candidates:
- `field_defect:cuhk-sds-bresar-title`: repair CUHK(SZ) SDS title extraction
  so BRESAR, Miha's `professor_affiliation.title` becomes exactly `助理教授`,
  with a regression test against the page/parser path.
- Duplicate identity risk groups are present in the deterministic report; P9
  can only proceed after deciding whether duplicate cleanup is required before
  publish/index refresh.
- Historical quality-gate issues remain open in large counts; P9 must either
  accept them explicitly as non-blocking for the publish slice or schedule a
  quality-gate remediation slice first.

## 2026-05-25 OpenSpec Final Validation

Commands:

```bash
openspec validate prof-post-full-quality-audit --strict
openspec instructions apply --change prof-post-full-quality-audit --json
```

Results:
- `openspec validate` returned `Change 'prof-post-full-quality-audit' is
  valid`.
- `openspec instructions apply` reported 21/22 complete before marking task
  4.6, with only the final validation task pending.

Task updates:
- Marked task 4.6 complete after recording the validation result.
