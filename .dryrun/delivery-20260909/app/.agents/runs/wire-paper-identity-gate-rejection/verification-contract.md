# Verification Contract — wire-paper-identity-gate-rejection

> Per CLAUDE.md §14.7. Claude-owned. Defines the RED/GREEN boundary before any production-code edit. Codex/Superpowers must not independently change the RED artifact or the gate.
> Re-baselined 2026-06-22 against a fresh `miroflow_real` scan (see `eligibility-baseline.json`). Supersedes the 2026-06-16 draft's 1,519-eligible figure.

## Change
- **OpenSpec change:** `wire-paper-identity-gate-rejection` (Standard, behavior-affecting).
- **Capability:** `paper-identity-status` (new).
- **Specs:** `openspec/changes/wire-paper-identity-gate-rejection/specs/paper-identity-status/spec.md`.
- **Tasks:** `openspec/changes/wire-paper-identity-gate-rejection/tasks.md` (12/24 done; pending = 2.4, 2.5, 5.6, 6.1–6.3, 7.1–7.4).
- **Portfolio:** `docs/plans/2026-06-22-professor-paper-gap-closure-portfolio.md` Phase 1 (re-baselines the 6/16 W0b card).

## Change Type
- `deterministic_module`

Behavior-affecting **at the retrieval boundary** (changes which paper rows are indexed), but the **new code surface is deterministic**: a pure guard (`decide_identity_status_rejection`), a DB writer + restorer (`apply_identity_status_rejection` / `restore_identity_status`), and a scan script (`run_paper_identity_scan.py`). The LLM same-person gate (`professor/paper_identity_gate.batch_verify_paper_identity`) is **reused unchanged** — no change to its threshold (0.8), inputs, or fail-safe-to-reject semantics.

## Superpowers Mode
- `full_tdd_allowed`

Per §14.7: deterministic modules / storage adapters / tool wrappers → full Superpowers TDD, RED = unit/contract tests. NOT agentic-RAG/badcase work, so a unit/contract RED is sufficient (no eval-first/trace-replay). TDD must NOT touch the gate.

## RED artifact (must fail before implementation)
Contract/unit tests, written first, all failing:

1. `tests/data_agents/paper/test_identity_status_writer.py::test_decide_reject_only_when_no_verified_link_and_prof_page_only` — `decide_identity_status_rejection` returns `reject` iff `(not has_verified_link) and (canonical_source == 'prof_page_only') and is_plausible_paper_title(title_clean)`; `no_change` otherwise (verified-link-remains; non-prof-page-only source; **garbage title → reason `implausible_title`**). Covers the 2³ condition matrix, not one case. (2.4/2.5/5.6 — the pending slice.)
2. `test_apply_rejection_sets_identity_status_and_files_issue_without_terminalizing_quality` — `apply_identity_status_rejection` sets `identity_status='rejected'`, records `prior_identity_status`, files a stage-`identity_gate` `pipeline_issue` with `run_id`, leaves `quality_status` unchanged, idempotent on re-apply. (2.2 — done; must stay green.)
3. `test_restore_returns_prior_identity_status_and_resolves_issue` — `restore_identity_status` restores the exact `prior_identity_status` and resolves the issue. (2.3 — done; must stay green.)
4. `tests/scripts/test_run_paper_identity_scan.py` — dry-run writes nothing and emits JSONL + counts; `--apply` writes only qualifying rejections; `PAPER_IDENTITY_GATE_ENABLED` falsy skips gate+writes. (5.4 — done; must stay green; extend for `title_clean` in 2.5.)
5. `tests/.../test_milvus_backfill_*` (extend) — `_is_indexable_paper` returns False for `identity_status='rejected'`. (4.1 — done.)

Test #1 is the live RED (pending 2.4). #2–#5 are already green and must not regress.

## Oracle Strength
- Observable: the 2³ guard matrix + reason enum; on `--apply` the exact `identity_status` transition + `pipeline_issue` fields (stage `identity_gate`, `run_id` non-null, prior recorded) + `quality_status` **unchanged**; idempotent re-apply; exact `prior_identity_status` restore.
- Stronger than a snapshot: the matrix covers the full condition space; the `quality_status`-unchanged assertion guards the load-bearing invariant (rejection must not terminalize quality); the restore assertion guards reversibility.
- Complementary real check: the real `miroflow_real` dry-run count (AC2) + the post-apply `ready`-untouched audit (AC3) + Milvus re-backfill spot-check (AC4).

## GREEN
Minimal implementation that turns RED #1 green, no weakening:
- Extend `decide_identity_status_rejection(*, has_verified_link, canonical_source, title_clean)` with the third condition (`is_plausible_paper_title(title_clean)` from `paper/title_quality`); new reason `implausible_title`. Update `run_paper_identity_scan.py` to pass `p.title_clean`.
- No migration (V020 column reused); no change to `milvus_backfill._is_indexable_paper`; no change to the LLM gate or the 0.8 threshold.

## Real-interaction / acceptance evidence (not RED; required for acceptance.md)
- **Eligibility baseline (task 1.2)**: `eligibility-baseline.json` — re-baselined 2026-06-22 to **28,928** eligible (was 1,519 on 6/16; growth driven by fresh UPC/crawl `prof_page_only`/`unverified`/candidate-only papers). 0 `ready` in the eligible set.
- **Real dry-run (task 6.1)**: `PAPER_IDENTITY_GATE_ENABLED=1`, unset the 6 proxy env vars (localhost must not be hijacked), run `run_paper_identity_scan.py` dry-run on `miroflow_real`; save counts + sampled JSONL. Compare rejected count to 28,928.
- **LLM-cost note**: 28,928 gate calls is a heavy LLM operation; batch + rate-limit + monitor. The 6/16 sample found 92% garbage titles — if that holds, the plausible-title guard keeps the *reject* verdict to a small subset; the dry-run (Slice B) reveals the true split.
- **Bounded `--apply` (task 6.2)**: verify only qualifying rows flipped + `pipeline_issue` rows filed with `run_id`; post-apply audit `SELECT quality_status, count(*) FROM paper WHERE identity_status='rejected' AND updated_at > now()-interval '1 day' GROUP BY 1` must show 0 `ready`.
- **Milvus re-backfill (task 6.3)**: spot-check a rejected paper no longer returns in retrieval.

## Acceptance contract (AC1–AC6) — maps to `acceptance.md`
- AC1: guard + RED #1 green (3-condition, plausible-title).
- AC2: dry-run counts saved + compared to 28,928 baseline.
- AC3: bounded apply — only qualifying rows rejected; **0 `ready` touched** (audited).
- AC4: Milvus re-backfill excludes rejected; spot-check passes.
- AC5: reversibility — `restore_identity_status` works; `quality_status` never mutated.
- AC6: `openspec validate wire-paper-identity-gate-rejection --strict` exits 0; ledger → `tasks-complete-not-archived`.

## Verification commands
- RED: `cd apps/miroflow-agent && uv run pytest tests/data_agents/paper/test_identity_status_writer.py::test_decide_no_change_for_garbage_title -n0` (fail until 2.4).
- GREEN: `cd apps/miroflow-agent && uv run pytest tests/data_agents/paper/test_identity_status_writer.py tests/scripts/test_run_paper_identity_scan.py -n0`.
- Regression: `cd apps/miroflow-agent && uv run pytest tests/data_agents/paper/ -n0`.
- Dry-run (real): `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy no_proxy NO_PROXY && cd apps/miroflow-agent && PAPER_IDENTITY_GATE_ENABLED=1 uv run python scripts/run_paper_identity_scan.py --dsn "$DATABASE_URL" --json-output .agents/runs/wire-paper-identity-gate-rejection/dry-run-<date>.jsonl`.
- Apply (bounded, post-AC2): `... --apply --limit <N> ...` then the `ready` audit above.
- Milvus: `cd apps/miroflow-agent && uv run python scripts/run_milvus_backfill.py`.
- Validate: `openspec validate wire-paper-identity-gate-rejection --strict`.

## Do-not rules (Codex)
- Do not modify `professor/paper_identity_gate.py`, `paper/milvus_backfill.py`, or any alembic migration.
- Do not promote the **53,165** `unverified` rows wholesale — only the W0b-eligible 28,928 (prof_page_only + no verified link + plausible title). The other ~24,237 non-prof_page_only unverified → Phase 6 D7. (Prior drafts cited "~7,297" — stale; the 6/22 count is 53,165 unverified / 28,928 eligible.)
- Do not touch `apply_identity_gate_reevaluation` (Gap A).
- Do not set `quality_status='rejected'` on the rejection path.
- Do not `--apply` without a prior dry-run artifact whose counts are recorded and reviewed.
- Report back per slice with: files changed, test command + pass count, and the artifact paths produced.

## Rollback
Fully reversible — `restore_identity_status` flips a row back when a `verified` link appears; `PAPER_IDENTITY_GATE_ENABLED=0` kills the gate with no writes; rejected rows can be bulk-restored by re-scanning with the gate off + a restore pass. No irreversible column overwrite (contrast the name-gate `ON CONFLICT DO UPDATE` nulling footgun).
