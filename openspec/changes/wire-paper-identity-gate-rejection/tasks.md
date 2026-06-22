# Tasks — wire-paper-identity-gate-rejection

> Codex-facing implementation slices. RED = unit/contract tests for the deterministic writer + scan (the LLM gate is reused unchanged). Order by dependency.

## 1. Verification contract & baseline

- [x] 1.1 Create `.agents/runs/wire-paper-identity-gate-rejection/verification-contract.md` (created 2026-06-16; re-baselined 2026-06-22 against the 28,928 fresh scan — see verification-contract.md AC1–AC6 + growth warning): classify as behavior-affecting (deterministic writer/scan; gate reused), select RED = contract/unit tests for the rejection guard + scan dry-run/apply semantics + reversibility, declare GREEN, and state that Superpowers TDD may drive the deterministic slices but must not change the gate.
- [x] 1.2 Baseline count (DONE 2026-06-22: **28,928** eligible, **0 `ready`** in the set; `eligibility-baseline.json` re-baselined with the 6/16 prior=1,519 preserved as history + growth explanation): run a SQL read on `miroflow_real` counting papers eligible for rejection (`canonical_source='prof_page_only'` AND no `professor_paper_link` with `link_status='verified'`); save to `.agents/runs/wire-paper-identity-gate-rejection/eligibility-baseline.json`. This is the predicted blast radius.

## 2. Identity-status writer (guard + reversible transition)

- [x] 2.1 Create `apps/miroflow-agent/src/data_agents/paper/identity_status_writer.py` with `decide_identity_status_rejection(*, has_verified_link: bool, canonical_source: str) -> IdentityStatusDecision` — returns `reject` only when `not has_verified_link and canonical_source == 'prof_page_only'`, else `no_change`. Pure function. (Mirror guard at `scripts/run_paper_title_enrichment_backfill.py:1085-1106` `_reject_implausible_paper`.) **Refined in 2.4 to add the plausible-title condition.**
- [x] 2.2 Add `apply_identity_status_rejection(conn, *, paper_id, run_id, evidence, prior_identity_status) -> RejectionResult` that writes `paper.identity_status='rejected'` (recording `prior_identity_status` for exact restore), files a `pipeline_issue` row at stage `identity_gate` with the gate decision + `run_id`, and does **not** touch `quality_status`. Idempotent on re-apply.
- [x] 2.3 Add `restore_identity_status(conn, *, paper_id) -> RestoreResult` that, on a re-scan finding a `verified` link, restores `identity_status` to the recorded `prior_identity_status` and resolves the matching `pipeline_issue`.

> 2.1–2.3 + group 3/4/5 implemented in Codex slice 1 (2026-06-16); 20 tests pass. The plausible-title guard below (2.4–2.5) is a refinement added after the dry-run found 92% of eligible rows had garbage titles.

- [x] 2.4 Extend `decide_identity_status_rejection(*, has_verified_link, canonical_source, title_clean)` to add a third condition: `is_plausible_paper_title(title_clean)` must be `True`. Reject only when all three hold; otherwise `no_change` (new reason `implausible_title` for the garbage-title case). Import `is_plausible_paper_title` from `paper/title_quality`.
- [x] 2.5 Update `run_paper_identity_scan.py` to pass `title_clean` into `decide_identity_status_rejection` (it already loads `p.title_clean`); ensure garbage-title eligible rows report as `no_change` (left `unverified`).

## 3. Scan script (dry-run default, flag, JSONL, counts)

- [x] 3.1 Create `apps/miroflow-agent/scripts/run_paper_identity_scan.py` mirroring `scripts/run_name_identity_scan.py`: dry-run by default; `--apply` to write; `--json-output`/`--archive` for per-row JSONL decisions (paper_id, verdict, confidence, reasoning, prior_identity_status, gate source spans); `_ScanStats`-style counts (`examined / rejected / unchanged / flipped_back / restored`).
- [x] 3.2 Read `PAPER_IDENTITY_GATE_ENABLED` in the script (not the module); default conservative/off; any of `0/false/off/no` → skip gate and writes (exit 0 with a "disabled" note). Keep this flag separate from `NAME_IDENTITY_GATE_ENABLED` and the `paper_collector` `identity_gate_enabled`.
- [x] 3.3 Scan flow: select prof-page-only papers; for each, determine `has_verified_link` from `professor_paper_link`; call `decide_identity_status_rejection`; in dry-run record the would-be decision; on `--apply` call `apply_identity_status_rejection` / `restore_identity_status` as appropriate. Reuse `professor/paper_identity_gate.batch_verify_paper_identity` and the `run_identity_verify_candidate_links.py` decision flow for the per-link verdicts — do **not** modify the gate. **Refined in 2.5 to pass `title_clean`.**

## 4. Milvus + retrieval interaction

- [x] 4.1 Confirm `paper/milvus_backfill._is_indexable_paper` already excludes `identity_status in {rejected, merged}` (no code change); add/extend a unit test asserting a `rejected` paper is not indexable. Document that a Milvus re-backfill is required for the change to take effect on already-indexed rows (operator runbook note).

## 5. Tests (RED → GREEN)

- [x] 5.1 RED: `tests/data_agents/paper/test_identity_status_writer.py` — `decide_identity_status_rejection` returns `reject` only for (no verified link + prof_page_only); returns `no_change` when a verified link remains or source != prof_page_only. **Updated in 5.6 for the plausible-title condition.**
- [x] 5.2 RED: `apply_identity_status_rejection` sets `identity_status='rejected'`, records `prior_identity_status`, files a stage-`identity_gate` `pipeline_issue` with `run_id`, and does not mutate `quality_status`; idempotent on re-apply.
- [x] 5.3 RED: `restore_identity_status` restores the exact `prior_identity_status` and resolves the issue when a `verified` link exists.
- [x] 5.4 RED: `run_paper_identity_scan.py` dry-run makes no writes and emits JSONL + counts; `--apply` writes only qualifying rejections; flag-off skips. (Script test mirroring `tests/scripts/test_run_name_identity_scan*`.)
- [x] 5.5 GREEN: implement until all RED tests pass; run `uv run pytest tests/data_agents/paper/test_identity_status_writer.py tests/scripts/test_run_paper_identity_scan.py -n0`.
- [x] 5.6 RED+GREEN (plausible-title guard): extend `test_decide_reject_only_when_no_verified_link_and_prof_page_only` to pass `title_clean` and assert `reject` requires a plausible title; add `test_decide_no_change_for_garbage_title` asserting `no_change` (reason `implausible_title`) when `is_plausible_paper_title` is False even though no verified link + prof_page_only. Re-run the writer + scan tests.

## 6. Real evidence (dry-run first, bounded apply, re-backfill)

- [ ] 6.1 Run `run_paper_identity_scan.py` (dry-run) against `miroflow_real` (unset proxy vars per project env); save counts + sampled JSONL to `.agents/runs/wire-paper-identity-gate-rejection/`; compare rejected count to the 1.2 baseline.
- [ ] 6.2 If reject rate is sane, run `--apply` on a bounded slice; verify `paper.identity_status='rejected'` only for qualifying rows and `pipeline_issue` rows filed with `run_id`.
- [ ] 6.3 Re-backfill Milvus (`scripts/run_milvus_backfill.py`); verify the excluded-row count matches the applied rejections; spot-check a rejected paper no longer returns in retrieval.

## 7. Acceptance, validation, ledger

- [ ] 7.1 Fill `acceptance.md` against the spec scenarios (each scenario → evidence artifact or gap).
- [ ] 7.2 `openspec validate wire-paper-identity-gate-rejection --strict` exits 0.
- [ ] 7.3 Register the change in `openspec/change-ledger.md` (status `in-implementation` → `tasks-complete-not-archived`); note it supersedes no archived change.
- [ ] 7.4 Update the W0b card in `docs/plans/2026-06-16-dirty-data-gap-closure-portfolio.md` to the Gap B definition and re-route "unverified promotion" to W0a/W2a (already drafted — verify consistency).
