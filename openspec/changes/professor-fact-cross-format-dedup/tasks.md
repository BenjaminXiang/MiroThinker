# Tasks: professor-fact-cross-format-dedup

## 1. Semantic-key module (RED first)

- [ ] 1.1 Create `apps/miroflow-agent/src/data_agents/professor/fact_dedup_key.py` with
      `semantic_fact_key(fact_type, value_raw, value_normalized=None)` and
      `completeness_score(fact_type, value_raw, value_normalized=None)`.
- [ ] 1.2 Unit tests `tests/data_agents/professor/test_fact_dedup_key.py` covering every
      false-positive guard and every collapse case from the spec scenarios:
      pipe↔JSON↔bilingual↔CJK equivalence; degree synonyms; gloss prefix;
      order-independent org tokens; distinct-period / distinct-field /
      distinct-role retention; `None` fallback for empty values.
- [ ] 1.3 `just lint` / `uv run pytest tests/data_agents/professor/test_fact_dedup_key.py`.

## 2. Universal writer

- [ ] 2.1 Upgrade `canonical_writer.py::_upsert_fact` to use `semantic_fact_key`
      with a literal-key fallback when the key is `None`, plus keep-richest
      (supersede poorer twin / update-in-place) and multi-twin retire.
- [ ] 2.2 Remove `fact_backfill.py::_retire_duplicate_active_facts`,
      `_english_original_fact_key`, and the literal `_fact_key`; update
      `persist_extracted_professor_facts` to rely on the writer and report
      `inserted/updated/superseded`.
- [ ] 2.3 Contract tests `tests/data_agents/professor/test_upsert_fact_dedup.py`
      (fake/real conn): (a) same fact in pipe+JSON+bilingual → 1 active row,
      richest kept; (b) keep-richest upgrades year-less JSON → pipe-with-years;
      (c) two distinct periods/fields/roles → 2 active rows; (d) repeated run is
      a no-op (idempotent).

## 3. Route raw-INSERT paths through the writer

- [ ] 3.1 `scripts/run_professor_llm_field_extract.py` (Path B): replace the raw
      `INSERT … ON CONFLICT` with `_upsert_fact`.
- [ ] 3.2 `scripts/run_unified_professor_crawl.py` (Path C): same.
- [ ] 3.3 `scripts/run_professor_web_enrich.py` (Path D, `fact_type='homepage'`):
      route the summary write through `_upsert_fact`; keep the "only write if
      summary grew" guard.
- [ ] 3.4 `scripts/run_topic_split_backfill.py` (Path G, `research_topic`): route
      atomic-topic inserts through `_upsert_fact`; keep source-compound
      deprecation.

## 4. Verification & cleanup parity

- [ ] 4.1 Add a repeatable no-LLM scan script (optional op artifact) mirroring
      this session's dedup passes, gated by an env flag, dry-run default — so a
      reverted run can restore a clean state without bespoke SQL.
- [ ] 4.2 `uv run pytest` (full agent suite) green; `just lint`.
- [ ] 4.3 Update `agent-links.md` / `change-log.md` with implementation evidence.

## Out of scope

- DB unique constraint on `(professor_id, fact_type, semantic_key)` — log in
  `debt-register.md` only.
- Output-format unification (force one canonical `value_raw` shape).
- Re-cleaning existing data (already done this session).
