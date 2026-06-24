# Design: professor-fact-cross-format-dedup

## 1. Root-cause summary

Seven insert paths write `professor_fact` in three incompatible encodings.

| Path | Trigger | Format | Dedup today |
|------|---------|--------|-------------|
| A | `write_professor_bundle` (homepage rules) `canonical_writer.py` | pipe | `_upsert_fact` (literal key) |
| B | `run_professor_llm_field_extract.py` | JSON | **none** (raw INSERT, no-op ON CONFLICT) |
| C | `run_unified_professor_crawl.py` | JSON | **none** (raw INSERT) |
| D | `run_professor_web_enrich.py` | prose `homepage` | **none** (raw INSERT) |
| E | `run_professor_llm_field_extraction_cuhksz_sample.py` | bilingual prose | `_upsert_fact` (literal) + field-skip |
| F | `run_professor_fact_backfill.py` → `persist_extracted_professor_facts` | bilingual prose | `_upsert_fact` + `_retire_duplicate_active_facts` (literal) |
| G | `run_topic_split_backfill.py` | bare `research_topic` | **none** (raw INSERT; deprecates source) |

Two defects compound:

1. The only dedup key — `_normalized_fact_key` / `_fact_key`
   (`canonical_writer.py:1320`, `fact_backfill.py:279`) — is a literal
   whitespace-collapsed case-folded string. It cannot match pipe↔JSON↔prose↔
   bilingual twins, so `_upsert_fact` inserts all of them.
2. Paths B/C/D/G bypass `_upsert_fact` entirely with `INSERT … ON CONFLICT DO
   NOTHING`. `professor_fact` has no unique constraint on
   `(professor_id, fact_type, value*)` (only a non-unique index
   `ix_professor_fact_professor_type`), so `ON CONFLICT` never fires and every
   insert adds a row.

## 2. The fix

Two parts. **No schema change.**

### Part 1 — `fact_dedup_key.py` (new, pure, unit-tested)

Pure functions, no DB, no LLM. The key implementation that already validated
clean on the live data (this session's six dedup passes superseded ~23,000
rows with zero confirmed false positives after the years-from-whole fix).

```python
def semantic_fact_key(fact_type, value_raw, value_normalized=None) -> tuple | None:
    """Comparable logical-fact key, format-independent. None == unkeyable."""
```

Algorithm:

1. **Format detect** on `value_raw`:
   - JSON object → parse; fields `school`/`organization`, `degree`/`role`,
     `field`.
   - pipe (`" | "` present) → split into up to 4 parts `[org, role/degree,
     field, years]`.
   - else prose.
2. **Extract components** (school/org, degree-or-role, field, years):
   - `ascii_core(part)` = ordered ASCII word tokens (len≥2), lowercased. For
     school/org+field combined into a token set for order-independence.
   - `cjk_set(part)` = set of CJK runs (stable across bilingual flips).
   - `degree_level(part)` = synonym map
     (`phd`/`master`/`bachelor`/`visit`/`postdoc`/…, covering `Ph.D.`,
     `Doctor of Engineering`, `博士`, `硕士`, `学士`, `访问学者`, …);
     fallback = the ASCII token set (never over-collapses).
   - `years_core(whole_value)` = `(19|20)\d\d` runs scanned across the
     **whole** value (not just the 4th pipe field — this is the fix that
     eliminated the `2018-2019` vs `2019-2020` false positive).
3. **Build key by fact_type family**:
   - structured (`education`, `work_experience`):
     `(ascii_token_set(org∪field), cjk_set(org), degree_level, years_core)`.
   - freeform (`award`, `academic_position`, `research_topic`, `homepage`):
     `(ascii_token_set(whole), cjk_set(whole), years_core(whole))`.
4. Return `None` when the key would be empty (e.g. all-whitespace) so the
   writer falls back to the legacy literal key (defensive — never silently
   collapse two empty values).

`completeness_score(fact_type, value_raw, value_normalized) -> tuple` for
keep-richest:

```text
(is_structured, n_populated_fields, has_year_range, len(value_raw))
```

`is_structured` = True for pipe or valid JSON. Compared lexicographically;
higher wins. Structured-with-more-fields beats prose; pipe-with-years beats
JSON-without-years.

### Part 2 — Universal writer

Upgrade `canonical_writer.py::_upsert_fact` to:

1. `key = semantic_fact_key(...)`; if `None`, fall back to the current literal
   key (preserves exact-match behavior for degenerate values).
2. scan active `(professor_id, fact_type)` rows; for each, compute its semantic
   key.
3. matches = active rows whose key == candidate key.
4. if no match → INSERT.
5. if matches:
   - pick the existing row with the highest `completeness_score`;
   - if `score(candidate) > score(best_existing)` → supersede `best_existing`
     (`status='superseded'`, keep its provenance, set `run_id` COALESCE) and
     INSERT the candidate;
   - else → UPDATE `best_existing` in place (refresh `value_normalized`,
     `source_page_id`, `evidence_span`, `confidence`, `run_id`) and supersede
     any *other* semantic-key twins (rn>1) — i.e. one canonical active row.

`fact_backfill.py::_retire_duplicate_active_facts` + `_fact_key` +
`_english_original_fact_key` are **removed**: the upgraded `_upsert_fact`
subsumes them (keep-richest + multi-twin retire in one pass).
`persist_extracted_professor_facts` drops its post-insert retire call and
reports the writer's `inserted/updated/superseded` counts.

The four raw-INSERT paths (B/C/D/G) are refactored to call `_upsert_fact`
(replacing the `INSERT … ON CONFLICT DO NOTHING` statements). Path-specific
quirks preserved:
- D (`fact_type='homepage'` profile summary): the "only write if summary grew"
  guard stays; the call simply goes through the writer.
- G (`research_topic` split): the source-compound deprecation stays; the
  atomic-topic inserts go through the writer.

## 3. False-positive safety (why this is safe)

Every guard is backed by a contract test (see tasks/acceptance) and was
empirically validated on live data this session:

- `years_core` scans the whole value → distinct periods never collapse (the
  single fix that took work near-dups from 305→250 by excluding the
  2018-19/2019-20 overlap).
- `degree_level` synonym map reconciles `Ph.D.`/`Doctor of Engineering`/`博士`
  but two Bachelors with different fields keep distinct `field` token sets.
- freeform keys include `cjk_set` + `years` → two editorial roles at the same
  venue (the `Energy Storage Materials` `2020 科学执行编辑` vs `2022 副编辑`
  case) stay distinct.
- `value_code` and any taxonomy join are untouched.

Conservative defaults: a `None` key falls back to the literal key (never
collapse two unkeyable values); keep-richest only *upgrades* when the
candidate is strictly richer, otherwise it updates in place (no data loss).

## 4. Why not a unique constraint?

A DB unique constraint on `(professor_id, fact_type, semantic_key)` would
require persisting the key as a column + a backfill + a generator. That is
real hardening but is **not required** to stop duplication (the writer
enforces it at application level, matching the existing spec's stance), and it
adds migration/rollback risk. Listed in `debt-register.md` as a future
hardening; explicitly **out of scope** for this change's acceptance.

## 5. Why not output-format unification?

Keep-richest already yields exactly one active fact per logical entry, so the
display is clean regardless of which format survives. Mandating one canonical
format changes `value_raw` shape and every consumer that parses it (admin
console serializers, RAG summary builders, exports) — a separate, riskier
change. Deferred.

## 6. Verification boundary (per CLAUDE.md §14.7)

This change is **deterministic** (normalization + dedup logic, no LLM, no
routing). RED = unit + contract tests; full Superpowers TDD is allowed.
GREEN = the writer passes the cross-format idempotency and false-positive
contracts. No eval-first/trace-debug requirement (this is not RAG/routing/
prompt/policy work). See
`.agents/runs/professor-fact-cross-format-dedup/verification-contract.md`.

## 7. Rollback

Pure ingest-behavior change — revert the code. To restore a clean DB state
after a reverted run, re-execute the one-shot dedup
(`.agents/runs/professor-fact-within-format-dedup/` JSONL archives + the
repeatable scan). No irreversible migration.

## 8. Open questions

- Should the writer also dedup **across fact_types** (e.g. a `research_topic`
  that duplicates an `award` string)? **No** — cross-type semantic match is
  unsafe and out of scope; the key is per `(professor_id, fact_type)`.
- Should keep-richest prefer pipe over JSON when both carry the same fields?
  Yes — pipe-with-year-range scores higher via `has_year_range`. If both are
  field-equal and year-less, length tiebreak keeps the more descriptive one.
