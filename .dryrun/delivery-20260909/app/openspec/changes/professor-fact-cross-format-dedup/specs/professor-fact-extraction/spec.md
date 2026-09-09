## MODIFIED Requirements

### Requirement: Backfill is idempotent and failure-isolated

The backfill runner MUST avoid duplicating active facts on repeated
runs. A failure for one professor MUST be logged and counted without
aborting the full batch.

Duplicate detection MUST use the application-level active-fact key:

```text
professor_id + fact_type + semantic_fact_key
```

`semantic_fact_key` MUST be a **format-normalizing** key that compares the
*logical* fact independent of its surface encoding. It MUST produce the same
key for the same fact written as pipe (`school | degree | field | years`),
JSON (`{"school","degree","field"}` / `{"organization","role"}`), bilingual
prose (`English (中文)` / `中文 (English)`), CJK prose, and gloss-prefixed
prose (`X` vs `X (English gloss)`). A literal whitespace-collapsed,
case-folded `value_raw`/`value_normalized` string is NOT sufficient and MUST
NOT be used as the key. `source_page_id` and `evidence_span` MUST NOT be part
of the key; they are provenance fields.

If the same fact is seen again with different provenance, the richer
representation MUST be kept and the poorer one MUST be superseded — the
existing active fact is updated or the poorer twin is retired rather than a
second active row being created.

#### Scenario: Re-running does not duplicate facts

- **GIVEN** a backfill has already written an education fact for a professor
- **WHEN** the same profile text is processed again
- **THEN** no duplicate active education fact is created

#### Scenario: Same fact in a different surface format does not duplicate

- **GIVEN** an active `education` fact exists for a professor as the pipe
  value `Tsinghua University | Ph.D. | Computer Science | 2010-2015`
- **WHEN** the extractor later writes the same degree as JSON
  `{"school":"Tsinghua University","degree":"Ph.D.","field":"Computer Science"}`
- **THEN** no second active education fact is created
- **AND** the richer representation (the one carrying the year range) is the
  one kept active

#### Scenario: Bilingual flip does not duplicate

- **GIVEN** an active `education` fact exists as
  `Tsinghua University (清华大学) | Ph.D. (博士) | CS`
- **WHEN** the same fact is later written as
  `清华大学 (Tsinghua University) | 博士 (Ph.D.) | CS`
- **THEN** exactly one active education fact remains for that logical degree

## ADDED Requirements

### Requirement: Universal dedup-aware writer for professor_fact

Every code path that writes an active `professor_fact` row MUST route through
a single dedup-aware writer that consults `semantic_fact_key` and applies the
keep-richest rule. No path MAY issue a raw `INSERT INTO professor_fact … ON
CONFLICT` to create an active row, because `professor_fact` has no unique
constraint on `(professor_id, fact_type, value*)` and such a statement always
inserts.

The writer MUST, for each candidate fact:

1. compute `semantic_fact_key` for the candidate;
2. scan active rows for `(professor_id, fact_type)` and compute each one's
   semantic key;
3. if no active row shares the candidate's semantic key → insert the candidate;
4. if an active row shares the semantic key → keep the richer representation
   (completeness score: structured-with-more-populated-fields > structured
   with fewer > prose; pipe-with-year-range >= JSON-without-years; ties broken
   by `value_raw` length) and supersede the other.

This applies to all current and future insert paths, including the homepage
rule writer (pipe), the LLM field extractors (JSON and bilingual prose), the
profile-summary writer (`fact_type='homepage'`), and the topic-split writer
(`research_topic`).

#### Scenario: A raw-INSERT path becomes non-duplicating

- **GIVEN** a professor already has an active `education` fact from the
  homepage rule path (pipe format) and an LLM field-extraction run is about
  to write the same degree as JSON
- **WHEN** the LLM extraction run writes via the universal writer
- **THEN** the writer finds the semantic-key match
- **AND** keeps the richer row active and supersedes the other
- **AND** no second active `education` row is created

#### Scenario: Keep-richest upgrades a poorer representation

- **GIVEN** an active `work_experience` fact exists as JSON without years
  `{"organization":"Tsinghua","role":"Postdoc"}` and a later run writes the
  same role as pipe `Tsinghua | Postdoc | 2017-2020`
- **WHEN** the writer processes the pipe candidate
- **THEN** the pipe row (richer: carries the year range) becomes the single
  active fact
- **AND** the year-less JSON row is superseded

### Requirement: Semantic key correctness (false-positive guards)

`semantic_fact_key` MUST collapse only facts that are truly the same logical
entry. It MUST satisfy, at minimum:

- **Distinct period retained**: two facts at the same organization with
  *different* time periods (e.g. `2018-2019` and `2019-2020`) MUST produce
  different keys. Years are extracted from the whole value, not only a single
  delimited field, so a range (`2016-2020`) and a completion year (`2020`)
  that are part of the same entry are reconciled only by the rule the writer
  defines; two genuinely different periods are never collapsed.
- **Distinct field retained**: two degrees at the same school with different
  fields (e.g. Bachelor in Economics vs Bachelor in Environmental
  Engineering) MUST produce different keys.
- **Distinct role/org retained** for freeform types (`award`,
  `academic_position`): two different awards or two different editorial roles
  at the same venue MUST produce different keys.
- **Degree synonyms reconciled**: `Ph.D.` ≡ `Doctor of Engineering` ≡ `博士`
  at the same school/field/period MUST produce the same key.
- **Gloss prefix collapsed**: `X` and `X (English gloss)` / `X (中文释义)`
  MUST produce the same key.
- **Order-independent org tokens collapsed** for JSON/structured values:
  `Tsinghua University (清华大学)` and `清华大学 (Tsinghua University)` MUST
  produce the same key.

#### Scenario: Two periods at the same school stay separate

- **GIVEN** a professor has a Master `2013-2016` and a PhD `2016-2020`, both
  at Peking University, both in Chemistry
- **WHEN** the writer processes both (in any format)
- **THEN** two active `education` facts remain, one per period

#### Scenario: Two fields at the same school stay separate

- **GIVEN** a professor has a Bachelor in Economics and a Bachelor in
  Environmental Engineering, both at Tsinghua, both `2008-2012`
- **WHEN** the writer processes both
- **THEN** two active `education` facts remain, one per field

#### Scenario: Degree synonyms collapse

- **GIVEN** a professor has a fact `Tsinghua | Doctor of Engineering | Env Eng`
  and another `Tsinghua | Ph.D. in Engineering | Env Eng` (same period)
- **WHEN** the writer processes both
- **THEN** exactly one active `education` fact remains (the richer kept)
