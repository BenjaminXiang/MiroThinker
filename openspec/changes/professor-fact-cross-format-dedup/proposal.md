# Proposal: professor-fact-cross-format-dedup

## Why

The `professor_fact` table accumulates **duplicate active rows for the same
logical fact** — the same education / work_experience / academic_position /
award entry stored 2–4 times in incompatible surface formats:

- pipe `school | degree | field | years` (homepage rule extractor, Path A),
- JSON `{"school","degree","field"}` (LLM field extractors, Paths B/C),
- bilingual prose `English original (中文翻译)` (LLM extractors, Paths E/F),
- CJK prose / bare strings (various).

On a freshly-audited snapshot, **2,487 professors (≈73%) had >3 active
education facts** and the median "extra" fact was a cross-format / bilingual
twin of an existing one. Users see the duplication directly: every active row
is rendered, so a single degree appears 2–3 times.

The `professor-fact-extraction` capability **already mandates** idempotent
dedup: "duplicate detection MUST use `professor_id + fact_type +
normalized_fact_key` … if the same fact is seen again with different
provenance, the existing active fact is updated or supplemented rather than
creating another active row." But the implementation of `normalized_fact_key`
is a **literal, whitespace-collapsed, case-folded string** that cannot match a
pipe value against its JSON / prose / bilingual twin. Worse, **four of seven
insert paths bypass dedup entirely** with raw `INSERT … ON CONFLICT DO
NOTHING`, and `professor_fact` has **no unique constraint** on
`(professor_id, fact_type, value*)` — so `ON CONFLICT` is a no-op and every
raw insert adds a new active row.

A one-shot cleanup has already superseded ~23,000 duplicate rows this session,
but **without a root-cause fix every future ingest re-creates them.** This
change makes ingestion itself non-duplicating.

This change is **behavior-affecting** (ingestion dedup semantics, persisted
`professor_fact` row counts) and **Standard** weight.

## What Changes

1. **MODIFY** the existing *Backfill is idempotent and failure-isolated*
   requirement in `professor-fact-extraction`: `normalized_fact_key` becomes a
   **format-normalizing semantic key** that parses pipe / JSON / prose /
   bilingual-gloss encodings into one comparable key, instead of a literal
   whitespace-collapsed string.

2. **ADD** a *Universal dedup-aware writer* requirement: **every** professor
   `_fact` insert path routes through a single writer that consults the
   semantic key and applies **keep-richest** (supersede the poorer twin,
   structured-with-more-fields wins). No path may raw-`INSERT` an active fact.

3. **ADD** a *Semantic key correctness* requirement naming the
   false-positive guards the key MUST satisfy (distinct field/period/org are
   NOT collapsed; bilingual flips and gloss prefixes ARE).

Non-goals (deferred):

- **Output-format unification** is explicitly out of scope. Because
  keep-richest guarantees exactly one active fact per semantic key, the user
  display is clean regardless of which surface format survives. Mandating one
  canonical format is a separate, riskier change (it changes `value_raw`
  shape and every consumer that parses it).
- Does not re-clean existing data (the one-shot dedup already ran; this change
  only prevents future re-duplication). A repeatable cleanup script may be
  offered as an operational artifact but is not part of the spec contract.
- Does not change roster/paper/identity collection, classification A–G,
  `_VALID_DOMAINS`, evidence shape, or any serialized public format.

## Capabilities

### Modified Capabilities
- `professor-fact-extraction` — strengthen the dedup key to semantic +
  require a universal writer (delta in `specs/`).

### New Capabilities
<!-- none -->

## Impact

- **Affected code** (all under `apps/miroflow-agent/`):
  - NEW `src/data_agents/professor/fact_dedup_key.py` — pure semantic-key +
    completeness-score functions (unit-tested, no DB).
  - UPGRADE `src/data_agents/professor/canonical_writer.py::_upsert_fact` to
    use the semantic key + keep-richest (replaces `_normalized_fact_key`).
  - FOLD/UPGRADE `src/data_agents/professor/fact_backfill.py
    ::_retire_duplicate_active_facts` + `_fact_key` to the semantic key (the
    keep-richest writer subsumes the post-insert retire).
  - REFACTOR the four raw-INSERT paths to call the writer:
    `scripts/run_professor_llm_field_extract.py` (B),
    `scripts/run_unified_professor_crawl.py` (C),
    `scripts/run_professor_web_enrich.py` (D, `fact_type='homepage'` summary),
    `scripts/run_topic_split_backfill.py` (G, `research_topic`).
- **Storage**: no migration. `professor_fact` schema unchanged (no new unique
  constraint required — dedup is enforced in the writer, consistent with the
  existing spec's application-level-key stance; a unique constraint is
  discussed in design.md as an optional hardening, **not** part of this
  change's acceptance).
- **Evidence/provenance**: unchanged — kept facts retain their original
  `source_page_id`, `evidence_span`, `run_id`; a superseded twin keeps its
  provenance and only its `status` changes.
- **No public API / serialized-format change**; classification A–G,
  retrieval `_VALID_DOMAINS`, evidence shape all untouched.
- **Rollback**: pure ingest-behavior change; revert the code and re-run the
  one-shot dedup script (archived under
  `.agents/runs/professor-fact-within-format-dedup/`) to restore a clean
  state. No irreversible data migration.
