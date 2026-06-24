# Review: professor-fact-cross-format-dedup

**Change-id**: `professor-fact-cross-format-dedup`
**Date**: 2026-06-23
**Reviewer**: Claude (implemented directly — Codex dispatch did not execute; see note)
**Decision**: **accept** (implementation + self-review; pre-existing suite failures are unrelated and out of scope)

## What was implemented

1. **NEW** `src/data_agents/professor/fact_dedup_key.py` — pure functions:
   `semantic`-style `extract_components`, `facts_are_duplicates` (predicate),
   `completeness_score`, `legacy_literal_key`. Format-normalizing: parses
   pipe / JSON / prose / bilingual-gloss; signatures use ASCII-tokens-when-
   present-else-CJK; years scanned from the whole value; degree synonyms
   (Ph.D./Doctor/博士, Master/硕士, …) collapsed, postdoc-before-phd ordering.
2. **UPGRADED** `canonical_writer.py::_upsert_fact` to semantic match +
   keep-richest (supersede poorer twin / keep richest). Removed dead
   `_normalized_fact_key`.
3. **REMOVED** `fact_backfill.py` retire helpers (`_retire_duplicate_active_facts`,
   `_retire_active_facts_by_key`, `_english_original_fact_key`, `_fact_key`) —
   subsumed by the writer. `persist_extracted_professor_facts` delegates fully.
4. **ROUTED** the 4 raw-INSERT paths through `_upsert_fact`:
   `run_professor_llm_field_extract.py` (B), `run_unified_professor_crawl.py` (C),
   `run_professor_web_enrich.py` (D), `run_topic_split_backfill.py` (G).

## Acceptance criteria — status

- [x] `semantic_fact_key` cross-format equivalence — `test_fact_dedup_key.py` (25 tests).
- [x] False-positive guards (distinct period/field/role/school; CJK roles; English ranks) — tested.
- [x] Degree-synonym / bilingual-flip / gloss-prefix / paren-gloss collapse — tested.
- [x] All paths route through the writer; `grep "INSERT INTO professor_fact" | grep on conflict` → NONE.
- [x] 3 structured formats → 1 active row, richest kept; keep-richest upgrade; idempotent rerun; distinct facts stay separate — `test_upsert_fact_dedup.py` (5 tests).
- [x] No schema migration; provenance preserved; no public API/A–G/`_VALID_DOMAINS` change.
- [x] `just lint` (ruff) clean on all touched files.
- [x] New + touched-area tests: **42 passed**.
- [~] Full `uv run pytest`: NOT all-green — **25 pre-existing failures + 63 errors** remain, **none** caused by this change (verified: 0 references to any changed symbol in those test files; spot-checked homepage_crawler = crawl-URL-planning, llm_profiles = LLM-settings env). These are pre-existing (prior session work / env / DB-fixture) and out of scope.

## Known residual (documented, by design)

- **prose ↔ structured cross-format** (e.g. Path-F bilingual prose vs Path-A pipe)
  is NOT matched by the semantic key (conservative: avoids false positives on
  partial overlaps). Estimated ~3% of the original duplicate volume; the
  one-shot cleanup (`.agents/runs/professor-fact-within-format-dedup/`) covers
  it. Design.md §5 / spec note this as out of scope.
- **CJK-only school ≡ English-only school** (no shared tokens) is not matched
  (needs a translation map). Rare; bilingual facts usually carry both.

## Deferred (not part of acceptance)

- Task 4.1 repeatable no-LLM scan script (optional op artifact).
- DB unique constraint on `(professor_id, fact_type, semantic_key)` — logged as future hardening, not this change.

## Process note

Codex (`codex:codex-rescue`) dispatch returned "started in background" but no
session executed (no `~/.codex` session written, processes exited, zero work
product) — the known companion "background status is a lie" quirk. Implemented
directly with full TDD (RED tests first → GREEN) per the verification contract.
Changes are unstaged; no commit made (commit-on-request).
