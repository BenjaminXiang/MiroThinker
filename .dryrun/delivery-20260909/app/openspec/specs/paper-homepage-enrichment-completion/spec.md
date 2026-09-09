# paper-homepage-enrichment-completion Specification

## Purpose
TBD - created by archiving change paper-homepage-enrichment-completion. Update Purpose after archive.
## Requirements
### Requirement: Page paper evidence preserves professor-page tier

The paper ingest path MUST record whether a page-declared paper came
from a Tier 2 official profile page or a Tier 3 personal/lab homepage.
The emitted evidence source MUST be `prof_homepage_tier2` or
`prof_homepage_tier3`.

#### Scenario: Tier 2 paper evidence

- **GIVEN** a publication is extracted from a professor official profile
  page classified as Tier 2
- **WHEN** the paper row and link are written
- **THEN** the page evidence source is `prof_homepage_tier2`

#### Scenario: Missing tier is diagnostic

- **GIVEN** a publication is extracted from a page with no tier
  classification
- **WHEN** ingest cannot derive the tier
- **THEN** the system writes a `pipeline_issue`
- **AND** it does not silently emit a generic page-only source value

### Requirement: Paper enrichment uses four-source fallback

The enrichment path MUST merge metadata for already-discovered paper
rows in this priority order: OpenAlex, Crossref, Semantic Scholar,
arXiv. Lower-priority sources MAY fill missing fields but MUST NOT
overwrite stronger source evidence. `citation_count` MUST remain
OpenAlex-only.

Author metadata MUST be mergeable. ORCID-bearing author identities from
a trusted source MUST be preserved when later sources provide only
plain display names.

#### Scenario: arXiv fills missing abstract

- **GIVEN** OpenAlex, Crossref, and Semantic Scholar return no abstract
- **AND** arXiv returns an abstract for the same paper identifier
- **WHEN** enrichment runs
- **THEN** the paper abstract is filled from arXiv
- **AND** the enrichment source list includes `arxiv`

### Requirement: Identifier contradictions block ready promotion

The enrichment path MUST detect conflicting DOI or arXiv identifiers
across sources for the same paper candidate. A contradiction MUST create
an open `pipeline_issue` using an existing stage value and MUST prevent
automatic promotion to `ready` while unresolved.

#### Scenario: DOI contradiction

- **GIVEN** a page-declared paper has canonical DOI `10.1/a`
- **AND** an enrichment source claims DOI `10.1/b` for the same matched
  title
- **WHEN** enrichment runs
- **THEN** a pipeline issue is written
- **AND** the paper is not promoted to `ready`

### Requirement: Summary changes trigger paper vector refresh

When `summary_zh` is inserted or materially changed, the system MUST
make the affected paper discoverable by a targeted Milvus refresh path.
The refresh path MUST support a bounded re-embed of affected paper
chunks without requiring a full Milvus rebuild.

#### Scenario: Summary backfill selects paper for re-embed

- **GIVEN** a paper has existing chunks in Milvus
- **WHEN** `summary_zh` changes
- **THEN** a targeted Milvus refresh run can select that paper
- **AND** the refreshed chunk text includes the new summary content

