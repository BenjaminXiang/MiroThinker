# Tasks — paper-implausible-title-cleanup

> Codex-facing implementation slices. RED = unit/contract tests for the writer
> parameterization + scan + display filter. Order by dependency. Depends on W0b
> (`wire-paper-identity-gate-rejection`) for `identity_status_writer` + the
> `rejected` status + Milvus exclusion.
>
> Status 2026-06-23: ALL tasks done + applied (528 high-precision garbage rejected,
> 0 `ready`) + Milvus cleaned (targeted delete). Archiving.

## 1. Verification contract & baseline
- [x] 1.1 Create `.agents/runs/paper-implausible-title-cleanup/verification-contract.md` (created 2026-06-22): behavior-affecting (deterministic scan + display filter; no LLM); RED = contract/unit tests; Superpowers TDD allowed on deterministic slices.
- [x] 1.2 (DONE 2026-06-22: dry-run-refined found 561 high-precision garbage, 30/30 samples clear) Baseline count: SQL read on `miroflow_real` counting `prof_page_only` papers with clearly-garbage titles (`is_clearly_garbage_paper_title` True) AND `identity_status NOT IN ('rejected','merged')`; save to `.agents/runs/paper-implausible-title-cleanup/eligibility-baseline.json`. Cross-check against the W0b dry-run JSONL `no_change` + no-verified-link count.

## 2. Writer parameterization
- [x] 2.1 Extend `apply_identity_status_rejection(*, ..., stage='identity_gate', reported_by='paper_identity_scan')` with keyword params (defaults preserve W0b behavior); thread them into the `pipeline_issue` INSERT + the `_fetch_open_issue` query.
- [x] 2.2 RED+GREEN: unit test that title-cleanup-stage issues are filed at `identity_gate` / `paper_title_cleanup_scan` (distinct from W0b's `paper_identity_scan` by `reported_by`; the `pipeline_issue.stage` CHECK has no `title_cleanup` value, so the allowed `identity_gate` is reused) — no collision in `_fetch_open_issue`.

## 3. Title-cleanup scan script
- [x] 3.1 Create `scripts/run_paper_title_cleanup_scan.py` mirroring `run_paper_identity_scan.py` structure: dry-run default, `--apply`, `--limit`, `--confirm-real-db`, `--json-output`/`--archive`, `_ScanStats` (examined/rejected/unchanged/skipped/issues_filed); `PAPER_TITLE_CLEANUP_ENABLED` flag (default off).
- [x] 3.2 Scan flow: select `prof_page_only` papers with `identity_status NOT IN ('rejected','merged')`; for each, call `is_clearly_garbage_paper_title(title_clean)`; if True → `apply_identity_status_rejection(stage='identity_gate', reported_by='paper_title_cleanup_scan', ...)` (the `pipeline_issue.stage` CHECK has no `title_cleanup` value, so the allowed `identity_gate` is reused) on `--apply`; emit JSONL. **NO LLM calls.**
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
- [x] 6.1 (DONE 2026-06-22: dry-run-refined on 40,865 → 561 high-precision rejects, 30/30 samples clear garbage; `dry-run-refined-2026-06-22.jsonl`) Dry-run on `miroflow_real` (unset proxy); save counts + sampled JSONL to `.agents/runs/paper-implausible-title-cleanup/`; compare to 1.2 baseline.
- [x] 6.2 (DONE 2026-06-22: full apply on 33,935 → 528 rejected, 0 `ready` (455 needs_enrichment + 73 rejected); 528 `pipeline_issue` at `identity_gate`/`paper_title_cleanup_scan` with `run_id`; `apply-2026-06-22.jsonl`) Bounded/full `--apply`; verify only clearly-garbage-titled prof_page_only rows rejected + `pipeline_issue` at `identity_gate` with `run_id`; 0 plausible-titled rows touched.
- [x] 6.3 (DONE 2026-06-23: the 528 title-cleanup-rejected papers are part of the 33,335 rejected/merged chunks removed via targeted Milvus delete from `apps/miroflow-agent/milvus.db`; delete-sample 4→0, confirmed survive, backup at `mirothinker-milvus-backup-20260623.db`) Milvus re-backfill; verify excluded count; spot-check a rejected garbage title no longer returns in retrieval + no longer on `/paper` default.

## 7. Acceptance, validation, ledger
- [x] 7.1 (DONE 2026-06-23: `acceptance.md` filled with apply/Milvus evidence) Fill `acceptance.md` against the spec scenarios.
- [x] 7.2 (DONE 2026-06-23) `openspec validate paper-implausible-title-cleanup --strict` exits 0.
- [x] 7.3 (DONE 2026-06-23: ledger updated; archiving) Register in `openspec/change-ledger.md`; note dependency on `wire-paper-identity-gate-rejection` (now archived).
- [x] 7.4 (DONE: portfolio 2026-06-22 Phase 5 references this remediation) Update the portfolio (Phase 5 / W1b note) to reference this remediation change.
