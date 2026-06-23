# Verification Contract — paper-implausible-title-cleanup

## Change
- Change ID: `paper-implausible-title-cleanup`
- OpenSpec path: `openspec/changes/paper-implausible-title-cleanup/`
- Run workspace: `.agents/runs/paper-implausible-title-cleanup/`
- Depends on: `wire-paper-identity-gate-rejection` (W0b) — reuses `identity_status_writer`,
  the `rejected` status, the Milvus `{rejected, merged}` exclusion, and
  `is_plausible_paper_title`.

## Change Type
- `deterministic_module`

The title-cleanup scan + writer parameterization + display filter are deterministic.
`is_clearly_garbage_paper_title` is pure rule-based (no LLM). **No LLM anywhere in this change.**

## Superpowers Mode
- `full_tdd_allowed`

Per §14.7: deterministic modules / writers / display filters → full TDD, RED = unit/contract
tests.

## RED artifact
- `tests/data_agents/paper/test_identity_status_writer.py` (extend): title-cleanup-stage
  issues are filed at `title_cleanup` / `paper_title_cleanup_scan` and are distinct from
  W0b `identity_gate` issues.
- `tests/scripts/test_run_paper_title_cleanup_scan.py` (new): dry-run no writes + JSONL +
  counts; `--apply` rejects only implausible-titled `prof_page_only`; plausible unchanged;
  already-rejected/merged skipped; `PAPER_TITLE_CLEANUP_ENABLED` off skips; no LLM called.
- `tests/.../test_domains_paper_list*` (new/extend): `/paper` default-excludes
  `{rejected, merged}`; filter can include them.

## GREEN
- Writer: parameterize `apply_identity_status_rejection(stage=, reported_by=)` +
  `_fetch_open_issue` (optional stage/reported_by filters; `None` = find any, for restore) —
  defaults preserve W0b (`identity_gate` / `paper_identity_scan`).
- Scan: new `run_paper_title_cleanup_scan.py` (no LLM; mirrors W0b scan structure).
- Display: `PAPER_SELECT_SQL` default-excludes `{rejected, merged}` + `SELECT identity_status`
  + admin filter option.

## Verification commands
- RED (writer): `cd apps/miroflow-agent && uv run pytest tests/data_agents/paper/test_identity_status_writer.py -n0` (after adding the title-cleanup test, before GREEN — expect TypeError on the new `stage=` kwarg).
- GREEN: `cd apps/miroflow-agent && uv run pytest tests/data_agents/paper/ tests/scripts/test_run_paper_title_cleanup_scan.py -n0`.
- OpenSpec: `openspec validate paper-implausible-title-cleanup --strict`.

## Do-not
- Do not modify `is_plausible_paper_title` (reused unchanged from W0b).
- Do not mutate `quality_status` on the rejection path.
- Do not invoke any LLM in the title-cleanup scan.
- Do not break W0b's `identity_gate` behavior — the writer defaults MUST preserve it
  (`stage=_STAGE`, `reported_by=_REPORTED_BY`).

## Notes
- Baseline + real dry-run/apply (tasks 1.2, 6.x) wait for the W0b slice B dry-run data
  (the `implausible_title` / `no_change` count). The CODE (this contract) is TDD against
  fakes, independent of that data.
- Rollback: dry-run-first + `PAPER_TITLE_CLEANUP_ENABLED=0` + reversible `identity_status`
  (restore via `restore_identity_status`, which now finds any open identity-status issue).
