# Verification Contract

## Change

- Change ID: close-workbook-gaps
- OpenSpec path: `openspec/changes/close-workbook-gaps/`
- Run workspace: `.agents/runs/close-workbook-gaps/`

## Change Type

- `agentic_rag_or_chat_behavior`

## Superpowers Mode

- `eval_first_required` (workbook scenario eval is the primary gate; unit
  tests alone are not sufficient GREEN evidence per
  `openspec/specs/development-methodology/spec.md`)

## RED Artifact

- Type: scenario eval (hardened workbook runner, live endpoint)
- Path: `.agents/runs/testset-baseline-20260909/run_testset.py`
  (three-layer judgment from `harden-serving-test-harness`), run against
  `http://127.0.0.1:18188`
- Expected failing reason: B1 — g17-t1 yields 1 CN id sourced from web with
  citations_local=0 (baseline `results-ds-flash-systemd.json`); the
  deployment-line read path never scans field-level patent→applicant
  bindings.
- Behavior class covered: company→patent traversal for any company with
  id-bound patents (7,078 bindings in s12f lookup), not only 优必选.

## Oracle Strength

- Observable behavior checked: answer text patent-id count (regex
  `CN\d{9,}[A-Z]?`), citations_local ≥1, and absence of web-sourced patent
  lists when local bindings exist.
- Why stronger: the oracle binds to local-data provenance (citation type),
  not just string presence — a web-sourced CN-id list cannot pass.
- LLM/agentic contract: full SSE scenario run on the live endpoint; replay
  gate guards the 7 reference sessions.

## Diagnosis / Anti-Overfit Check

- Root-cause hypothesis: the G3-simple direct scan exists only in the data
  line (commit `790f4d1`); the deployment line reads only relationship
  tables (121 rows / 48 companies, 优必选 absent).
- Sibling patterns searched: professor→company and paper→professor
  traversals (same direct-scan pattern, planned as C3/C4); simple_serve's
  prototype scan (defective: pronoun over-truncation, citation ordering) —
  not ported.
- Why not one-example: the scan keys on company_id bindings generically;
  g17-t1 is the workbook witness, but any bound company exercises it.
- Anti-hardcode: assertion requires citations_local ≥1 — hardcoding CN ids
  into the answer template cannot produce local citations.

## Context / Dependency Surface

- Source OpenSpec requirement(s): this change's spec delta
  (`canonical-v2-chat` company→patent traversal).
- Legacy/source-of-truth docs: evidence doc §九 GAP-01; data-line commit
  `790f4d1`.
- Affected modules:
  `.worktrees/canonical-v2-s11-consolidation/.../canonical_v2/knowledge_read_isolated.py`
  (serving line for 18188).
- Existing tests/evals likely affected: replay gate (must stay 7/7);
  canonical_v2 read-path tests.
- Regression surface: company→patent answers, citation assembly.
- External dependencies: live 18188 service; pack lookup SQLite (read-only).

## Mock Policy

- Mocks used: none in the scenario eval.
- Behavior not mocked away: end-to-end retrieval + rendering + citations.
- Complementary real check: direct SQLite probe of the pack lookup
  confirming the returned CN ids are the bound ones (no fabrication).

## GREEN Criteria

- g17-t1 assertion GREEN on the live endpoint (≥3 CN ids,
  citations_local ≥1, ids verified against lookup bindings).
- Replay gate 7/7 after restart.
- canonical_v2 focused tests pass; no pre-existing-passing test broken.
- Gap registry entry GAP-01 flipped with evidence archived.

## Forbidden Shortcuts

- No hardcoded 优必选 patent lists.
- No web-sourced patent list presented as local.
- No weakening of the runner assertion to force GREEN.

## Verification Plan

- RED command:
  `python .agents/runs/testset-baseline-20260909/run_testset.py --base-url http://127.0.0.1:18188 --only 17`
- Focused GREEN command: same, after B1 port + service restart.
- Regression command:
  `cd apps/admin-console && uv run python scripts/replay_fix_round1.py`
- Real interaction / contract command: SQLite probe comparing returned CN
  ids to `lookup` bindings for the 优必选 company_id.
- OpenSpec validation command: `openspec validate close-workbook-gaps`

## Notes

- Assumptions: 18188 runs from
  `.worktrees/canonical-v2-s11-consolidation` (branch
  `codex/canonical-v2-s12a-ready`); restart via the established
  systemd/wrapper flow.
- Out of scope: assembly-contract repair; simple_serve fixes (prototype,
  retired line); professor→company and paper→professor (C3/C4).
- Rollback note: revert the B1 commit and restart 18188; data untouched.

## B5 — guard-hit graceful degradation (slice contract, 2026-09-11)

- RED artifact (offline): decoder/renderer tests in
  `tests/canonical_v2/test_knowledge_serving_isolated.py` — prose carrying a
  full `<|canonical_v2_selection_v1|>` / `<|canonical_v2_answer_v1|>` marker
  raises `ValueError` today (decoder unit + both renderer modes + the
  rewritten marker-in-answer test); SSE integration test in admin-console
  `test_canonical_v2_chat_http_adapter.py` ends in an `error` event with no
  `done` today. Live-production RED already archived (design.md §B5:
  journalctl + replay failure set, both lines, 2026-09-10).
- GREEN criteria: marker redacted, surrounding prose byte-intact, redaction
  recorded on the decoder; both decode sites set the
  `prose-private-marker-redacted` degradation token via
  `current_turn_trace()`; SSE turn completes with answer+done, no error
  event, journal carries the token; token added to the admin-console
  allowlist (Literal + `_VALID_DEGRADATION_TOKENS`).
- Regression gate: hermetic pack (`test_serving_pack_loader.py` 22 passed),
  B1 focused (`-k "relationship or patent"` 96 passed / 26 skipped),
  fast_boot + index_projection_embedded (14 passed), full
  `test_knowledge_serving_isolated.py`, turn-trace suites — all unchanged
  vs the C2.1s baseline.
- Live evidence (B5.4, main context): same-day differential / replay
  re-run — marker-class empty answers disappear on both sides.
- Out of scope: template fallback for this class (rejected — stays reserved
  for genuine synthesis failure); prompt-side marker suppression.
