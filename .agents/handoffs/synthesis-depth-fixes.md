# Handoff — Synthesis-Depth Fixes (path-to-90 workstream 1)

> Claude → (inline) implementation. Status: spec+plan committed; inline execution starting.

## Contract (doc-as-contract)

- Spec: `docs/superpowers/specs/2026-07-07-synthesis-depth-fixes-design.md`
- Plan: `docs/superpowers/plans/2026-07-07-synthesis-depth-fixes.md`
- Tests: `apps/admin-console/tests/test_chat_synthesis_depth.py`
- Code: `apps/admin-console/backend/api/chat.py`
- GREEN gate: `apps/admin-console/scripts/eval_true_accuracy.py --runs 3`

## Task

3 code-level synthesis fixes (L3/L4), one commit each, then eval:
1. Fix 3 — `_call_gemma_synthesis` add `temperature=0` (chat.py:3840)
2. Fix 1 — list-entity enrichment (compact helpers + `_enrich_list_entities` + extend render Path A 3633-3650 & Path B 3747-3777)
3. Fix 2 — `_reformulate_query_for_search` (local qwen3.6) wired into the web-search block, retry once on 0 results for `qa` intent only; move `intent` computation earlier
4. Eval `--runs 3`; record results to `docs/solutions/`

Target: 9/19 (47%) → ~12-13/19 (~60-70%). No retrieval regression.

## OpenSpec discrepancy — recorded (per user instruction 2026-07-07)

1. The prior session summary mentioned an OpenSpec change named `intent-aware-synthesis`
   as "created + validated".
2. **`openspec/` does not exist on disk in this branch** — verified: `ls openspec/` →
   "No such file or directory"; `git ls-files openspec/` → empty; not gitignored, simply
   absent. The intent-aware-synthesis *feature* was implemented (code verified:
   `_detect_answer_intent` + 5 templates at chat.py:155, 4006-4016), but the OpenSpec
   *change artifact* was never persisted to this branch.
3. Therefore this task uses **doc-as-contract** — the committed spec + plan + tests above
   are the behavior contract. No reference to `intent-aware-synthesis` OpenSpec change
   remains in the contract docs.
4. **No OpenSpec validation was run** (there is nothing to validate against).
5. Future OpenSpec adoption — bootstrapping `openspec/` + its validation tooling — is a
   separate harness/setup change and must NOT be mixed into these small fixes.

## Verification (per CLAUDE.md §8)

Pure helpers are unit-tested (`test_chat_synthesis_depth.py`). End-to-end synthesis
behavior (deeper answers, qid19/20/22 unblocked, qid11 stable) is **eval-first** —
`eval_true_accuracy.py --runs 3`, proxy unset, backend DOWN (Milvus single-writer lock).

## Next action

Implement Task 1 (Fix 3, one line), commit; Task 2 (Fix 1), commit; Task 3 (Fix 2),
commit; Task 4 (eval + record). Owner: Claude (inline).
