## ADDED Requirements

### Requirement: Dataset closure starts with bucketed read-only audit

The system MUST provide a read-only Professor dataset quality closure audit
that expands aggregate blockers into row-level or group-level remediation
buckets before any write-mode backfill runs.

#### Scenario: Audit classifies remaining blockers

- **WHEN** the dataset closure audit runs against `miroflow_real`
- **THEN** it reports buckets for short ready profile summaries, missing Chinese
  research overviews, missing Professor paper summaries, and duplicate verified
  Professor-paper title/year groups
- **AND** each bucket row includes stable identifiers, current status, proposed
  remediation lane, automatic-eligibility flag, and skip or blocker reason when
  not automatically eligible

#### Scenario: Audit remains read-only

- **WHEN** the dataset closure audit runs without an explicit write flag
- **THEN** it MUST NOT update Professor rows, Paper rows, merge aliases,
  profile sections, pipeline issues, or index artifacts

### Requirement: Dry-run evidence gates every write lane

Every automated remediation lane MUST run in bounded dry-run mode and record
evidence before write mode is allowed for that lane.

#### Scenario: Dry-run reports write plan

- **WHEN** a dry-run runs for profile summaries, research overviews, Professor
  paper summaries, or duplicate paper merges
- **THEN** the report includes input count, eligible count, proposed write
  count, skipped count, representative samples, validation failures, provider
  failures, and affected Professor/Paper ids

#### Scenario: Write mode is blocked without dry-run evidence

- **WHEN** an operator attempts a write-mode remediation batch without current
  dry-run evidence for the same lane and selection
- **THEN** the command refuses to write
- **AND** it reports the missing dry-run evidence requirement

### Requirement: Profile summary closure enforces user-facing quality

The system MUST repair short or shallow ready Professor profile summaries only
from official profile facts, official source text, persisted profile sections,
and Professor-linked output evidence. Repaired summaries MUST satisfy the
current 200-300 character Chinese profile-summary contract before ready
promotion.

#### Scenario: Short ready summary is repaired from grounded inputs

- **WHEN** a ready Professor has a `profile_summary` shorter than 200 Chinese
  characters and sufficient grounded inputs exist
- **THEN** the closure generates or writes a 200-300 character Chinese summary
  that covers identity, affiliation, research direction, background or output
- **AND** Professor quality re-evaluation may keep or promote the row to
  `ready` only after the summary passes length and repetition checks

#### Scenario: Insufficient summary inputs create visible issue

- **WHEN** a Professor has a short summary but lacks sufficient official facts,
  source text, or output evidence for a grounded rewrite
- **THEN** the closure does not fabricate a summary
- **AND** it records a visible unresolved issue or residual-risk row with the
  missing input reason

### Requirement: Research overview closure persists Chinese source-grounded sections

The system MUST backfill durable Chinese `research_overview` profile sections
for Professors whose official profile source contains research overview text in
Chinese or English. English source text MAY be translated by an LLM only when
the output is keyed to source text hash and preserves source traceability.

#### Scenario: Chinese overview is extracted directly

- **WHEN** official profile text contains a Chinese research overview section
- **THEN** the closure persists a Chinese `research_overview` section with
  professor id, language, source page or source hash, generation method, run id,
  and timestamps

#### Scenario: English overview is translated idempotently

- **WHEN** official profile text contains an English research overview section
  and no Chinese section exists
- **THEN** the closure may translate it to Chinese
- **AND** repeated runs with the same source hash do not create conflicting
  duplicate sections

#### Scenario: Missing official overview remains unresolved

- **WHEN** no supported official research overview text can be extracted
- **THEN** the closure does not create an invented overview
- **AND** it records an unresolved reason instead of silently passing the row

### Requirement: Professor paper summaries use deduplicated verified links

The system MUST generate Professor `paper_summary` only from deduplicated
eligible verified Professor-paper links and MUST exclude rejected, uncertain,
merged-away, or unresolved duplicate records.

#### Scenario: Eligible verified papers produce summary

- **WHEN** a Professor has deduplicated eligible verified paper links and lacks
  `paper_summary`
- **THEN** the closure generates or writes a grounded Professor
  `paper_summary`
- **AND** the summary cites only the eligible linked paper inputs used for that
  Professor

#### Scenario: Duplicate links block summary readiness

- **WHEN** a Professor still has active duplicate verified title/year paper
  groups after merge planning should have run
- **THEN** the closure does not use the duplicated group for final ready
  promotion
- **AND** it records the duplicate blocker for merge remediation or residual
  review

### Requirement: Duplicate paper closure preserves canonical traceability

The system MUST plan and execute duplicate Professor-paper link closure through
canonical Paper ids, preferring richer rows and preserving old-to-new merge
traceability plus official Professor-page evidence.

#### Scenario: Identifier match merges page-only row

- **WHEN** a page-only Professor-linked paper matches an enriched Paper row by
  DOI or arXiv id
- **THEN** the closure migrates the verified Professor link to the canonical
  Paper id or resolves it through a merge alias
- **AND** official Professor-page evidence remains attached to the displayed
  canonical paper

#### Scenario: Ambiguous fuzzy match is not auto-merged

- **WHEN** a duplicate title/year group lacks sufficient DOI, arXiv, author,
  venue, or source evidence for a safe merge
- **THEN** the closure does not auto-merge the group
- **AND** it records an unresolved duplicate issue with the evidence gap

### Requirement: Batch writes require post-write re-evaluation and sampling

Every write-mode closure batch MUST be followed by targeted quality
re-evaluation, affected-id audit checks, API sampling, and refresh selection
evidence before the batch can be considered complete.

#### Scenario: Batch completion records verification evidence

- **WHEN** a write-mode batch finishes
- **THEN** the run evidence records changed Professor ids, changed Paper ids,
  write counts, quality-status before/after distribution, remaining blocker
  counts for affected ids, Admin Professor detail samples, Paper detail samples
  when papers changed, and index refresh selection

#### Scenario: Failed post-write verification blocks completion

- **WHEN** post-write quality re-evaluation or API sampling fails for a changed
  row
- **THEN** the batch is not marked complete
- **AND** the failure is recorded with the row id, stage, and reason

### Requirement: Professor core closure excludes hidden company roles

The dataset closure MUST keep Professor core readiness independent from
company/news association completeness. It MUST NOT require private,
non-disclosed, or non-official company roles to be present in Professor profile
data.

#### Scenario: Company association is not a Professor blocker

- **WHEN** a Professor has complete core profile and paper quality evidence but
  no company or startup role in the official Professor profile
- **THEN** the dataset closure does not block Professor core readiness for that
  reason
- **AND** any company/news association remains available to runtime
  multi-source recall or downstream cross-domain evidence

### Requirement: External providers enrich only Professor-seeded papers

The dataset closure MUST NOT create a Professor's offline paper list by
searching external literature providers using only the Professor name.
External providers MAY enrich paper candidates already discovered from official
Professor-owned pages.

#### Scenario: No official paper candidates prevents provider-only discovery

- **WHEN** a Professor has no extractable paper candidates from official
  Professor-owned pages
- **THEN** the dataset closure does not create a paper list solely from
  OpenAlex, Crossref, Semantic Scholar, DBLP, arXiv, or web-search author-name
  results
- **AND** it records a no-paper-source or extraction-blocked state

### Requirement: Closure finishes only when blockers are cleared or classified

The dataset closure MUST NOT be marked complete until every targeted dataset
blocker is either cleared by verified writes or converted into a visible
unresolved issue or accepted residual-risk row with evidence and next action.

#### Scenario: Final closure report has no silent blockers

- **WHEN** the final dataset closure audit runs
- **THEN** it reports zero unclassified blockers for short ready summaries,
  missing Chinese research overviews, missing Professor paper summaries, and
  duplicate verified paper title/year groups
- **AND** any remaining unresolved records are listed with reason, confidence
  impact, and next action

#### Scenario: Completion artifacts are updated after evidence

- **WHEN** the dataset closure is considered complete
- **THEN** `tasks.md`, `acceptance.md`, and
  `.agents/runs/professor-dataset-quality-closure/verification.md` contain the
  final audit command, batch reports, skipped checks, residual-risk decisions,
  verification outputs, and OpenSpec validation result
