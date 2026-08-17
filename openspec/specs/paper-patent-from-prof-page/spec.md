# paper-patent-from-prof-page Specification

## Purpose
TBD - created by archiving change prof-paper-patent-from-page-flow. Update Purpose after archive.
## Requirements
### Requirement: Publications-section extraction from prof Tier 2/3 pages

The pipeline MUST extract paper candidates only by parsing the
Publications section of a professor's school-official homepage (Tier
2) or personally-maintained homepage / lab homepage (Tier 3). External
literature databases MUST NOT be used as discovery sources for the
periodic offline pipeline.

The extractor MUST:

- Reuse `apps/miroflow-agent/src/data_agents/professor/homepage_publications.py`
  for HTML-to-paper-entry parsing.
- Capture the minimum set per Paper Review §3.1 P4: `title`, `year`,
  `venue`, `authors` (where `authors` may be inferred as
  `<professor_name> et al.` if the page lists only the page-owner).
- Record `evidence.source_type = "prof_homepage_tier2"` or
  `"prof_homepage_tier3"` with `evidence.source_url` set to the
  specific subpage where the entry was found.
- Treat missing abstract / DOI / arxiv_id / venue as expected (preprint
  / accepted-not-published case is first-class per P4).

#### Scenario: Preprint listed on professor page

- **GIVEN** a prof Tier 2 page lists "Smith, J. et al., 'Foo Bar', 2026"
  with no DOI, no abstract, and no arxiv_id
- **WHEN** the extractor runs
- **THEN** a `PaperRecord` candidate is produced with `title="Foo Bar"`,
  `year=2026`, `authors=["Smith, J. et al."]`, `venue=None`, no DOI,
  no abstract
- **AND** `evidence.source_type = "prof_homepage_tier2"`
- **AND** `quality_status = "needs_enrichment"` (downgraded; awaits
  enrichment to potentially promote to `ready`)

#### Scenario: External DB as discovery source is forbidden

- **GIVEN** the pipeline is computing candidate papers for
  `professor_id="PROF-X"`
- **WHEN** the discovery step runs
- **THEN** the system MUST NOT call OpenAlex / Crossref / Semantic
  Scholar / arXiv / DBLP / Web Search for the purpose of returning a
  paper list keyed by author name
- **AND** the only source for the candidate list is the parsed
  Publications section of the professor's Tier 2 / Tier 3 pages

### Requirement: Patents-section extraction from prof Tier 2/3 pages

The pipeline MUST extract patent candidates by parsing the Patents
section (variants: 专利 / Patents / Patent Applications / 发明专利) of
a professor's Tier 2 / Tier 3 pages, when such a section exists.

The extractor MUST:

- Use a conservative section-header match: only match sections whose
  heading contains one of `专利 / Patents / Patent Applications /
  发明专利 / 实用新型 / 外观`.
- Capture per-entry: `title` (required), `patent_id` (optional),
  `application_date` or `grant_date` (optional), `inventors`
  (optional; may be inferred as `[<professor_name>, ...]`).
- Record `evidence.source_type = "prof_homepage_tier2"` or
  `"prof_homepage_tier3"`.
- Be tolerant of zero-result extraction: most prof pages do not list
  patents, and that is normal.

#### Scenario: Page has no Patents section

- **GIVEN** a prof Tier 2 page contains Publications but no Patents
  section
- **WHEN** the extractor runs
- **THEN** zero patent candidates are produced
- **AND** no `pipeline_issue` row is written (absence is normal)

#### Scenario: Page has Patents section with only title

- **GIVEN** a prof Tier 2 page lists "一种基于 X 的 Y 方法 (专利申请号 待审)"
  in a section titled `专利`
- **WHEN** the extractor runs
- **THEN** a `PatentRecord` candidate is produced with `title="一种基于 X 的 Y 方法"`,
  `patent_id=None`, `application_date=None`, `inventors=[<prof_name>]`
- **AND** `evidence.source_type = "prof_homepage_tier2"`
- **AND** `quality_status = "needs_enrichment"`

### Requirement: Paper canonical upsert with 3-level dedup

When the extractor produces a paper candidate, the pipeline MUST match
it against the existing `paper` canonical using the following priority
chain (per Paper Review §3.1 P11):

1. **DOI match** (when both candidate and any existing row have DOI):
   exact lowercased DOI string match.
2. **Arxiv ID match** (when DOI absent on either side): exact
   lowercased Arxiv ID.
3. **Title-fuzzy + author-Jaccard fallback** (when neither DOI nor
   Arxiv ID present): title similarity ≥ 0.85 (token-set ratio) AND
   author-list Jaccard ≥ 0.5.

On match: update existing row's fields where the new evidence is
strictly better (e.g. fill missing abstract; do not overwrite existing
DOI from prof-page-only data). On no match: insert new row with
`quality_status` per the rules below.

#### Scenario: DOI match upsert

- **GIVEN** an existing `paper` row with `doi="10.1234/abc"` and
  `summary_zh=NULL`
- **AND** the extractor produces a candidate matching by DOI with a
  non-null abstract
- **WHEN** upsert runs
- **THEN** the existing row is updated: `abstract` filled (if was
  NULL), `last_updated` bumped
- **AND** existing `summary_zh` remains NULL until enrichment runs
  (separate Requirement)

#### Scenario: Title-fuzzy fallback merge

- **GIVEN** an existing `paper` row with `title="Foo Bar Baz"`,
  `year=2026`, `authors=["Smith, J.", "Lee, K."]`, no DOI
- **AND** the extractor produces a candidate with `title="Foo Bar Baz."`
  (period suffix), `year=2026`, `authors=["J. Smith", "K. Lee"]`,
  no DOI
- **WHEN** upsert runs
- **THEN** title token-set ratio ≥ 0.85 AND author Jaccard ≥ 0.5 →
  match accepted
- **AND** the existing row is updated, no duplicate row inserted

#### Scenario: Multi-source preprint version merge is NOT done in MVP

- **GIVEN** a paper exists in canonical with `arxiv_id="2305.12345v1"`
- **AND** the extractor produces a candidate with `arxiv_id="2305.12345v2"`
- **WHEN** upsert runs
- **THEN** these are treated as DIFFERENT papers (no version-stripping
  merge in MVP) — Phase B may add `arxiv_id` version-normalization

### Requirement: Patent canonical upsert with patent_id hard match

The pipeline MUST upsert patent candidates to canonical via
`patent_id` hard match when the candidate has a `patent_id`, and via
plain INSERT when the candidate has no `patent_id`. Specifically:

- **If the candidate has `patent_id`**: match by exact `patent_id`
  string (uppercased + whitespace-stripped) against existing `patent`
  rows. Match → update; no match → insert.
- **If the candidate has NO `patent_id`**: insert as a new row. The
  pipeline MUST NOT attempt fuzzy title-based merging in MVP. (When
  xlsx import later brings in the same patent with a `patent_id`, the
  canonical will gain a `patent_id`-bearing row but the prof-page row
  will remain — orphan-resolution is Phase B per Paper Review §3.3 C5.)

#### Scenario: patent_id hard-match upsert

- **GIVEN** an existing `patent` row with `patent_id="CN202310012345.6"`
- **AND** the extractor produces a candidate with the same `patent_id`
  but a different `title` field (formatting variant)
- **WHEN** upsert runs
- **THEN** existing row is updated; `title` is preserved (existing
  authoritative form; new title goes to `evidence.snippet` for
  audit) and `last_updated` bumped

#### Scenario: prof-page patent without patent_id

- **GIVEN** the extractor produces a candidate with `title="一种 X 方法"`,
  no `patent_id`
- **AND** the existing canonical contains no patent with this title
- **WHEN** upsert runs
- **THEN** a new `patent` row is inserted with `patent_id=NULL`,
  `quality_status="needs_enrichment"`, `evidence.source_type="prof_homepage_tier2"`

### Requirement: Identity gate semantics (paper + patent)

`professor.paper_identity_gate` and `professor.patent_identity_gate` MUST verify
**same-person vs same-name only**. They MUST NOT verify content truth
(whether the paper / patent actually exists in the world or contains
truthful claims).

The gate MUST:

- Return confidence ≥ 0.8 → automatic acceptance: link to
  `professor_paper_link` / `professor_patent_link`.
- Return confidence ∈ [0.5, 0.8) → defer to LLM judge with the prof's
  context (institution + research_directions + ORCID if available);
  LLM returns yes/no.
- Return confidence < 0.5 → reject; write `pipeline_issue` with
  `stage="identity_gate"`.

The gate input is always the page-side claim (the page lists this
paper/patent for this prof) plus optional enrichment-side authorship
information (e.g. OpenAlex co-authors). When discovery is purely from
the prof's own page (no external claim available), the gate accepts
unconditionally with confidence 1.0 — page declaration alone is
sufficient (per Paper Review §3.1 P9).

#### Scenario: Page-only attribution → unconditional acceptance

- **GIVEN** a paper candidate sourced solely from `prof_id=PROF-X`'s
  Tier 2 page
- **AND** no enrichment data is available yet
- **WHEN** the gate evaluates
- **THEN** confidence = 1.0 → automatic acceptance
- **AND** `professor_paper_link` row is inserted with
  `confidence=1.0` and `match_reason="prof_page_declaration"`

#### Scenario: OpenAlex enrichment reveals same-name conflict

- **GIVEN** a paper candidate from prof's page is matched to an
  existing canonical row with `doi="10.1234/abc"`
- **AND** OpenAlex enrichment returns 3 authors: "Smith, John A." (UCB),
  "Smith, John B." (Stanford), "Smith, J." (the prof's institution)
- **WHEN** the gate re-evaluates after enrichment
- **THEN** the gate finds 1-of-3 author match by institution → returns
  confidence ≥ 0.8 → keeps the existing
  `professor_paper_link` (no demotion or removal)

### Requirement: Async enrichment workflow (paper only)

After paper discovery + canonical upsert, the pipeline MUST attempt
enrichment from external sources, applying the field-level fallback
priority per Paper Review §3.1 P10:

- `abstract`: OpenAlex → Crossref → Semantic Scholar → arXiv (first
  available wins)
- `citation_count`: OpenAlex (canonical source; do not call others)
- `venue` / `year`: OpenAlex `publication_date` / `host_venue.name`
- `authors`: OpenAlex authors list, ORCID-bearing entries preferred
- `doi` / `arxiv_id`: cross-checked across all sources; mismatches →
  `pipeline_issue` row with `stage="paper_attribution"`

Enrichment MUST:

- Be **fire-and-forget**: a seed-run's `last_run_status` flips to
  `success` when discovery + initial upsert completes, regardless of
  enrichment status. Enrichment proceeds asynchronously in the
  background.
- Be **rate-limited**: respect each source's published rate budget
  (OpenAlex: 10 RPS polite pool; Crossref: 50 RPS unauth; S2: 1 RPS
  unauth; arXiv: 1 RPS).
- Honor an **enrichment kill-switch**: a Hydra config knob
  `paper.enrichment_disabled = false` allows ops to disable enrichment
  globally during incidents (default `false`).

Enrichment MUST NOT:

- Be used to **discover** new papers not present on prof pages.
- Promote `quality_status` from `rejected` (LLM-judged unwanted
  content) back to `ready`.

#### Scenario: Enrichment fills missing abstract

- **GIVEN** a paper canonical row from prof-page discovery with `doi`
  set, `abstract=NULL`, `quality_status="needs_enrichment"`
- **WHEN** OpenAlex enrichment finds the same DOI and returns abstract
- **THEN** `abstract` is updated; `enrichment_sources` array gains
  `"openalex"`
- **AND** if `summary_zh` generation succeeds afterwards,
  `quality_status` may promote to `ready` (separate Requirement)

#### Scenario: Patent never enriched externally

- **GIVEN** a patent canonical row from prof-page discovery
- **WHEN** the post-discovery enrichment step runs
- **THEN** the system MUST NOT call any external patent API or web
  search
- **AND** the patent row remains in `quality_status=needs_enrichment`
  unless and until xlsx import or another prof-page sighting brings
  additional fields

### Requirement: summary_zh generation (Chinese paragraph)

The pipeline MUST generate `paper.summary_zh` as a **Chinese paragraph
200-400 characters**, optionally containing internal four-段 markers
(per Paper Review §3.1 P2). The generation runs whenever a paper
canonical row has `abstract` available (either from prof-page
extraction or from enrichment).

The generator MUST:

- Use the existing `apps/miroflow-agent/src/data_agents/paper/abstract_translator.py`
  (140 lines).
- Produce paragraph form, NOT JSON object form.
- Pass through a boilerplate-detection LLM judge: outputs that are
  generic phrases without specific information are marked
  `quality_status=rejected` and `summary_zh` is set back to NULL.
- For preprint case (no abstract, only title + year + venue): MAY
  attempt summary_zh from title alone, but apply a stricter
  boilerplate gate; many such cases will end up `quality_status=needs_review`.

`summary_text` MUST equal `summary_zh` (per Paper Review §3.1 P3 and
Shared-Spec §4.2.1). No separate column needed; admin API returns
Postgres `summary_zh` for the `summary_text` field.

#### Scenario: Successful summary_zh generation

- **GIVEN** a paper row with `abstract` present (English, 1500 chars)
- **WHEN** summary_zh generation runs
- **THEN** `summary_zh` is a Chinese paragraph of 200-400 characters
- **AND** boilerplate judge passes
- **AND** `quality_status` may promote to `ready`

#### Scenario: Boilerplate-rejected summary

- **GIVEN** the LLM produces "本文研究了一个重要问题，提出了一种新方法，
  实验证明了有效性。" (generic 36-char boilerplate)
- **WHEN** the boilerplate judge runs
- **THEN** judge returns reject
- **AND** `summary_zh` is set back to NULL
- **AND** `quality_status` is set to `rejected`

### Requirement: Quality status promotion logic

The pipeline MUST manage `quality_status` transitions per the V019
six-value enum (per Paper Review §3.1 P15):

| From → To | Trigger |
|---|---|
| (initial) → `needs_enrichment` | New paper / patent from prof-page with missing fields |
| `needs_enrichment` → `ready` | All required fields present + summary_zh passes boilerplate judge |
| `needs_enrichment` → `partial` | Enrichment partially succeeded (some fields filled, others still missing) |
| `needs_enrichment` → `rejected` | LLM boilerplate judge rejects |
| `ready` → `needs_review` | Manual flag by admin; or downstream contradiction detected |
| `low_confidence` → `ready` / `needs_review` | Identity gate post-enrichment re-evaluation |

The pipeline MUST NOT auto-degrade `ready` → `needs_enrichment` if a
later enrichment fails. `ready` is a strictly forward-monotonic state
in the absence of admin intervention.

`rejected` is a terminal state for the current canonical row;
re-extraction from the same prof page MAY produce a new candidate that
upserts on title, but the LLM judge will run again.

#### Scenario: Promotion to ready

- **GIVEN** a paper row with `quality_status="needs_enrichment"`
- **AND** OpenAlex enrichment fills `abstract` and `citation_count`
- **AND** summary_zh generation succeeds with passing boilerplate judge
- **WHEN** the post-enrichment promotion step runs
- **THEN** `quality_status` becomes `ready`

### Requirement: Cross-domain link writers

The pipeline MUST upsert `professor_paper_link` and
`professor_patent_link` rows idempotently via composite keys
`(paper_id, professor_id)` and `(patent_id, professor_id)`
respectively.

For each link write:

- `match_reason` MUST be set to one of: `"prof_page_declaration"` (
  page-only attribution), `"homepage_title_resolution"` (prof-page
  declaration resolved through title metadata), `"openalex_author_match"`
  (post-enrichment identity match), `"manual_override"` (admin set).
- `confidence` MUST be ∈ [0, 1] floating-point.
- `verified_at` MUST be set when the gate accepted at confidence ≥ 0.8.

#### Scenario: Link upsert is idempotent

- **GIVEN** a `professor_paper_link` row already exists for
  `(paper_id=PAPER-1, professor_id=PROF-A)` with
  `confidence=1.0` and `match_reason="prof_page_declaration"`
- **WHEN** the same prof page is re-crawled and the same paper is
  re-discovered
- **THEN** no new link row is inserted (composite key match)
- **AND** the existing row's `last_updated` is bumped

### Requirement: Deprecation of S2-as-discovery path

The system MUST mark `paper.pipeline.run_paper_pipeline` as deprecated and migrate callers to the prof-page-driven path via `paper.homepage_ingest`.

Until callers migrate (deferred to a follow-up cleanup change), the
function:

- MUST emit a `DeprecationWarning` on first call per process.
- MAY continue to call `discover_professor_paper_candidates` from
  Semantic Scholar to avoid breaking existing scripts.
- MUST NOT be invoked by the new `run_for_single_seed` entry point in
  `prof-seed-admin-console` Phase B.

#### Scenario: Deprecation warning fires once per process

- **GIVEN** a Python process imports and calls
  `paper.pipeline.run_paper_pipeline(...)` for the first time
- **WHEN** the call begins
- **THEN** a `DeprecationWarning` is emitted with text referencing
  this change ID and the migration target
- **AND** subsequent calls in the same process do not re-emit (use
  `warnings.warn(..., stacklevel=2)` once-only pattern)

### Requirement: Refactor hybrid.py to enrichment-only role

The module `apps/miroflow-agent/src/data_agents/paper/hybrid.py` MUST
be refactored so that:

- `discover_*_from_openalex / from_crossref / from_semantic_scholar`
  functions are renamed to `enrich_paper_with_openalex / with_crossref /
  with_semantic_scholar` — signature changes from "given a professor,
  return paper candidates" to "given a paper canonical row, return
  enrichment fields".
- The aggregating wrapper
  `discover_professor_paper_candidates_from_hybrid_sources` is removed.
- The new aggregating wrapper `enrich_paper_with_hybrid_sources(paper)`
  fans out to each enrichment source and merges results per the
  field-level fallback priority above.

Any caller currently invoking `discover_*` from this module MUST be
updated to either (a) use the new enrichment functions if they wanted
post-discovery enrichment, or (b) call homepage_ingest if they wanted
discovery (this typically means deprecating their entire script).

#### Scenario: New enrichment caller

- **GIVEN** a paper canonical row with `doi="10.1234/abc"` but
  missing `abstract`
- **WHEN** `enrich_paper_with_hybrid_sources(paper)` is called
- **THEN** OpenAlex is queried first by DOI; if found, abstract is
  returned
- **AND** Crossref / S2 / arXiv are NOT queried (first-source-wins for
  abstract)
- **AND** `citation_count` is queried only from OpenAlex

