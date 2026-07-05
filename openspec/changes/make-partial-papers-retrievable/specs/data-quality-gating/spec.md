## MODIFIED Requirements

### Requirement: Retrieval-readiness invariant and rebackfill coupling

The set of rows indexable by Milvus SHALL equal the set of rows the write-time
gate promotes to `ready`, **OR** the set of `paper` rows whose
`quality_status='partial'` AND that carry collected rich retrieval text
(`paper_full_text.abstract` non-empty OR `paper_full_text.intro` non-empty),
subject only to the per-domain identity/merge exclusions. The Milvus
indexability filters (`_is_indexable_*`) are the retrieval-readiness consumer
and SHALL key on `quality_status` (and, for paper, `identity_status`) plus, for
`paper` rows at `quality_status='partial'`, the rich-text predicate. A
write-path transition of a row into or out of an indexable state SHALL be
followed by a Milvus rebackfill so the transition is reflected in retrieval.
No second, **persisted** readiness signal SHALL exist; the rich-text predicate
SHALL be derived from `paper_full_text` at evaluation time, not stored as an
independent column. `professor`, `company`, and `patent` SHALL remain indexable
iff `quality_status='ready'` (modulo identity/merge exclusions) — the
partial-rich-text relaxation applies to `paper` only.

#### Scenario: A newly-ready paper becomes retrievable after rebackfill
- **GIVEN** a paper previously stuck below `ready` that the write-path gate now
  promotes to `ready`
- **WHEN** a Milvus rebackfill runs
- **THEN** the paper is present in `paper_chunks` and retrievable via the
  retrieval service

#### Scenario: A partial paper with collected full text becomes retrievable
- **GIVEN** a paper with `quality_status='partial'`, `identity_status` not in
  `{rejected, merged}`, and `paper_full_text.abstract` non-empty (or
  `paper_full_text.intro` non-empty), while `summary_zh` and `abstract_clean`
  are NULL
- **WHEN** a Milvus rebackfill runs
- **THEN** the paper is present in `paper_chunks` (with `abstract`/`intro`
  chunks) and retrievable via vector recall

#### Scenario: A title-only partial paper is NOT retrievable
- **GIVEN** a paper with `quality_status='partial'`, no `paper_full_text`
  row (or both `abstract` and `intro` empty), and `summary_zh`/`abstract_clean`
  NULL
- **WHEN** a Milvus rebackfill runs
- **THEN** the paper is NOT present in `paper_chunks` (the backfill SHALL
  delete any prior chunks for it)

#### Scenario: No second persisted readiness signal
- **GIVEN** two paper rows with identical `quality_status='partial'`,
  `identity_status`, and `paper_full_text` richness
- **WHEN** Milvus indexability is evaluated
- **THEN** both receive the same verdict, and no persisted `indexed`/`retrievable`
  boolean column disagrees with the derived verdict

#### Scenario: Professor/company/patent unaffected by the partial relaxation
- **GIVEN** a professor (or company, or patent) row with
  `quality_status='partial'`
- **WHEN** Milvus indexability is evaluated
- **THEN** it is NOT indexable (the partial-rich-text relaxation is paper-only)

## ADDED Requirements

### Requirement: Partial-paper rich-text retrievability predicate

The system SHALL define a single derived predicate
`paper_has_rich_retrieval_text(paper_id)` that returns TRUE iff the paper has a
`paper_full_text` row with non-empty `abstract` OR non-empty `intro`. This
predicate SHALL be the sole basis for admitting a `partial` paper into Milvus
indexability and into the vector-recall quality filter. The predicate SHALL NOT
be persisted as a column; it SHALL be computed from `paper_full_text` at
backfill and at retrieval-filter time. A `partial` paper for which the predicate
is FALSE (title-only) SHALL be treated as non-indexable and non-admissible by
the vector filter, identical to `needs_enrichment`.

#### Scenario: Predicate true on full-text abstract
- **GIVEN** a `partial` paper with `paper_full_text.abstract = '...'` non-empty
- **WHEN** `paper_has_rich_retrieval_text` is evaluated
- **THEN** it returns TRUE

#### Scenario: Predicate false when only a title is present
- **GIVEN** a `partial` paper with no `paper_full_text` row
- **WHEN** `paper_has_rich_retrieval_text` is evaluated
- **THEN** it returns FALSE, and the paper is not indexable

#### Scenario: Predicate false for a ready paper is irrelevant
- **GIVEN** a `ready` paper with no `paper_full_text` row
- **WHEN** indexability is evaluated
- **THEN** the paper is indexable by virtue of `quality_status='ready'`; the
  rich-text predicate is not consulted for `ready` rows
