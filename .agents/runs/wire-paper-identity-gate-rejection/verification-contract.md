# Verification Contract — wire-paper-identity-gate-rejection

> Per CLAUDE.md §14.7. Claude-owned. Defines the RED/GREEN boundary before any production-code edit. Codex/Superpowers must not independently change the RED artifact or the gate.

## Change
- **OpenSpec change:** `wire-paper-identity-gate-rejection` (Standard, behavior-affecting).
- **Capability:** `paper-identity-status` (new).
- **Specs:** `openspec/changes/wire-paper-identity-gate-rejection/specs/paper-identity-status/spec.md`.
- **Tasks:** `openspec/changes/wire-paper-identity-gate-rejection/tasks.md`.
- **Portfolio source:** `docs/plans/2026-06-16-dirty-data-gap-closure-portfolio.md` W0b (Gap B).

## Classification
Behavior-affecting **at the retrieval boundary** (changes which paper rows are indexed), but the **new code surface is deterministic**: a pure guard (`decide_identity_status_rejection`), a DB writer + restorer (`apply_identity_status_rejection` / `restore_identity_status`), and a scan script (`run_paper_identity_scan.py`). The LLM same-person gate (`professor/paper_identity_gate.batch_verify_paper_identity`) is **reused unchanged** — this change does not alter its threshold (0.8), inputs, or fail-safe-to-reject semantics.

Per §14.7: deterministic modules / storage adapters / tool wrappers → **full Superpowers TDD is allowed**, with RED = unit/contract tests. This is NOT agentic-RAG/badcase work, so a unit/contract RED is sufficient (no eval-first/trace-replay requirement).

## RED artifact (must fail before implementation)
Contract/unit tests, written first, all failing:

1. `tests/data_agents/paper/test_identity_status_writer.py::test_decide_reject_only_when_no_verified_link_and_prof_page_only` — `decide_identity_status_rejection` returns `reject` iff `(not has_verified_link) and (canonical_source == 'prof_page_only') and is_plausible_paper_title(title_clean)`; `no_change` otherwise (verified-link-remains; non-prof-page-only source; **garbage title → reason `implausible_title`**). Refined 2026-06-16 after the dry-run found 92% of eligible rows had parser-garbage titles.
2. `test_apply_rejection_sets_identity_status_and_files_issue_without_terminalizing_quality` — `apply_identity_status_rejection` sets `identity_status='rejected'`, records `prior_identity_status`, files a stage-`identity_gate` `pipeline_issue` with `run_id`, leaves `quality_status` unchanged, and is idempotent on re-apply.
3. `test_restore_returns_prior_identity_status_and_resolves_issue` — `restore_identity_status` restores the exact `prior_identity_status` and resolves the issue.
4. `tests/scripts/test_run_paper_identity_scan.py` — dry-run writes nothing and emits JSONL + counts; `--apply` writes only qualifying rejections; `PAPER_IDENTITY_GATE_ENABLED` falsy skips gate+writes.
5. `tests/.../test_milvus_backfill_*` (extend) — `_is_indexable_paper` returns False for `identity_status='rejected'`.

These five define the contract. They are the RED; Superpowers may sequence them but must not substitute a different RED.

## GREEN
Minimal implementation that turns the RED green, with no weakening of invariants:
- `paper/identity_status_writer.py` — pure guard + DB writer + restorer (mirror `_reject_implausible_paper` guard at `run_paper_title_enrichment_backfill.py:1085-1106`; stage `identity_gate` from V006 enum).
- `scripts/run_paper_identity_scan.py` — mirror `run_name_identity_scan.py` (dry-run default, `--apply`, JSONL, `_ScanStats`); flag `PAPER_IDENTITY_GATE_ENABLED` read in the script.
- No migration (V020 column reused); no change to `milvus_backfill._is_indexable_paper`; no change to the LLM gate.

## Allowed Superpowers mode
Full TDD on the deterministic slices (RED → GREEN → refactor). TDD must NOT: change the gate, change the 0.8 threshold, weaken evidence/`run_id`, or alter `_VALID_DOMAINS`/A–G. If implementation reveals the RED/GREEN boundary is wrong, **update this contract + OpenSpec first**, then resume.

## Real-interaction / acceptance evidence (not RED; required for acceptance.md)
- Eligibility baseline (task 1.2): SQL count of prof-page-only papers with no verified link, saved as `eligibility-baseline.json`.
- Real dry-run on `miroflow_real` (unset the 6 proxy env vars first — localhost must not be hijacked); rejected count ≈ baseline.
- Bounded `--apply` slice; verify only qualifying rows flipped + `pipeline_issue` rows filed with `run_id`.
- Milvus re-backfill; spot-check a rejected paper no longer returns in retrieval.

## Do-not rules (Codex)
- Do not modify `professor/paper_identity_gate.py`, `paper/milvus_backfill.py`, or any alembic migration.
- Do not promote the ~7,297 `unverified` rows (out of scope → W0a/W2a).
- Do not touch `apply_identity_gate_reevaluation` (Gap A).
- Do not set `quality_status='rejected'` on the rejection path.
- Report back per slice with: files changed, test command + pass count, and the artifact paths produced.
