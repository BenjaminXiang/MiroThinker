# Verification Contract: professor-fact-cross-format-dedup

Change-id: `professor-fact-cross-format-dedup`
Spec: `openspec/changes/professor-fact-cross-format-dedup/specs/professor-fact-extraction/spec.md`

## Change classification

- **Type**: deterministic normalization + dedup logic. **No LLM, no RAG
  routing, no prompt, no policy, no tool-choice.**
- **Weight**: Standard (behavior-affecting: persisted `professor_fact` row
  counts / dedup semantics). No schema migration.
- Per CLAUDE.md §14.7 → deterministic module → **full Superpowers TDD is
  allowed** with **unit/contract tests as RED**.

## RED artifact (must exist before GREEN)

1. `tests/data_agents/professor/test_fact_dedup_key.py` — pure-function unit
   tests asserting the spec's collapse cases AND every false-positive guard
   (distinct period / field / role; degree synonyms; gloss prefix; bilingual
   flip; order-independent tokens; `None` fallback).
2. `tests/data_agents/professor/test_upsert_fact_dedup.py` — writer contract
   tests against a fake or real connection:
   - pipe + JSON + bilingual of one degree → exactly 1 active row, richest kept;
   - year-less JSON superseded by pipe-with-years (keep-richest upgrade);
   - two distinct periods (2018-2019 vs 2019-2020) → 2 active rows;
   - two distinct fields at same school → 2 active rows;
   - idempotent re-run → no new rows, no status flips.

These tests are written first and MUST fail (RED) before the implementation.

## GREEN

Implementation (`fact_dedup_key.py` + upgraded `_upsert_fact` + 4 path
refactors) makes RED pass. The four raw-INSERT paths no longer issue
`INSERT INTO professor_fact … ON CONFLICT` for active rows (verified by grep).

## Allowed Superpowers mode

Full TDD (RED → GREEN → REFACTOR). No eval-first / trace-debug requirement
(not RAG/routing/prompt/policy work).

## Regression safety

- A literal-key fallback must remain for `None` (unkeyable) values so the
  writer never collapses two empty/deg\enerate facts.
- Existing single-format idempotency (the current `_upsert_fact` exact-text
  behavior) must still hold for values the semantic key cannot parse — covered
  by keeping the legacy path as the `None` fallback.

## Out of scope for verification

- DB unique constraint (debt-register only).
- Re-cleaning existing data (done; parity scan is an optional op artifact).
- Output-format unification.
