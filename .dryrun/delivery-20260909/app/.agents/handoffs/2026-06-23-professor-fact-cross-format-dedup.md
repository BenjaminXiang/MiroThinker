# Codex Handoff: professor-fact-cross-format-dedup

**Change-id**: `professor-fact-cross-format-dedup`
**Spec**: `openspec/changes/professor-fact-cross-format-dedup/specs/professor-fact-extraction/spec.md`
**Design**: `openspec/changes/professor-fact-cross-format-dedup/design.md`
**Verification contract**: `.agents/runs/professor-fact-cross-format-dedup/verification-contract.md`
**Read first**: proposal.md, design.md (§2 algorithm is normative), the existing
`openspec/specs/professor-fact-extraction/spec.md`.

## Goal

Stop `professor_fact` from accumulating duplicate active rows for the same
logical fact across its 7 insert paths. Add a format-normalizing semantic key
and route every insert through one keep-richest writer. **No schema change.**

## Slice scope (implement in this order, TDD)

1. **`src/data_agents/professor/fact_dedup_key.py`** (NEW, pure functions):
   - `semantic_fact_key(fact_type, value_raw, value_normalized=None) -> tuple | None`
   - `completeness_score(fact_type, value_raw, value_normalized=None) -> tuple`
   - Algorithm exactly as `design.md §2`. Reuse the validated patterns: pipe
     split on `" | "`; JSON parse; `ascii_core` (ASCII word tokens ≥2,
     lowercased), `cjk_set` (CJK runs), `degree_level` synonym map, `years_core`
     scanned across the **whole** value. Per-family key shape in §2.3. Return
     `None` when the key would be empty.
2. **Upgrade `canonical_writer.py::_upsert_fact`**: semantic key with literal
   fallback on `None`; scan active `(professor_id, fact_type)` rows; keep-richest
   (supersede poorer / update-in-place; retire extra semantic-key twins rn>1).
3. **Remove** `fact_backfill.py::_retire_duplicate_active_facts`,
   `_english_original_fact_key`, literal `_fact_key`; simplify
   `persist_extracted_professor_facts` to rely on the writer.
4. **Route raw-INSERT paths** through `_upsert_fact`:
   - `scripts/run_professor_llm_field_extract.py` (B),
   - `scripts/run_unified_professor_crawl.py` (C),
   - `scripts/run_professor_web_enrich.py` (D — keep the "summary grew" guard),
   - `scripts/run_topic_split_backfill.py` (G — keep source-compound deprecation).

## Do-not rules

- Do NOT add a DB unique constraint or any Alembic migration.
- Do NOT unify output formats (pipe vs JSON vs prose) — keep-richest handles the
  display problem; format unification is explicitly out of scope.
- Do NOT change evidence shape, `run_id` provenance, classification A–G,
  `_VALID_DOMAINS`, or any serialized public format.
- Do NOT weaken the false-positive guards to make tests pass — if a guard seems
  wrong, update OpenSpec + the verification contract first, then code.
- Do NOT re-clean existing data (already done this session).
- Do NOT hardcode secrets; nothing logged that isn't already.

## RED (write first, must fail)

- `tests/data_agents/professor/test_fact_dedup_key.py` — every collapse case +
  every false-positive guard from the spec scenarios.
- `tests/data_agents/professor/test_upsert_fact_dedup.py` — the 5 writer
  contracts in the verification contract.

## GREEN + checks

- `cd apps/miroflow-agent && uv run pytest tests/data_agents/professor/`
- `cd apps/miroflow-agent && uv run pytest` (full suite, xdist)
- `just lint` from repo root
- `grep -Rn "INSERT INTO professor_fact" apps/miroflow-agent | grep -i "on conflict"`
  → must return nothing (no raw active-row inserts remain).

## Done criteria (report back)

- All RED→GREEN tests pass; full suite green; lint clean.
- The grep proof above.
- A tiny before/after: 3 formats of one degree → 1 active row.
- List of files changed + a one-paragraph summary of any deviation from this
  handoff (with reason).

## Environment note

Codex sandbox blocks localhost; this change needs no DB network for the unit/
contract tests (use a fake connection). If you run anything against the real DB,
unset the 6 proxy env vars first (HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy/
ALL_PROXY/all_proxy) or loopback is hijacked.
