# Acceptance: professor-fact-cross-format-dedup

A change is accepted only when ALL of the following hold.

## Spec contract

- [ ] `semantic_fact_key` produces identical keys for pipe / JSON / bilingual
      prose / CJK prose / gloss-prefix encodings of the same logical fact.
- [ ] `semantic_fact_key` keeps distinct keys for: different time periods at the
      same org; different fields at the same school; different roles/awards at
      the same venue.
- [ ] `semantic_fact_key` collapses degree synonyms (`Ph.D.` ≡ `Doctor of
      Engineering` ≡ `博士`) and bilingual flips / gloss prefixes.

## Writer contract

- [ ] Every professor_fact insert path routes through `_upsert_fact`; `grep -Rn
      "INSERT INTO professor_fact" apps/miroflow-agent` returns no active-row
      raw inserts (only the writer's parameterized INSERT inside `_upsert_fact`).
- [ ] Inserting the same education as pipe + JSON + bilingual in one run yields
      exactly **1** active row; the kept row is the richest (pipe-with-years if
      present).
- [ ] Keep-richest: a year-less JSON fact is superseded when a pipe-with-years
      twin arrives; a poorer prose twin is superseded by a structured twin.
- [ ] Re-running the writer on the same input is a no-op (idempotent — no new
      rows, no status flips).
- [ ] Two genuinely-distinct facts (different period/field/role) remain **2**
      active rows.

## Code quality / invariants

- [ ] No new schema migration; `professor_fact` columns unchanged.
- [ ] Evidence/provenance preserved on superseded rows (only `status`/`run_id`/
      `updated_at` change).
- [ ] No secrets logged; no public API / serialized-format change; A–G and
      `_VALID_DOMAINS` untouched.
- [ ] `uv run pytest` green; `just lint` clean.

## Operational parity (so a revert is recoverable)

- [ ] The repeatable no-LLM scan (task 4.1) reproduces this session's dedup on a
      known-dirty fixture (dry-run JSONL matches the archived
      `professor-fact-within-format-dedup` results within documented tolerance).

## Evidence to report

- Pytest output (unit + contract suites).
- `grep` proof that no raw active-row insert remains.
- A small before/after on a synthetic multi-format fixture showing 3 inputs → 1
  active row.
