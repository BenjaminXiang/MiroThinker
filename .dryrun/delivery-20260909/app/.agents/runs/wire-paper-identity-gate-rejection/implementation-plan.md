# Implementation Plan — wire-paper-identity-gate-rejection (Phase 1)

> Codex-facing execution slices to close W0b. Verification contract: `.agents/runs/wire-paper-identity-gate-rejection/verification-contract.md`. Portfolio Phase 1: `docs/plans/2026-06-22-professor-paper-gap-closure-portfolio.md`.
> Baseline (2026-06-22): 28,928 eligible (unverified + `prof_page_only` + no verified link); 0 `ready` in the eligible set. Real reject rate TBD by slice B dry-run.

## Source docs to read first

- `openspec/changes/wire-paper-identity-gate-rejection/proposal.md` (Why/What Changes/Non-goals)
- `openspec/changes/wire-paper-identity-gate-rejection/tasks.md` (12/24 done; pending = 2.4, 2.5, 5.6, 6.1–6.3, 7.1–7.4)
- `openspec/changes/wire-paper-identity-gate-rejection/acceptance.md` (AC1–AC6)
- `.agents/runs/wire-paper-identity-gate-rejection/verification-contract.md` (RED/GREEN, forbidden shortcuts)
- `apps/miroflow-agent/src/data_agents/paper/identity_status_writer.py` (existing 2.1–2.3 impl)
- `apps/miroflow-agent/src/data_agents/paper/title_quality.py` (`is_plausible_paper_title`, reused)
- `apps/miroflow-agent/scripts/run_name_identity_scan.py` (scan script template to mirror)

## Slices (in order)

### Slice A — Plausible-title guard (tasks 2.4, 2.5, 5.6)
- RED first: extend `tests/data_agents/paper/test_identity_status_writer.py` with `test_decide_no_change_for_garbage_title` (assert `no_change` + reason `implausible_title` when `is_plausible_paper_title` False, even though no verified link + `prof_page_only`) and extend `test_decide_reject_only_when_no_verified_link_and_prof_page_only` to pass `title_clean` and assert `reject` requires a plausible title. Confirm RED fails.
- GREEN: extend `decide_identity_status_rejection(*, has_verified_link, canonical_source, title_clean)` to add the third condition (`is_plausible_paper_title(title_clean)`); new reason `implausible_title`. Update `run_paper_identity_scan.py` to pass `p.title_clean` (already loaded). Do NOT touch the LLM gate.
- Exit: `uv run pytest tests/data_agents/paper/test_identity_status_writer.py tests/scripts/test_run_paper_identity_scan.py -n0` green; full paper test dir green.
- Do-not: weaken the gate threshold; mutate `quality_status`; hardcode a title.

### Slice B — Real dry-run (task 6.1)
- `unset` the 6 proxy vars; `PAPER_IDENTITY_GATE_ENABLED=1`; run `run_paper_identity_scan.py` (dry-run default) against `miroflow_real`; save counts + sampled JSONL to `.agents/runs/wire-paper-identity-gate-rejection/dry-run-<date>.jsonl`.
- Exit: `examined / rejected / unchanged / flipped_back` counts recorded; rejected count compared to the 28,928 baseline (`eligibility-baseline.json`). Expected < 28,928 (guard filters garbage titles). If reject rate looks wrong (>50% of eligible or hits any `ready`), STOP and report — do not proceed to Slice C.
- Do-not: `--apply` in this slice.

### Slice C — Bounded apply (task 6.2)
- After Slice B sign-off: `run_paper_identity_scan.py --apply --limit <N>` on a bounded slice; verify `paper.identity_status='rejected'` only for qualifying rows; verify each has a stage-`identity_gate` `pipeline_issue` with `run_id`.
- Post-apply audit (AC3): `SELECT quality_status, count(*) FROM paper WHERE identity_status='rejected' GROUP BY 1;` — must show 0 `ready`. If any `ready` appears, STOP, restore, report.
- Exit: bounded apply artifact + apply-summary.json; 0 `ready` touched confirmed.
- Do-not: apply the full 28,928 in one pass without Slice C sign-off; apply without a matching dry-run artifact.

### Slice D — Milvus re-backfill (task 6.3)
- `run_milvus_backfill.py` (excludes `{rejected, merged}` via `_is_indexable_paper`); verify excluded-row count matches applied rejections; spot-check a rejected paper no longer returns in retrieval.
- Exit: rebackfill log saved; spot-check artifact; a rejected paper excluded from retrieval.
- Do-not: change `_is_indexable_paper` (already correct); re-backfill before Slice C.

### Slice E — Acceptance, validate, ledger (tasks 7.1–7.4)
- Fill `acceptance.md` AC1–AC6 against the artifacts (Met/Partial/Unmet + path).
- `openspec validate wire-paper-identity-gate-rejection --strict` exits 0.
- Ledger status → `tasks-complete-not-archived`; note re-baseline (28,928 eligible, 0 ready touched).
- Update the W0b card in the portfolio doc to "closed (Phase 1)".
- Exit: acceptance complete; validate green; ledger updated.

## Done criteria (acceptance contract AC1–AC6)

1. AC1 guard + 5.6 tests green (3-condition, plausible-title).
2. AC2 dry-run counts saved + compared to 28,928 baseline.
3. AC3 bounded apply: only qualifying rows rejected; 0 `ready` touched (audited).
4. AC4 Milvus re-backfill excludes rejected; spot-check passes.
5. AC5 reversibility: `restore_identity_status` works; `quality_status` never mutated.
6. AC6 `openspec validate --strict` exits 0; ledger updated.

## Report back

- Slice-by-slice: command + exit status + artifact path; the real reject count (Slice B); the post-apply `ready` audit (Slice C); the Milvus excluded count (Slice D).
- Any blocker, unexpected reject rate, or `ready` touched → STOP and report before proceeding.
