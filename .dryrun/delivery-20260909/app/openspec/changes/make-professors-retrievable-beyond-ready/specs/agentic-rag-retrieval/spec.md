## ADDED Requirements

### Requirement: Professor vector recall SHALL admit non-ready professors (decouple retrievability from publication-completeness)

The professor vector-recall quality filter SHALL admit a professor candidate whose
`quality_status` is `ready`, `needs_review`, or `needs_enrichment`. The filter SHALL exclude
only `low_confidence` professors (non-person-name / profile-blob / reader-artifact /
missing-official-source — not reliable entities) and `rejected`/`merged` (excluded upstream from
the index). `quality_status` SHALL be a ranking signal, not a retrieval gate: better-embedded
`ready` profiles are expected to rerank above `needs_review`/`needs_enrichment`. This decouples
retrievability (can the entity be found?) from publication-completeness (is the record polished?),
matching the fact that professor data is 94.5% official-sourced and professors are embedded
regardless of `ready`.

#### Scenario: a needs_review professor is admitted by the vector filter
- **GIVEN** a professor with `quality_status='needs_review'`, resolved identity, embedded in
  `professor_research_profiles`
- **WHEN** it is vector-recalled into the candidate window and the quality filter is applied
- **THEN** the candidate is retained for rerank (not dropped as non-ready)

#### Scenario: a needs_enrichment professor is admitted by the vector filter
- **GIVEN** a professor with `quality_status='needs_enrichment'` (e.g. missing a derived field)
  but a resolved identity and canonical name
- **WHEN** it is vector-recalled and the quality filter is applied
- **THEN** the candidate is retained for rerank

#### Scenario: a low_confidence professor is excluded
- **GIVEN** a professor with `quality_status='low_confidence'` (e.g. non-person-name,
  profile-blob, or reader-artifact)
- **WHEN** it is vector-recalled and the quality filter is applied
- **THEN** the candidate is dropped (not a reliable entity)

#### Scenario: a ready professor is unaffected and ranks first
- **GIVEN** a `ready` professor and a `needs_review` professor both vector-recalled
- **WHEN** the quality filter + rerank are applied
- **THEN** both are retained; the `ready` professor is not demoted below `needs_review` by the
  filter (ranking may still order by relevance)
