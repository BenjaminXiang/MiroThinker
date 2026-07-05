## ADDED Requirements

### Requirement: Paper snippet source chain SHALL cover full-text abstract

The paper snippet builder SHALL derive the generation snippet from a source
chain that includes `paper_full_text.abstract` as a fallback after
`summary_zh` and `abstract_clean`, and `title` as the final fallback. The chain
SHALL be, in order: `summary_zh` → `abstract_clean` → `paper_full_text.abstract`
→ `title`. A paper that is retrievable SHALL also be presentable: if a paper is
admitted to Milvus by the rich-text predicate, its snippet SHALL be non-empty
and sourced from `paper_full_text.abstract` (or `intro`, where the embedding
used `intro`). This removes the embedding-source ⊋ snippet-source asymmetry by
which a paper embedded off `paper_full_text.abstract` would otherwise yield an
empty snippet and be recalled-but-invisible to the answer.

#### Scenario: a partial paper with full text yields a non-empty snippet
- **GIVEN** a `partial` paper with `summary_zh` and `abstract_clean` NULL and
  `paper_full_text.abstract` non-empty
- **WHEN** its snippet is built for the title-exact path
- **THEN** the snippet equals `paper_full_text.abstract` (truncated as usual)
  and `snippet_source='paper_full_text_abstract'`

#### Scenario: a ready paper keeps its summary_zh snippet
- **GIVEN** a `ready` paper with non-empty `summary_zh`
- **WHEN** its snippet is built
- **THEN** the snippet equals `summary_zh` (the chain's first source wins)

#### Scenario: the title-exact SELECT joins paper_full_text
- **GIVEN** a paper matched by title-exact lookup that has no `summary_zh` and
  no `abstract_clean` but has `paper_full_text.abstract`
- **WHEN** the title-exact candidate is constructed
- **THEN** the SELECT has joined `paper_full_text` and the snippet is non-empty,
  so the candidate is not dropped as having no presentable text

### Requirement: Vector recall SHALL admit partial papers with collected rich text

The vector-recall quality filter SHALL admit a `paper` candidate whose
`quality_status='partial'` when `paper_has_rich_retrieval_text` is TRUE, in
addition to `ready` papers. A vector-recalled `partial` paper with rich text
SHALL NOT be dropped before rerank. A `partial` paper without rich text, and
any `needs_enrichment` paper, SHALL be dropped by the vector filter (they are
not indexable, so they cannot be vector-recalled in a correct system; this
requirement defends against stale Milvus state). The `paper_title_exact` path's
existing non-ready admission (snippet-bearing exact matches) is unchanged and
remains a separate, broader channel.

#### Scenario: a vector-recalled partial-with-rich-text paper passes the filter
- **GIVEN** a `partial` paper with `paper_full_text.abstract` non-empty that ANN
  recalls into the candidate window
- **WHEN** the vector-recall quality filter is applied
- **THEN** the candidate is retained for rerank (not dropped as non-ready)

#### Scenario: a vector-recalled title-only partial is dropped
- **GIVEN** a `partial` paper with no `paper_full_text` richness that appears in
  ANN results due to stale Milvus state
- **WHEN** the vector-recall quality filter is applied
- **THEN** the candidate is dropped (defensive; it is not indexable)

#### Scenario: a ready paper is unaffected
- **GIVEN** a `ready` paper vector-recalled into the candidate window
- **WHEN** the vector-recall quality filter is applied
- **THEN** the candidate is retained (unchanged behavior)
