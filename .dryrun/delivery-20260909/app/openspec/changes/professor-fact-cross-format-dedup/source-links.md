# Source Links: professor-fact-cross-format-dedup

Legacy / current-behavior sources consulted when baselining this change.

## Current spec (authority for the modified requirement)

- `openspec/specs/professor-fact-extraction/spec.md` — *Requirement: Backfill is
  idempotent and failure-isolated* already mandates
  `professor_id + fact_type + normalized_fact_key` dedup and "update or
  supplement, not duplicate". This change **strengthens the key to semantic**;
  it does not invent the dedup obligation.

## Code (the seven insert paths + the weak key)

- `apps/miroflow-agent/src/data_agents/professor/canonical_writer.py` —
  `_upsert_fact` (≈L1180), `_normalized_fact_key` (≈L1320, the literal key to be
  replaced), `_format_education_entry`/`_format_work_entry` (≈L1453, pipe
  emitters, Path A).
- `apps/miroflow-agent/src/data_agents/professor/fact_backfill.py` —
  `persist_extracted_professor_facts` (≈L136), `_retire_duplicate_active_facts`
  (≈L196), `_retire_active_facts_by_key`, `_fact_key`, `_english_original_fact_key`
  (≈L268-281, to be folded into the writer).
- `apps/miroflow-agent/scripts/run_professor_llm_field_extract.py` — Path B raw
  INSERT (≈L223), `_facts_from` JSON builder (≈L72).
- `apps/miroflow-agent/scripts/run_unified_professor_crawl.py` — Path C raw
  INSERT (≈L400), fact map (≈L361).
- `apps/miroflow-agent/scripts/run_professor_web_enrich.py` — Path D `homepage`
  summary INSERT (≈L358).
- `apps/miroflow-agent/scripts/run_topic_split_backfill.py` — Path G
  `research_topic` atomic INSERT (≈L126), source deprecation (≈L114).
- `apps/miroflow-agent/scripts/run_professor_llm_field_extraction_cuhksz_sample.py`
  — Path E (via `_upsert_fact`, field-skip guard).

## Schema (no-change confirmation)

- `apps/miroflow-agent/alembic/versions/V003_init_professor_domain.py` —
  `professor_fact` definition; confirms only a **non-unique** index
  `ix_professor_fact_professor_type` on `(professor_id, fact_type)` and no unique
  constraint on value → `ON CONFLICT DO NOTHING` is a no-op (root cause #2).
- `apps/miroflow-agent/alembic/versions/V007_*` — `run_id` addition (provenance).

## Empirical validation of the key (this session)

- `.agents/runs/professor-fact-within-format-dedup/` — six dedup passes that
  superseded ~23,000 duplicate rows using exactly the key algorithm in
  `design.md §2`, with the `years_core`-from-whole fix that eliminated the
  `2018-2019` vs `2019-2020` false positive. JSONL archives per pass
  (`superseded-2026-06-23.jsonl`, `gloss-prefix-…`, `json-flip-…`,
  `pipe-prose-…`) are the ground-truth fixtures for task 4.1 parity.

## Adjacent (non-overlapping) changes

- `openspec/changes/professor-profile-field-completion-pipeline/` — field
  *completion* (filling missing fields across schools), explicitly leaves the
  extraction-correctness/dedup contract alone. No conflict; cited for boundary.
