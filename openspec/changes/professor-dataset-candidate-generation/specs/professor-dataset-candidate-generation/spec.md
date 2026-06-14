## ADDED Requirements

### Requirement: Candidate generation emits source-grounded dry-run evidence

The system MUST provide a bounded Professor dataset candidate-generation dry-run
that enriches dataset-quality closure bucket rows with candidate values or
explicit rejection reasons before write mode is allowed.

Candidate generation MUST use a relaxed quality gate. Usable LLM or
deterministic output SHOULD be emitted as a candidate even when it has quality
issues. The report MUST record `candidate_status`, `quality_flags`,
`source_confidence`, `write_recommendation`, and `llm_self_check` evidence so
operators can review weak candidates. Hard rejection is reserved for rows with
no target entity, no usable candidate content, no grounded inputs for the lane,
or a provider failure that produced no output.

#### Scenario: Candidate dry-run reports every lane

- **WHEN** candidate generation runs for profile summaries, research overviews,
  Professor paper summaries, and duplicate Paper merge planning
- **THEN** the report includes input count, candidate count, validation failure
  count, provider failure count, skipped count, affected Professor ids, affected
  Paper ids, lane-specific samples, and a selection hash
- **AND** each emitted candidate records relaxed-gate evidence including status,
  quality flags, source confidence, write recommendation, and LLM self-check
- **AND** the output is directly consumable by the existing dataset-quality
  closure write-mode evidence gate

#### Scenario: Candidate dry-run is read-only

- **WHEN** candidate generation runs without an explicit write-mode remediation
  command
- **THEN** it MUST NOT update Professor rows, Paper rows, profile sections,
  merge aliases, quality status, pipeline issues, or vector indexes

### Requirement: Profile-summary candidates are Chinese and grounded

The system MUST generate `candidate_profile_summary` values only from official
Professor profile evidence, persisted structured facts, official source text,
and Professor-linked output evidence. The current 200-300 Chinese character
profile-summary contract is a quality target, not a hard blocker for candidate
reporting. Candidates outside the target length MUST be emitted as
`candidate_status=needs_review` with `profile_summary_length_out_of_range`
instead of being rejected when the Chinese content is otherwise usable.

#### Scenario: Sufficient grounded inputs produce a profile-summary candidate

- **WHEN** a short ready Professor profile has official source text or
  structured facts sufficient to describe identity, affiliation, research
  direction, background, or output
- **THEN** candidate generation produces a Chinese `candidate_profile_summary`
  and marks it `ready` when it satisfies the 200-300 character target
- **AND** the candidate evidence records source ids, source hashes or source
  text references, generation method, validation rules, input facts used,
  quality flags, source confidence, write recommendation, and LLM self-check

#### Scenario: Short but usable profile summary remains a candidate

- **WHEN** the configured LLM or deterministic synthesis returns Chinese
  profile-summary content shorter than the target length
- **THEN** candidate generation emits the candidate instead of rejecting it
- **AND** the candidate records `candidate_status=needs_review`,
  `profile_summary_length_out_of_range`, source evidence when available, and a
  review-before-write recommendation

#### Scenario: Unsupported summary generation is rejected

- **WHEN** a row lacks enough official profile facts, source text, or linked
  output evidence for a grounded profile summary
- **THEN** candidate generation does not fabricate a summary
- **AND** it records a rejection reason and recommended next action

### Requirement: Research-overview candidates preserve source traceability

The system MUST generate durable Chinese research-overview candidates from
official source text only. Chinese source text MUST be extracted directly when
available. English source text MAY be translated by an LLM only when the output
preserves source traceability. A source text hash is required for `ready`
candidates, but missing or weak source hashes SHOULD be recorded as quality
flags on usable candidates rather than forcing rejection.

#### Scenario: Chinese research overview is extracted

- **WHEN** official profile text contains a Chinese research-overview section
- **THEN** candidate generation emits `candidate_research_overview_zh` or
  `research_overview_content`
- **AND** the candidate records source page id or URL, source span, source text
  hash, source language, and `generation_method=official_extract`

#### Scenario: English research overview is translated

- **WHEN** official profile text contains an English research-overview section
  and no Chinese overview exists
- **THEN** candidate generation may call the configured LLM translation provider
- **AND** the candidate records source text hash, source language, translated
  Chinese content, provider metadata, and `generation_method=llm_translation`

#### Scenario: Missing source text is rejected

- **WHEN** no supported official research-overview source span can be extracted
- **THEN** candidate generation does not create invented overview content
- **AND** it records a source-missing rejection reason

#### Scenario: Weak source hash is reviewable

- **WHEN** a Chinese research-overview candidate has usable Chinese content but
  lacks a durable source text hash
- **THEN** candidate generation emits the candidate as `needs_review`
- **AND** the candidate records `missing_source_text_hash`, weak source
  confidence, and source/provenance evidence available for later repair

### Requirement: Professor paper-summary candidates use deduplicated verified links

The system MUST generate `candidate_paper_summary` values only from
deduplicated eligible verified Professor-Paper links seeded by official
Professor-owned pages. Rejected, uncertain, and provider-only author-search
records MUST NOT be treated as verified Professor core inputs. Unresolved
duplicate status SHOULD downgrade a candidate to `needs_review` rather than
blocking candidate reporting when verified Professor-seeded Paper links exist.

#### Scenario: Verified linked papers produce paper-summary candidate

- **WHEN** a Professor has deduplicated verified Paper links with enough title,
  year, venue, topic, abstract, or summary evidence
- **THEN** candidate generation emits a grounded Chinese
  `candidate_paper_summary`
- **AND** the candidate evidence records the Paper ids used, excluded Paper ids
  and reasons, duplicate status, and source-page provenance

#### Scenario: Provider-only author search is not accepted

- **WHEN** external provider results are available only from a Professor-name
  author search and are not seeded by official Professor-owned pages
- **THEN** candidate generation MUST NOT use those results to create a
  Professor paper list or paper summary
- **AND** it records a provider-only rejection reason

#### Scenario: Unresolved duplicates produce reviewable paper summary candidate

- **WHEN** verified Professor-seeded Paper links exist but the Professor still
  has unresolved duplicate Paper evidence
- **THEN** candidate generation emits a Chinese `candidate_paper_summary` with
  `candidate_status=needs_review`
- **AND** the candidate records `unresolved_duplicate_status`, included Paper
  ids, excluded Paper ids, source-page provenance, and a review-before-write
  recommendation

### Requirement: Duplicate Paper merge candidates are conservative

The system MUST generate duplicate Paper canonical merge candidates only when
there is safe identity evidence for automatic writing. DOI or arXiv equality
SHOULD be preferred. A title/year duplicate group without sufficient
identifier, author, venue, or source evidence MAY still be emitted as a
manual-review merge candidate, but it MUST be marked `needs_review` and MUST
NOT be recommended for automatic writing.

#### Scenario: Identifier match produces merge candidate

- **WHEN** duplicate verified Professor-Paper rows share DOI or arXiv identity
  and one canonical Paper row is richer than the others
- **THEN** candidate generation emits `canonical_paper_id`, `old_paper_ids`,
  `merge_reason`, evidence type, confidence, and affected Professor/Paper ids
- **AND** the merge candidate preserves official Professor-page evidence for
  the displayed canonical Paper

#### Scenario: Ambiguous duplicate group becomes manual-review candidate

- **WHEN** a duplicate title/year group lacks sufficient safe identity evidence
- **THEN** candidate generation emits a merge candidate with weak evidence,
  `candidate_status=needs_review`, and a review-before-write recommendation
- **AND** it records unsafe-merge quality flags and manual-review provenance

### Requirement: Candidate generation handles provider failures visibly

The system MUST report LLM/provider failures, validation failures, and skipped
rows as first-class dry-run evidence. Provider failure MUST NOT silently promote
or write a row.

#### Scenario: LLM provider failure is visible

- **WHEN** the configured LLM provider fails while generating or translating a
  candidate
- **THEN** the dry-run report increments provider failure counts
- **AND** the affected row records provider, stage, error class, retryability,
  and next action

### Requirement: Candidate dry-run uses real LLM providers by default

The system MUST connect a real OpenAI-compatible LLM provider for
`candidate-dry-run` by default in development. Deterministic synthesis MAY
remain available only as an explicit operator-selected mode. Missing
credentials, provider request failures, empty responses, and malformed JSON MUST
be recorded as provider failures or review evidence; they MUST NOT be silently
converted into deterministic successful candidates. The CLI MUST load the
application-local `.env` file before resolving Professor LLM settings so local
development credentials are available without shell-level exports.

#### Scenario: Default candidate dry-run builds a real provider

- **WHEN** `run_professor_dataset_quality_closure.py --mode candidate-dry-run`
  runs without an explicit deterministic provider mode
- **THEN** the CLI resolves the configured Professor LLM profile and injects
  real profile-summary, research-translation, and paper-summary providers into
  candidate generation
- **AND** candidate evidence records provider metadata including profile, model,
  prompt hash, response hash, finish reason when available, and task type

#### Scenario: Candidate dry-run loads local environment credentials

- **WHEN** the CLI module starts in development
- **THEN** it loads `apps/miroflow-agent/.env` before building real candidate
  LLM providers
- **AND** DeepSeek credentials in that file or the supported key-file fallback
  can be resolved without logging raw API keys

#### Scenario: Missing provider credentials are visible

- **WHEN** the default real provider mode cannot resolve an API key
- **THEN** candidate generation does not silently fall back to deterministic
  synthesis
- **AND** each affected LLM-backed lane records a retryable provider failure
  with `MissingLLMCredentials`, provider profile, model, stage, and next action

#### Scenario: LLM output is self-checked before candidate reporting

- **WHEN** a real LLM provider returns usable candidate JSON
- **THEN** the candidate is emitted only as dry-run evidence and is never written
  directly to Professor or Paper tables
- **AND** the candidate records `llm_self_check`, quality flags, source
  confidence, source hashes, provider metadata, and write recommendation

### Requirement: Candidate output remains within Professor core boundaries

The system MUST preserve the Professor official profile -> verified paper chain
as the seed for Professor core remediation. Candidate generation MUST keep
company/news association and hidden company/startup roles outside Professor core
readiness.

#### Scenario: Hidden company role remains outside candidate generation

- **WHEN** a Professor has no official company/startup role in the Professor
  profile
- **THEN** candidate generation does not block profile-summary, research
  overview, or paper-summary candidates for that reason
- **AND** any company/news association remains a runtime multi-source recall or
  downstream cross-domain-linking concern
