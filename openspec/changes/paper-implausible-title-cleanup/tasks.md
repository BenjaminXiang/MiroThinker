# Tasks — paper-implausible-title-cleanup

> Codex-facing implementation slices. RED = unit/contract tests for the writer
> parameterization + scan + display filter. Order by dependency. Depends on W0b
> (`wire-paper-identity-gate-rejection`) for `identity_status_writer` + the
> `rejected` status + Milvus exclusion.
>
> Status 2026-06-22: code slices 2-5 + 1.1 + 7.2 + 7.3 done (direct implementation,
> TDD GREEN). Tasks 1.2 / 6.x / 7.1 / 7.4 remain (need the real `miroflow_real`
> baseline + apply, informed by the W0b slice B dry-run).

## 1. Verification contract & baseline
- [x] 1.1 Create `.agents/runs/paper-implausible-title-cleanup/verification-contract.md` (created 2026-06-22): behavior-affecting (deterministic scan + display filter; no LLM); RED = contract/unit tests; Superpowers TDD allowed on deterministic slices.
- [ ] 1.2 Baseline count: SQL read on `miroflow_real` counting `prof_page_only` papers with clearly-garbage titles (`is_clearly_garbage_paper_title` True) AND `identity_status NOT IN ('rejected','merged')`; save to `.agents/runs/paper-implausible-title-cleanup/eligibility-baseline.json`. Cross-check against the W0b dry-run JSONL `no_change` + no-verified-link count.

## 2. Writer parameterization
- [x] 2.1 Extend `apply_identity_status_rejection(*, ..., stage='identity_gate', reported_by='paper_identity_scan')` with keyword params (defaults preserve W0b behavior); thread them into the `pipeline_issue` INSERT + the `_fetch_open_issue` query.
- [x] 2.2 RED+GREEN: unit test that title-cleanup-stage issues are filed at `title_cleanup` / `paper_title_cleanup_scan` and are distinct from W0b `identity_gate` issues (no collision in `_fetch_open_issue`). (`test_apply_rejection_with_title_cleanup_stage_files_distinct_issue`.)

## 3. Title-cleanup scan script
- [x] 3.1 Create `scripts/run_paper_title_cleanup_scan.py` mirroring `run_paper_identity_scan.py` structure: dry-run default, `--apply`, `--limit`, `--confirm-real-db`, `--json-output`/`--archive`, `_ScanStats` (examined/rejected/unchanged/skipped/issues_filed); `PAPER_TITLE_CLEANUP_ENABLED` flag (default off).
- [x] 3.2 Scan flow: select `prof_page_only` papers with `identity_status NOT IN ('rejected','merged')`; for each, call `is_clearly_garbage_paper_title(title_clean)`; if True → `apply_identity_status_rejection(stage='title_cleanup', reported_by='paper_title_cleanup_scan', ...)` on `--apply`; emit JSONL. **NO LLM calls.**
- [x] 3.3 `_strip_proxy_env()` + `--confirm-real-db` (mirror W0b safety gates).

## 4. Display exclusion
- [x] 4.1 `PAPER_SELECT_SQL`: add `p.identity_status` to SELECT; add default `WHERE p.identity_status NOT IN ('rejected','merged')` (applied when no explicit identity_status filter).
- [x] 4.2 Add `identity_status` to the paper filter UI config (`domains.py` filter parsing) so admins can explicitly include `rejected`/`merged`.
- [x] 4.3 RED+GREEN: contract test that the `/paper` list default-excludes `rejected`/`merged` and that the filter can include them. (`test_paper_list_default_excludes_rejected_and_merged_identity_status` + `test_paper_list_identity_status_filter_opts_out_of_default_exclusion` + the `RELEASED_KEYS` shape tests updated to include `identity_status`.)

## 5. Tests (RED → GREEN)
- [x] 5.1 RED: `tests/data_agents/paper/test_identity_status_writer.py` — title-cleanup stage issues distinct from identity_gate.
- [x] 5.2 RED: `tests/scripts/test_run_paper_title_cleanup_scan.py` — dry-run no writes + JSONL + counts; `--apply` rejects only implausible-titled prof_page_only; plausible titles unchanged; already-rejected/merged skipped; flag-off skips.
- [x] 5.3 RED: `tests/.../test_domains_postgres.py` — default-excludes rejected/merged; filter includes them.
- [x] 5.4 GREEN: implement until all RED pass. `miroflow-agent`: paper suite + both scan tests = 930 passed. `admin-console`: 311 passed (4 pre-existing failures unrelated to this change).

## 6. Real evidence (dry-run first, bounded apply, re-backfill)
- [ ] 6.1 Dry-run on `miroflow_real` (unset proxy); save counts + sampled JSONL to `.agents/runs/paper-implausible-title-cleanup/`; compare to 1.2 baseline.
- [ ] 6.2 Bounded `--apply`; verify only implausible-titled prof_page_only rows rejected + `pipeline_issue` at `title_cleanup` with `run_id`; 0 plausible-titled rows touched.
- [ ] 6.3 Milvus re-backfill; verify excluded count; spot-check a rejected garbage title (e.g. "Co-supervised PhD student", "011 (IF: 26.8") no longer returns in retrieval + no longer on `/paper` default.

## 7. Acceptance, validation, ledger
- [ ] 7.1 Fill `acceptance.md` against the spec scenarios (A1/A2/A5 have unit-test evidence now; A3/A4/AC2/AC3 need the 6.x real run).
- [x] 7.2 `openspec validate paper-implausible-title-cleanup --strict` exits 0.
- [x] 7.3 Register in `openspec/change-ledger.md` (status `proposed` → `in-implementation`); note dependency on `wire-paper-identity-gate-rejection`.
- [ ] 7.4 Update the portfolio (Phase 5 / W1b note) to reference this remediation change.
