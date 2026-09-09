## ADDED Requirements

### Requirement: Each structured field has a declared multi-source completion chain

The system SHALL complete each professor structured field (`research_directions`, `research_overview`, `education`, `academic_position`, `work_experience`, `award`, `contact`) by attempting a **declared priority-ordered source chain**, and SHALL leave the field empty only after the chain is exhausted. The chain per field SHALL be: (1) homepage section extraction (per-school template), (2) LLM structured-field extraction, (3) external enrichment where applicable (OpenAlex `concepts` for `research_directions`; ORCID education/employment for `education`/`work_experience`). Fields with no reliable external source (`academic_position`, `award`, `contact`) stop at L2.

#### Scenario: Field attempted through its full chain before being left empty
- **WHEN** a professor's `research_directions` is empty
- **THEN** the system attempts homepage section extraction, then LLM extraction, then OpenAlex-concepts enrichment, and only records the field as residual if all three yield nothing

#### Scenario: External-source-applicable fields use enrichment
- **WHEN** `education` cannot be extracted from the homepage
- **THEN** the system attempts ORCID education enrichment before leaving it empty

### Requirement: LLM structured-field extraction is template-agnostic (Layer 2)

The system SHALL provide an LLM structured-field extractor that, given a professor homepage's text, extracts the structured facts (`research_topic`, `education`, `academic_position`, `work_experience`, `award`, `contact`) independent of the school's HTML template. This layer SHALL run when the homepage section extractor (Layer 1) returns nothing for a field.

#### Scenario: Template-resistant homepage yields fields via LLM
- **WHEN** a school whose homepage template the section extractor does not recognize is processed
- **THEN** the LLM extractor still populates the structured facts from the page text

### Requirement: External enrichment backfills template-agnostic fields (Layer 3)

The system SHALL enrich `research_directions` from OpenAlex author `concepts`/`x_concepts` (extending `openalex_metrics.py` beyond h-index), and SHALL enrich `education` and `work_experience` from ORCID education/employment sections when an ORCID iD is present. Enrichment SHALL run after L1/L2 yield nothing.

#### Scenario: OpenAlex concepts fill missing research directions
- **WHEN** a professor with an OpenAlex author record has empty `research_directions` after L1/L2
- **THEN** the top OpenAlex concepts are written as `research_topic` facts with OpenAlex provenance

#### Scenario: ORCID education fills missing education
- **WHEN** a professor with an ORCID iD has empty `education` after L1/L2
- **THEN** ORCID education/employment entries are written as `education`/`work_experience` facts with ORCID provenance

### Requirement: Total-extraction failures are diagnosed and fixed before field layers (Layer 4)

The system SHALL detect schools where the **whole** homepage is unextracted (all fields near-empty — e.g., HIT-Shenzhen 0% across fields) and SHALL diagnose the cause (HTTP block / JS-rendered / URL structure / selector) and fix the crawl before attempting L1–L3, because no field layer can succeed on a page that was not fetched/parsed.

#### Scenario: Total-failure school is detected and crawl-fixed first
- **WHEN** a school's professors have ~0% fill across all structured fields
- **THEN** the system flags it as a total-crawl-failure and routes it to crawl diagnosis/fix ahead of field completion

### Requirement: Field-completeness gate measures per-school per-field fill rate

The system SHALL provide a field-completeness audit (`run_professor_field_completeness_audit.py`) that reports, per school and per field, the fill rate, and SHALL compare against declared targets. Audit output SHALL be saved as an artifact.

#### Scenario: Audit reports per-school per-field fill rates
- **WHEN** the audit runs against `miroflow_real`
- **THEN** it emits a per-school × per-field fill-rate table to a saved artifact, flagging fields below target

### Requirement: Completion closes its issues (closure, not file-only)

When a field is completed (written via any layer), the system SHALL resolve the matching `pipeline_issue` row (if one was filed for that professor × field gap) with the completing `run_id` and source. The system SHALL NOT leave completed-field gaps as open `pipeline_issue` rows (addresses root cause A1).

#### Scenario: Completed field resolves its gap issue
- **WHEN** a field that had an open field-gap `pipeline_issue` is completed
- **THEN** that `pipeline_issue` is marked resolved with the completing `run_id` and source

### Requirement: Completed fields carry source provenance and run_id

Every completed field value SHALL record its source (`homepage_section` / `llm_extraction` / `openalex` / `orcid`) and the producing `run_id`, preserving source traceability. No field SHALL be written without a source attribution.

#### Scenario: Externally-enriched field is traceable
- **WHEN** `research_directions` is filled from OpenAlex
- **THEN** the resulting facts record source `openalex` and the `run_id`

### Requirement: English field values are translated to Chinese (bilingual, original preserved)

For any professor structured-field value (`research_directions`, `education`, `work_experience`, `academic_position`, `profile_summary`) whose original crawled text is in English, the system SHALL produce a **bilingual** form that preserves the original and adds Chinese: either `English (Chinese translation)` or `Chinese (English original)`. The original crawled text SHALL never be lost. This applies both to newly-extracted fields and to **existing DB field values** (a backfill pass over current rows). Chinese-original values are left as-is (optionally augmented with an English gloss). The translation reuses the existing translation provider infrastructure.

#### Scenario: English research direction becomes bilingual
- **WHEN** a professor's crawled `research_directions` value is English (e.g. "machine learning")
- **THEN** the stored value is bilingual, e.g. `machine learning (机器学习)`, with the original preserved

#### Scenario: Existing English DB field is backfilled to bilingual
- **WHEN** an existing professor fact row holds an English value
- **THEN** a translation backfill rewrites it to the bilingual form without losing the original

#### Scenario: Chinese-original value is preserved
- **WHEN** a field value is already Chinese
- **THEN** it is left as-is (no destructive overwrite; English gloss optional)
