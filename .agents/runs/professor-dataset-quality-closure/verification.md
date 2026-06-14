# Verification Log: professor-dataset-quality-closure

## 2026-06-13 Initial Slice

Scope: create the verification contract and implement the read-only bucketed
baseline audit. No write-mode backfill or database mutation is allowed in this
slice.

RED evidence:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py -q -n0 --no-cov`
- Result before implementation: exit `2`.
- Failure: tests could not import `DatasetClosureBucketRow` from
  `src.data_agents.professor.core_profile_paper_quality_audit`.

Implementation:

- Added read-only dataset closure bucket models:
  `DatasetClosureBucketRow` and `DatasetClosureBuckets`.
- Added optional `closure_buckets` JSON output while preserving the legacy
  default report when `--include-buckets` is not supplied.
- Added `load_dataset_closure_buckets` with bounded samples for:
  - `ready_summary_lt_200`
  - `missing_research_overview_zh`
  - `missing_professor_paper_summary`
  - `duplicate_verified_paper_title_year_groups`
- Added CLI options:
  - `--include-buckets`
  - `--bucket-limit`

Targeted verification:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py -q -n0 --no-cov`
- Result: exit `0`, `7 passed in 0.51s`.

Real database read-only baseline:

- Command:
  `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python apps/miroflow-agent/scripts/run_professor_core_profile_paper_quality_audit.py --include-buckets --bucket-limit 5`
- Result: exit `1`, expected because dataset readiness remains blocked.
- Blockers:
  - `ready_summary_lt_200:441`
  - `missing_research_overview_zh:2510`
  - `missing_professor_paper_summary:2200`
  - `duplicate_verified_paper_title_year_groups:5186`
- Case status:
  - Ahmed Elazab: passing
  - Ding Wenbo: passing
  - pFedGPA: passing
- Bucket summary:
  - `ready_summary_lt_200`: total `441`, sampled `5`, truncated `true`,
    lane `profile_summary_repair`
  - `missing_research_overview_zh`: total `2510`, sampled `5`,
    truncated `true`, lane `research_overview_backfill`
  - `missing_professor_paper_summary`: total `2200`, sampled `5`,
    truncated `true`, lane `professor_paper_summary_generation`
  - `duplicate_verified_paper_title_year_groups`: total `5186`, sampled `5`,
    truncated `true`, lane `duplicate_paper_merge`
- Representative samples:
  - short-summary sample: `PROF-019A6958E272`, profile summary length `197`,
    automatic eligibility `true`, source URL
    `https://csce.suat-sz.edu.cn/info/1012/1397.htm`
  - missing-overview sample: `PROF-000003A9EBC4`, source language `zh`,
    automatic eligibility `true`
  - missing-paper-summary sample: `PROF-000E83C9344A`, verified paper count
    `93`, duplicate group count `0`, automatic eligibility `true`
  - duplicate-paper sample: `PROF-00248146798C:2022:in-situgrowthofultrathinsulfurmicro-crystalonmxe`,
    paper ids `PAPER-39FBE370CED6` and `PAPER-CC0FCC5198C5`,
    DOI evidence count `1`, automatic eligibility `true`

Skipped in this slice:

- Write-mode remediation lanes.
- Professor quality re-evaluation.
- API sampling of changed rows.
- Index/vector refresh.

## 2026-06-13 Bucket Classification Rules

Scope: stabilize the bucket taxonomy and eligibility rules used by the
read-only audit. No database writes were run.

Implementation:

- Extracted pure classification helpers for:
  - profile summary repair eligibility;
  - research overview source-language and extraction eligibility;
  - Professor paper-summary eligibility with duplicate-link blocking;
  - duplicate paper merge eligibility based on enriched row plus DOI/arXiv
    evidence.
- Added unit coverage for eligible and skipped branches of all four blocker
  classes.

Verification:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py -q -n0 --no-cov`
- Result: exit `0`, `8 passed in 0.53s`.
- Command:
  `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python apps/miroflow-agent/scripts/run_professor_core_profile_paper_quality_audit.py --include-buckets --bucket-limit 2`
- Result: exit `1`, expected because dataset readiness remains blocked.
- Real bucket summary:
  - `ready_summary_lt_200`: total `441`, sampled `2`, truncated `true`
  - `missing_research_overview_zh`: total `2510`, sampled `2`,
    truncated `true`
  - `missing_professor_paper_summary`: total `2200`, sampled `2`,
    truncated `true`
  - `duplicate_verified_paper_title_year_groups`: total `5186`,
    sampled `2`, truncated `true`
- Real classification examples:
  - `PROF-019A6958E272`: profile-summary repair eligible from grounded facts
    and raw profile text.
  - `PROF-000003A9EBC4`: research-overview backfill eligible with detected
    Chinese source text.
  - `PROF-000E83C9344A`: Professor paper-summary generation eligible with
    `93` verified papers and no duplicate group in the sample row.
  - `PROF-00248146798C:2022:in-situgrowthofultrathinsulfurmicro-crystalonmxe`:
    duplicate-paper merge eligible with enriched row and DOI evidence.

## 2026-06-14 Bounded Dry-Run Lane Gate

Scope: add a unified read-only dry-run lane report and write-mode evidence
gate for the four remediation lanes. This slice does not run write-mode
backfills and does not mutate `miroflow_real`.

RED evidence:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
- Result before implementation: exit `2`.
- Failure: `ModuleNotFoundError: No module named 'src.data_agents.professor.dataset_quality_closure'`.
- Additional RED for candidate profile-summary validation:
  `test_profile_summary_dry_run_excludes_invalid_candidate_summary` failed
  until invalid candidate summaries were excluded from proposed writes.

Implementation:

- Added `src.data_agents.professor.dataset_quality_closure`.
- Added `scripts/run_professor_dataset_quality_closure.py`.
- Added dry-run lane report fields:
  - `dataset_input_count`
  - `input_count`
  - `eligible_count`
  - `proposed_write_count`
  - `skipped_count`
  - `validation_failure_count`
  - `provider_failure_count`
  - `affected_professor_ids`
  - `affected_paper_ids`
  - `skip_reason_counts`
  - `validation_rules`
  - `selection_hash`
- Added write-mode gate: write mode refuses without `--dry-run-evidence`.
- Added profile-summary candidate validation for the 200-300 Chinese character
  contract when a dry-run row provides `candidate_profile_summary`.

Targeted verification:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
- Result: exit `0`, `14 passed in 0.55s`.

Real database dry-run:

- Command:
  `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py --bucket-limit 3`
- Result: exit `0`.
- Lane summaries:
  - `profile_summary_repair`: dataset input `441`, sampled input `3`,
    eligible `3`, proposed writes `3`, validation failures `0`,
    affected professors `PROF-019A6958E272`, `PROF-01DB8A76ECAC`,
    `PROF-01FAFE3D04B6`
  - `research_overview_backfill`: dataset input `2510`, sampled input `3`,
    eligible `3`, proposed writes `3`, provider failures `0`
  - `professor_paper_summary_generation`: dataset input `2200`, sampled input
    `3`, eligible `3`, proposed writes `3`
  - `duplicate_paper_merge`: dataset input `5186`, sampled input `3`,
    eligible `3`, proposed writes `3`, affected professor
    `PROF-00248146798C`, affected paper ids include
    `PAPER-0923DBB68679`, `PAPER-35A2566F296D`,
    `PAPER-39FBE370CED6`, `PAPER-4F88A9FE7AAE`,
    `PAPER-CC0FCC5198C5`, and `PAPER-F39354DC03A0`
- Selection hash:
  `3f0e43b46bc31959a5763f708163ac4b1c59327ade6b891f8c1a9c0a70f456d6`.

Write-mode gate verification:

- Command:
  `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py --lane profile_summary_repair --mode write --bucket-limit 1`
- Result: exit `2`.
- Output error: `missing_dry_run_evidence`.
- No write-mode backfill was run.

## 2026-06-14 Write-Mode Batch Orchestration

Scope: implement write-mode batch orchestration and evidence-driven default
writers for the four remediation lanes. This slice uses fake connections and
candidate evidence in tests. No write-mode remediation command was run against
`miroflow_real`.

RED evidence:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py -q -n0 --no-cov`
- Result before implementation: exit `2`.
- Failure: tests could not import `ClosureRowWriteResult` from
  `src.data_agents.professor.dataset_quality_closure`.
- Command:
  `uv run pytest apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
- Result before implementation: exit `1`.
- Failure: write mode still returned `write_mode_not_implemented` instead of
  requiring `run_id` and loading dry-run evidence.
- Additional RED after adding default writer tests:
  `default_dataset_closure_writers` could not be imported until the
  evidence-driven writer set existed.

Implementation:

- Added write-mode report models:
  - `ClosureRowWriteResult`
  - `DatasetClosureWriters`
  - `LaneWriteBatchSummary`
  - `DatasetClosureWriteReport`
- Added `load_dry_run_evidence` and write validation that compares the
  evidence lane list and `selection_hash` with the current bucket selection.
- Added `run_dataset_closure_write_batch` with:
  - non-sentinel `run_id` requirement;
  - per-lane batch-size bounds;
  - visible row-level issue payloads for skipped, failed, and unresolved rows;
  - changed Professor/Paper ids;
  - rollback evidence fields.
- Added default evidence-driven writers for:
  - candidate `profile_summary` updates on `professor`;
  - candidate `research_overview` upserts on `professor_profile_section`;
  - candidate Professor `paper_summary` updates on `professor`;
  - candidate duplicate-paper old-to-canonical mappings on `paper_merge_alias`.
- Updated `run_professor_dataset_quality_closure.py --mode write` to require
  `--dry-run-evidence`, require `--run-id`, reload current buckets, run the
  write batch, and output the write report.

Targeted verification:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
- Result: exit `0`, `11 passed in 0.62s`.
- Command:
  `uv run ruff check apps/miroflow-agent/src/data_agents/professor/dataset_quality_closure.py apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py`
- Result: exit `0`, `All checks passed!`.

Skipped in this slice:

- Real write-mode remediation against `miroflow_real`; by contract this slice
  implemented and tested the write path but did not mutate production-like
  data.
- Candidate generation via LLM translation or summarization. The default
  writers only persist candidate values already present in evidence and report
  missing candidates as residual-risk rows.
- Post-write quality re-evaluation, API sampling, and index/vector refresh.

## 2026-06-14 Post-Write Verification Interface

Scope: add a reusable report interface for post-write evidence. This is a
code-level scaffold backed by unit tests with injected callbacks; it is not yet
the real post-write integration run required by tasks 5.1 through 5.5.

RED evidence:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py -q -n0 --no-cov`
- Result before implementation: exit `2`.
- Failure: tests could not import `AffectedAuditEvidence` from
  `src.data_agents.professor.dataset_quality_closure`.

Implementation:

- Added post-write evidence models for:
  - quality re-evaluation before/after distributions;
  - affected-id closure audit evidence;
  - Admin Professor and Paper detail API samples;
  - index refresh selection;
  - post-write verification report status and blocking issues.
- Added `build_post_write_verification_report`, which derives changed
  Professor/Paper ids from a write report and blocks completion when required
  callback evidence is missing, throws, or returns failures.
- Added tests that prove a complete callback evidence set allows completion
  and a failed Admin Professor detail sample blocks completion.

Targeted verification:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
- Result: exit `0`, `21 passed in 0.61s`.
- Command:
  `uv run ruff check apps/miroflow-agent/src/data_agents/professor/dataset_quality_closure.py apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py`
- Result: exit `0`, `All checks passed!`.

Still pending:

- Real Professor quality re-evaluation for changed Professor ids.
- Real affected-id closure audit checks.
- Real Admin Professor detail and Paper detail API sampling.
- Real index/vector refresh selection evidence.

## 2026-06-14 Default Post-Write Verification Callbacks

Scope: wire default post-write verification callbacks into the write-mode CLI
path. This implements the code path required after a write batch, but this
slice still did not execute real remediation writes against `miroflow_real`.

RED evidence:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py -q -n0 --no-cov`
- Result before implementation: exit `2`.
- Failure: tests could not import
  `default_post_write_verification_callbacks` from
  `src.data_agents.professor.dataset_quality_closure`.
- Command:
  `uv run pytest apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
- Result before CLI integration: exit `1`.
- Failure: the CLI module did not expose or invoke
  `build_post_write_verification_report`, so write-mode output had no
  `post_write_verification` evidence.

Implementation:

- Added default post-write callbacks for:
  - changed Professor quality re-evaluation with before/after distribution;
  - affected-id blocker audit for short summaries, missing research overview,
    missing Professor paper summary, and duplicate verified paper groups;
  - Professor detail shape sampling for profile summary, paper summary,
    research-overview presence, and verified paper count;
  - Paper detail shape sampling for title, quality status, and verified
    Professor-link count;
  - index refresh selection from changed Professor/Paper ids.
- Wired `run_professor_dataset_quality_closure.py --mode write` to append
  `post_write_verification` to the write report.
- Write mode now returns a non-zero status when post-write verification fails
  for changed Professor/Paper ids.

Verification:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
- Result: exit `0`, `27 passed in 0.64s`.
- Command:
  `uv run ruff check apps/miroflow-agent/src/data_agents/professor/dataset_quality_closure.py apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py`
- Result: exit `0`, `All checks passed!`.
- Command:
  `openspec validate "professor-dataset-quality-closure" --strict`
- Result: exit `0`, change is valid.
- Command:
  `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py --lane profile_summary_repair --mode write --bucket-limit 1`
- Result: exit `2`, expected guard failure `missing_dry_run_evidence`.
- No write-mode remediation ran.

Skipped in this slice:

- Real write-mode remediation and real post-write sampling against changed
  `miroflow_real` rows. The path is implemented and tested with fake
  connections, but production-like data was not mutated.

## 2026-06-14 Domain Boundary Regression Coverage

Scope: add regression tests for the user-confirmed boundary that Professor core
closure follows official roster/profile/paper evidence, while company/news
association remains outside Professor core readiness.

Implementation:

- Added tests proving provider-only author-search results do not produce a
  Professor `paper_summary` write candidate and do not reach the write lane.
- Added tests proving hidden company/startup role absence does not block
  profile-summary closure when official Professor core evidence is present.
- Added tests proving external enrichment is accepted only when it enriches an
  official Professor-seeded paper candidate.

Verification:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py -q -n0 --no-cov`
- Result: exit `0`, `12 passed in 0.56s`.

## 2026-06-14 Current Slice Final Verification

Commands:

- `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
  - Result: exit `0`, `24 passed in 0.59s`.
- `uv run ruff check apps/miroflow-agent/src/data_agents/professor/dataset_quality_closure.py apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py`
  - Result: exit `0`, `All checks passed!`.
- `openspec validate "professor-dataset-quality-closure" --strict`
  - Result: exit `0`, change is valid.
- `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py --lane profile_summary_repair --mode write --bucket-limit 1`
  - Result: exit `2`, expected guard failure `missing_dry_run_evidence`.
  - No write-mode remediation ran.

Current OpenSpec progress after this slice:

- Completed through write-mode batch orchestration and domain-boundary
  regression coverage.
- Post-write verification callbacks are wired into write mode, but real
  post-write evidence remains pending because no real write batch has been
  executed against `miroflow_real`.

## 2026-06-14 Final Dataset Closure Evidence Pass

Scope: run final read-only audit and current targeted regression checks without
executing real write-mode remediation against `miroflow_real`.

Final read-only dataset audit:

- Command:
  `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python apps/miroflow-agent/scripts/run_professor_core_profile_paper_quality_audit.py --include-buckets --bucket-limit 5`
- Result: exit `1`, expected because readiness remains `blocked`.
- Remaining blockers:
  - `ready_summary_lt_200:441`
  - `missing_research_overview_zh:2510`
  - `missing_professor_paper_summary:2200`
  - `duplicate_verified_paper_title_year_groups:5186`
- Case status:
  - Ahmed Elazab: passing
  - Ding Wenbo: passing
  - pFedGPA: passing
- Bucket sample status:
  - all four blocker classes returned bounded samples;
  - all four summaries are truncated, so the full blocker population has not
    been converted into durable residual-risk rows.

Targeted Professor/Paper closure regression:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
- Result: exit `0`, `27 passed in 0.64s`.

Targeted Admin Professor detail and Paper detail API regression:

- Command:
  `uv run pytest apps/admin-console/tests/test_admin_professor_api.py::test_admin_professor_detail_returns_seven_sections apps/admin-console/tests/test_admin_professor_api.py::test_admin_professor_detail_prefers_persisted_chinese_research_overview apps/admin-console/tests/test_admin_professor_api.py::test_admin_professor_detail_returns_canonical_paper_link_fields apps/admin-console/tests/test_data_api_paper_v011.py::test_paper_detail_includes_full_text_metadata apps/admin-console/tests/test_data_api_paper_v011.py::test_domains_paper_detail_returns_summary_zh_column_value -q -n0 --no-cov`
- Result: exit `0`, `5 passed, 4 warnings in 0.04s`.
- Warnings: FastAPI `on_event` deprecation warnings in existing admin-console
  startup/shutdown code.

Targeted frontend Professor/Paper detail routing regression:

- Command:
  `npm run test -- RecordDetail.test.tsx ProfessorWorkbench.test.tsx`
  from `apps/admin-console/frontend`
- Result: exit `0`, `2 passed` test files, `11 passed` tests.

OpenSpec validation:

- Command:
  `openspec validate "professor-dataset-quality-closure" --strict`
- Result: exit `0`, change is valid.

Current final-closure decision:

- Task 7.1 is complete because the final read-only audit was run.
- Task 7.3 is complete for the current executable regression set: unit/script,
  real read-only integration audit, API detail tests, and frontend detail tests
  ran in this session.
- Task 7.5 is complete because strict OpenSpec validation passed.
- Task 7.2 remains incomplete. The four blocker classes are not cleared, and
  only bounded samples are classified in the audit output. The full blocker
  population still needs real lane-specific remediation or durable
  residual-risk records with reason, confidence impact, and next action.

Skipped checks and confidence impact:

- Real write-mode remediation against `miroflow_real`: skipped. Confidence
  impact: blockers remain in the real dataset. Next action: generate bounded
  dry-run candidate evidence for each lane, then run write mode with matching
  evidence and a real run id.
- Real post-write verification against changed `miroflow_real` rows: skipped
  because no real rows changed. Confidence impact: the post-write path is
  covered by tests but not by production-like changed-row evidence.
- Index/vector refresh: skipped because no real rows changed. Confidence
  impact: refresh selection is implemented and tested, but no refresh artifact
  exists for a real remediation batch.

## 2026-06-14 Residual-Risk Classification Closure

Scope: close the final "no silent blockers" requirement by converting every
remaining targeted blocker into an open `pipeline_issue` row with evidence,
confidence impact, and next action. This did not repair Professor/Paper data
fields and did not run write-mode remediation.

RED evidence:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py -q -n0 --no-cov`
- Result before implementation: exit `2`.
- Failure: tests could not import
  `file_residual_risk_issues_for_buckets`.
- Command:
  `uv run pytest apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
- Result before CLI integration: exit `1`.
- Failure: `residual-risk` mode was treated as dry-run and CLI functions for
  residual-risk filing and coverage were missing.

Implementation:

- Added residual-risk issue filing for fully loaded bucket sets.
- Added residual-risk coverage verification that checks every bucket row has an
  open `pipeline_issue` with issue type
  `professor_dataset_quality_closure_residual_risk`.
- Added CLI modes:
  - `--mode residual-risk`
  - `--mode residual-risk-coverage`
- Residual-risk issue evidence includes blocker type, remediation lane, reason,
  confidence impact, recommended action, next action, source ids/URLs, and
  bucket evidence.

Targeted verification:

- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py -q -n0 --no-cov`
- Result: exit `0`, `17 passed in 0.63s`.
- Command:
  `uv run pytest apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
- Result: exit `0`, `8 passed in 0.56s`.
- Command:
  `uv run pytest apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py -q -n0 --no-cov`
- Result: exit `0`, `33 passed in 0.66s`.
- Command:
  `uv run ruff check apps/miroflow-agent/src/data_agents/professor/dataset_quality_closure.py apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py`
- Result: exit `0`, `All checks passed!`.

Real database residual-risk baseline:

- Command:
  `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py --mode residual-risk-coverage --bucket-limit 6000`
- Result before filing: exit `1`, `status:incomplete`,
  `input_count:10337`, `covered_count:0`, `unclassified_count:10337`.

Real database residual-risk filing:

- Command:
  `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py --mode residual-risk --bucket-limit 6000 --run-id 253a1ac9-73aa-4ee9-ab65-347ba84aee2a`
- Result: exit `0`.
- Filing report:
  - `input_count:10337`
  - `inserted_count:10336`
  - `updated_count:1`
  - `ready_summary_lt_200:441`
  - `missing_research_overview_zh:2510`
  - `missing_professor_paper_summary:2200`
  - `duplicate_verified_paper_title_year_groups:5186`
- Coverage report from the same command:
  - `status:complete`
  - `covered_count:10337`
  - `unclassified_count:0`

Real database residual-risk coverage after filing:

- Command:
  `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py --mode residual-risk-coverage --bucket-limit 6000`
- Result: exit `0`.
- Coverage:
  - `status:complete`
  - `input_count:10337`
  - `covered_count:10337`
  - `unclassified_count:0`
  - `ready_summary_lt_200:441`
  - `missing_research_overview_zh:2510`
  - `missing_professor_paper_summary:2200`
  - `duplicate_verified_paper_title_year_groups:5186`

Final data-quality audit after residual-risk classification:

- Command:
  `DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' uv run python apps/miroflow-agent/scripts/run_professor_core_profile_paper_quality_audit.py --include-buckets --bucket-limit 5`
- Result: exit `1`, expected because underlying Professor/Paper data fields are
  still blocked.
- Remaining data blockers:
  - `ready_summary_lt_200:441`
  - `missing_research_overview_zh:2510`
  - `missing_professor_paper_summary:2200`
  - `duplicate_verified_paper_title_year_groups:5186`
- Interpretation: task 7.2 is now complete because all blockers are visible
  unresolved issues with next action, not because the underlying data has been
  repaired.

Skipped or unavailable checks:

- Direct `psql` count query was not run because `psql` is not installed in this
  environment. The coverage CLI above is the authoritative verification for
  this slice.
- Real data remediation writes, post-write quality re-evaluation against
  changed Professor rows, and index refresh remain skipped because this slice
  only classified unresolved blockers.
