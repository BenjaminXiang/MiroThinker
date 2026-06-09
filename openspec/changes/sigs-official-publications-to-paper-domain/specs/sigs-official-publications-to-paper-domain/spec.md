## ADDED Requirements

### Requirement: SIGS official publication entries are parsed as full paper candidates

The system MUST parse every official SIGS professor-page publication entry into a paper candidate whose `clean_title` is the paper title rather than an author list. Author-prefixed and numbered citation formats MUST preserve listed authors, venue text, year, source URL, and direct PDF URL when present.

The system MAY use LLM-assisted extraction for SIGS and other variable professor-page citation formats, but only after deterministic code locates the official publication section. LLM fallback MUST be available across institutions when rule parsing yields suspicious titles or low-recall citation sections, not only for one SIGS hostname. LLM output MUST be validated against source spans before any candidate enters the paper-domain bridge.

Source headings such as "Representative Publications" or `代表性论文` MUST be treated only as provenance labels. The system MUST NOT infer that these publications are the professor's representative works.

#### Scenario: Ahmed author-prefixed SIGS citation

- **GIVEN** Ahmed Elazab's SIGS official profile page contains `1- M. Abdelaziz, T. Wang, W. Anwaar, A. Elazab*. Robust attention transfer neural networks for diagnosis of Alzheimer's disease from structural magnetic resonance images, Engineering Applications of Artificial Intelligence, 164, 113260, 2026`
- **WHEN** homepage publication extraction runs for the page
- **THEN** the extracted publication has `clean_title` equal to `Robust attention transfer neural networks for diagnosis of Alzheimer's disease from structural magnetic resonance images`
- **AND** `authors_text` contains `M. Abdelaziz` and `A. Elazab`
- **AND** `venue_text` contains `Engineering Applications of Artificial Intelligence`
- **AND** `year` is `2026`

#### Scenario: Official list is not truncated

- **GIVEN** a SIGS official profile page lists more than five official publication entries under a publication section
- **WHEN** homepage publication extraction runs
- **THEN** every parseable official publication entry is returned
- **AND** no fixed per-professor paper count cap is applied by the extractor

#### Scenario: LLM extraction is source-grounded

- **GIVEN** a SIGS official publication section contains citation formats that vary across professors
- **WHEN** LLM-assisted publication extraction is enabled for the post-collection bridge
- **THEN** the LLM receives only the official publication-section text
- **AND** each accepted item has a `source_span` from the page text
- **AND** `title`, `authors_text`, `venue_text`, `year`, and identifiers are accepted only when grounded in that `source_span`
- **AND** invalid or hallucinated items are not sent to title resolution

#### Scenario: Cross-institution low-quality rule extraction uses the same fallback

- **GIVEN** a non-SIGS official professor page has a publication section whose rule-parsed candidates contain suspicious author-list titles or whose citation-rich section yields fewer than three parsed papers
- **WHEN** an LLM extractor is configured for homepage publication extraction
- **THEN** the system attempts the same source-grounded LLM fallback used for SIGS
- **AND** accepted items still require source-span grounding
- **AND** invalid or hallucinated items are dropped before paper-domain title resolution

### Requirement: SIGS official publications bridge to canonical paper domain

The system MUST bridge extracted official SIGS professor-page publications through the paper-domain ingest path after professor seed recollection. For each parseable listed publication, the bridge MUST attempt title resolution, upsert a canonical `paper` row, and create or update a verified `professor_paper_link` with `is_officially_listed=true`.

The bridge MUST NOT run external title resolution synchronously inside the professor seed recollection main loop.

The bridge MAY enable LLM-assisted publication extraction as a post-collection option. That option MUST not be part of the professor seed recollection main loop.

The bridge's title resolver MUST use a conservative multi-source title cascade. Official professor-page entries remain the relationship evidence, while external sources only resolve or enrich paper metadata. The resolver MUST try OpenAlex, Crossref, Semantic Scholar, DBLP, arXiv, and optional web search in order, skipping rate-limited or failing sources without blocking later sources. A result MUST NOT be accepted unless normalized title similarity and available year/author hints meet the resolver confidence threshold.

#### Scenario: Ahmed paper bridge writes verified links

- **GIVEN** Ahmed Elazab's SIGS official profile page has parseable official publication entries
- **WHEN** the post-collection homepage paper ingest bridge runs for Ahmed
- **THEN** each parseable official publication is eligible for `resolve_paper_by_title`
- **AND** each resulting paper is upserted into `paper`
- **AND** a `professor_paper_link` row is written with `link_status='verified'`
- **AND** the link has `is_officially_listed=true`
- **AND** the link records `prof_homepage_tier2` or `prof_homepage_tier3` according to the stored page role

#### Scenario: Malformed author-list title is blocked before resolver

- **GIVEN** publication parsing returns a candidate whose `clean_title` looks like an author list and lacks a real paper title
- **WHEN** the homepage paper ingest bridge processes the candidate
- **THEN** the bridge does not call external title resolution for that candidate
- **AND** it records a diagnostic pipeline issue for the malformed publication

#### Scenario: Title resolver cascades across multiple metadata sources

- **GIVEN** a clean official-page publication title is not confidently resolved by OpenAlex
- **WHEN** `resolve_paper_by_title` runs for the bridge
- **THEN** it attempts Crossref title search before Semantic Scholar, DBLP, arXiv, and optional web search
- **AND** it attempts Semantic Scholar before DBLP, arXiv, and optional web search when Crossref is missing or below threshold
- **AND** it attempts DBLP before arXiv and optional web search when Crossref and Semantic Scholar are missing or below threshold
- **AND** a rate-limited or failing source returns no candidates without blocking later sources
- **AND** author-list-like titles remain below the confidence threshold and are not accepted automatically

### Requirement: Enrichment and summary preserve source truth

The system MUST attempt paper metadata, abstract, summary, full-text, and paper Milvus refresh follow-up for SIGS officially linked papers using existing paper-domain scripts and services. If a resolver or full-text source provides an abstract, `abstract_clean` MAY be written and `summary_zh` MAY be generated. If no source provides an abstract, the system MUST NOT fabricate `abstract_clean`.

Page-only papers without abstracts MUST remain in an enrichment or review-needed quality state and MUST retain diagnostic evidence explaining the missing metadata.

#### Scenario: Resolver abstract supports summary generation

- **GIVEN** a SIGS officially linked paper has resolver metadata with `abstract_clean`
- **WHEN** paper summary backfill runs for the professor or paper
- **THEN** the paper gets a source-grounded `summary_zh`
- **AND** a targeted paper Milvus refresh can include the changed paper

#### Scenario: Page-only paper without abstract stays reviewable

- **GIVEN** a SIGS officially linked paper was created from page-only data and no resolver or full-text abstract is available
- **WHEN** summary and quality follow-up runs
- **THEN** `abstract_clean` remains empty
- **AND** the paper remains marked for enrichment or review
- **AND** a pipeline issue or equivalent diagnostic evidence records the unresolved metadata gap

### Requirement: Frontend display and retrieval quality are both acceptance gates

SIGS rollout acceptance MUST verify both user-visible display quality and backend retrieval quality. A complete-looking frontend page is not sufficient unless the refreshed professor and paper records are also indexed and retrievable through the paper/professor retrieval path used by chat and search.

#### Scenario: Frontend shows complete professor and paper records

- **GIVEN** a SIGS professor has official profile data and officially listed papers with abstracts or summaries
- **WHEN** the admin frontend opens the professor and paper detail pages
- **THEN** the professor page shows complete identity, affiliation, homepage, research/profile fields, and linked papers
- **AND** each sampled paper page shows title, authors, year or venue when available, English abstract when available, Chinese `summary_zh` when generated, quality status, and source metadata
- **AND** `summary_text` and `summary_zh` aliases do not render duplicate summary blocks

#### Scenario: Backend retrieval recalls refreshed professor and paper records

- **GIVEN** SIGS professor and paper Milvus refresh has run after homepage ingest and summary backfill
- **WHEN** retrieval or chat searches by professor name, paper title, research topic, and abstract keywords
- **THEN** the expected professor and officially linked papers appear in the top results with source traceability
- **AND** results prefer `ready` records but do not hide reviewable page-only records when the query is explicitly about that professor's official publications
- **AND** retrieval evidence includes query text, expected IDs, returned IDs/ranks, domain, and pass/fail reason

### Requirement: SIGS rollout evidence reports parse and enrichment outcomes

The system MUST report SIGS rollout statistics for Ahmed first, then a random SIGS sample, then the full SIGS set before claiming completion.

#### Scenario: Ahmed acceptance report

- **WHEN** the Ahmed single-professor bridge validation completes
- **THEN** the report includes official publication count, parsed count, canonical paper count, verified link count, resolver hit count, page-only count, abstract count, `summary_zh` count, full-text count, Milvus refresh count, and failure reasons

#### Scenario: Random SIGS sample report

- **WHEN** the random SIGS sample validation completes
- **THEN** the report includes per-professor official publication count, parsed count, ingested count, verified link count, abstract count, `summary_zh` count, and failure reasons
- **AND** the report includes frontend display checks and backend retrieval checks for the sampled professors and papers
