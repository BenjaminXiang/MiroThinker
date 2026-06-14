## ADDED Requirements

### Requirement: Professor core paper chain uses official profile seeds

The system MUST treat university roster pages and official Professor profile
pages as the discovery source for Professor core identity and Professor-linked
papers. External literature providers MUST enrich papers already discovered
from official Professor pages, and MUST NOT discover the offline Professor paper
list by querying external providers with only a professor name.

#### Scenario: Full seed run discovers papers from official pages

- **WHEN** a full Professor seed run succeeds for a university roster
- **THEN** the Professor rows are written from the roster/profile chain
- **AND** Professor-linked paper candidates are derived from the official
  profile, official homepage, lab homepage, CV, or publication subpages owned by
  that profile
- **AND** external providers are used only to fill identifiers, abstracts,
  summaries, PDFs, venues, authors, or citation metadata for those candidates

#### Scenario: External provider search is not a discovery source

- **WHEN** the pipeline needs papers for a Professor that has no extractable
  publication titles on official Professor-owned pages
- **THEN** the offline pipeline MUST NOT create a paper list only from OpenAlex,
  Crossref, Semantic Scholar, DBLP, arXiv, or Web Search author-name results
- **AND** the Professor paper chain records a visible issue or no-paper state
  instead of inventing discovered papers

#### Scenario: Sample seed run cannot promote final readiness

- **WHEN** a Professor seed run is executed with a sample or row limit
- **THEN** the run may write preview or diagnostic data
- **AND** it MUST NOT promote affected Professor rows to final `ready` through
  the core profile-paper quality closure

### Requirement: Chinese research overview is durable and source-grounded

The system MUST persist a Chinese research overview for a Professor when the
official profile contains a research overview, research interests paragraph, or
equivalent section in Chinese or English. If the official section is English,
the system MAY use an LLM translation step, but the persisted Chinese overview
MUST remain traceable to the official source page and source text or source
hash.

#### Scenario: English official overview is translated for Ahmed Elazab

- **WHEN** Ahmed Elazab's official profile contains the English research
  overview beginning with "My research focuses on developing trustworthy
  artificial intelligence for medical image analysis"
- **THEN** the Professor detail payload exposes a Chinese research overview
- **AND** the stored overview is linked to the official source page and the
  source English text or source hash
- **AND** the profile is not considered `ready` if the Chinese overview is
  missing while the English source overview is present

#### Scenario: Stored overview takes precedence over raw extraction

- **WHEN** a Professor has a persisted Chinese research overview section
- **THEN** the Admin Professor detail API returns that persisted section
- **AND** raw `profile_raw_text` section extraction is used only as a fallback
  or diagnostic path

### Requirement: Professor ready status reflects user-facing profile quality

The system MUST NOT mark a Professor as `ready` unless the user-facing core
profile fields satisfy the quality contract. The contract MUST include current
official identity, current affiliation, a Chinese `profile_summary` of 200-300
characters, a durable Chinese research overview when source material exists,
and no open critical issue in the Professor core profile-paper chain.

#### Scenario: Short Professor summary blocks ready status

- **WHEN** a Professor has a `profile_summary` shorter than 200 Chinese
  characters
- **THEN** the Professor quality evaluation returns `needs_review` or
  `needs_enrichment`
- **AND** the Professor is not marked `ready`

#### Scenario: Repetitive term-list summary blocks ready status

- **WHEN** a Professor summary mostly repeats research-topic labels and does not
  cover identity, research direction, representative output, or background
- **THEN** the quality evaluation records a shallow or repetitive summary reason
- **AND** the Professor is not marked `ready`

#### Scenario: Ding Wenbo profile has complete core fields

- **WHEN** the system answers or displays "介绍清华的丁文伯"
- **THEN** the local Professor data includes identity, email or homepage when
  available, education facts, work-experience facts, research directions,
  academic positions, honors or awards, and a non-repetitive Chinese summary
- **AND** missing Professor-company startup roles do not block Professor core
  readiness

### Requirement: Professor paper links are deduplicated before summaries and display

The system MUST deduplicate verified Professor paper links before generating
Professor output summaries, returning Admin detail paper lists, refreshing
retrieval indexes, or generating chat answers. Deduplication MUST prefer richer
canonical paper rows over page-only rows while preserving official page
evidence and old-to-new merge traceability.

#### Scenario: Ahmed Alzheimer paper resolves to one displayed paper

- **WHEN** Ahmed Elazab has both a Crossref DOI row and a prof-page-only row for
  "Improved Alzheimer's disease diagnosis using multimodal sparse similarity
  feature selection and auxiliary data"
- **THEN** the Professor detail paper list displays one canonical paper for that
  title/year
- **AND** the official Professor-page evidence remains attached to the chosen
  canonical paper link
- **AND** the superseded page-only paper id has a durable merge target mapping

#### Scenario: Duplicate verified links block Professor ready status

- **WHEN** a Professor has two active verified links with the same normalized
  paper title and year after canonical merge should have run
- **THEN** the Professor core quality closure records a duplicate-paper issue
- **AND** the Professor is not promoted to `ready`

### Requirement: Paper enrichment supports detail links and external PDF links

The system MUST enrich homepage-derived papers with external identifiers,
abstracts, Chinese summaries, and PDF links when those data can be resolved
without violating the official-page discovery rule. Paper detail pages and chat
answers MUST expose the local paper detail route for each displayed paper.

#### Scenario: pFedGPA resolves to arXiv PDF when available

- **WHEN** the homepage-derived paper title is "pFedGPA: Diffusion-based
  Generative Parameter Aggregation for Personalized Federated Learning"
- **THEN** title enrichment attempts to resolve its arXiv record
- **AND** the paper detail data includes the arXiv identifier or PDF URL when
  the provider returns `2409.05701`
- **AND** the paper can be reached through `/paper/<paper_id>`

#### Scenario: Professor workbench paper title links to paper detail

- **WHEN** the Admin Professor workbench renders a paper row with
  `paper_id="PAPER-EXAMPLE"`
- **THEN** the paper title is rendered as a navigable link to
  `/paper/PAPER-EXAMPLE`

#### Scenario: Chat citation uses the same paper page route

- **WHEN** a chat answer cites a local paper with id `PAPER-EXAMPLE`
- **THEN** the citation URL uses the configured admin/frontend base URL plus
  `/paper/PAPER-EXAMPLE`
- **AND** it does not use an obsolete browse hash route for that paper

### Requirement: Full seed closure chains profile and paper quality stages

After a successful full Professor seed run, the system MUST run or schedule a
seed-scoped quality closure that connects homepage paper ingest, title
enrichment and merge, paper enrichment and promotion, Professor output summary
generation, Professor quality re-evaluation, and retrieval/index refresh
selection. The closure MUST be idempotent and MUST record visible issues for
failed stages.

#### Scenario: Successful full seed produces closure evidence

- **WHEN** a full Professor seed run succeeds without a row limit
- **THEN** the system runs or schedules the core profile-paper quality closure
- **AND** the closure records stage counts for homepage papers, title merges,
  paper summaries, Professor output summaries, quality re-evaluation, and index
  refresh selection

#### Scenario: Closure failure is visible and blocks ready promotion

- **WHEN** one closure stage fails for a Professor
- **THEN** the failure is recorded as a pipeline issue or equivalent run
  evidence with professor id, seed id, stage, and reason
- **AND** the affected Professor is not promoted to `ready` by this closure

### Requirement: Runtime cross-domain association is separate from Professor core readiness

The system MUST keep Professor core readiness independent from company/news
association completeness. Runtime multi-source recall MAY combine Professor,
Company, News, Paper, and Patent data to answer cross-domain questions, but the
Professor crawler MUST NOT be required to collect private or non-disclosed
company roles from Professor pages.

#### Scenario: Ding Wenbo company association can be answered by other domains

- **WHEN** a user asks whether Ding Wenbo participated in founding any company
- **THEN** the runtime answer MAY use Company-domain records, news evidence, or
  other public cross-domain evidence to associate Ding Wenbo with a company
- **AND** absence of that company role from Professor profile data does not make
  Ding Wenbo's Professor core profile incomplete
