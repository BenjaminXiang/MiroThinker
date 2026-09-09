# professor-profile-field-extraction-integrity Specification

## Purpose
TBD - created by archiving change prof-title-contamination-repair. Update Purpose after archive.
## Requirements
### Requirement: Professor title fields are bounded academic role phrases

The Professor extraction pipeline MUST only populate title or position fields
with bounded academic role phrases. A title value MUST NOT include reader
metadata, page title metadata, navigation text, education sections, research
sections, profile summary text, publication text, or other non-title body
content.

#### Scenario: CUHK(SZ) SDS reader Markdown title is bounded

- **WHEN** the extractor processes the CUHK(SZ) SDS BRESAR, Miha profile text
  containing reader metadata and the profile heading `## BRESAR, Miha 助理教授`
- **THEN** the extracted title is exactly `助理教授`
- **AND** the extracted title excludes `URL Source`, `Published Time`,
  `Markdown Content`, navigation text, education content, research sections,
  profile summary text, and publication text

#### Scenario: Genuine compound academic title remains valid

- **WHEN** a profile contains a bounded role phrase such as `教授，博士生导师`
- **THEN** the extractor may keep the bounded role phrase as the title
- **AND** the title guard does not require the title to be a single token

### Requirement: Contaminated title candidates are rejected before canonical writes

The Professor pipeline MUST reject contaminated title candidates before they
are converted into canonical Professor affiliations. If no clean bounded title
can be extracted, the title field MUST be left empty rather than storing page
chrome or body text.

#### Scenario: Reader metadata is not written as affiliation title

- **WHEN** a title candidate contains `URL Source`, `Published Time`, or
  `Markdown Content`
- **THEN** that candidate is rejected unless a clean bounded title can be
  extracted from the same profile content
- **AND** `professor_affiliation.title` is not populated with the contaminated
  candidate

#### Scenario: Section content is not written as affiliation title

- **WHEN** a title candidate contains section labels such as `教育背景`,
  `研究领域`, `个人简介`, or `学术著作`
- **THEN** that candidate is rejected unless a clean bounded title can be
  extracted from the same profile content

#### Scenario: Corrected title supersedes stale current variants

- **WHEN** a Professor's primary affiliation title is corrected from a
  contaminated candidate to a clean bounded title for the same official source
  page
- **THEN** the corrected affiliation is the only current affiliation variant
  for that Professor, institution, department, and source page
- **AND** the stale contaminated variant remains available as historical data
  but is no longer marked current

### Requirement: Known title blocker is re-verified against real data

The BRESAR, Miha CUHK(SZ) SDS title blocker MUST NOT be considered resolved
until the real current data is verified after repair.

#### Scenario: BRESAR title blocker is cleared

- **WHEN** the targeted repair and rerun or targeted data rewrite completes
- **THEN** `miroflow_real.professor_affiliation.title` for BRESAR, Miha is
  exactly `助理教授`
- **AND** the P8 post-full audit reports `cuhk-sds-bresar-title` as resolved
- **AND** the verification record includes the command that proved the real
  row state

### Requirement: SIGS tab labels are parsed as sections, not title content

The Professor extractor MUST treat Tsinghua SIGS tab labels and tab bodies as sectioned profile content. Tab labels and body content MUST NOT contaminate the bounded academic title field, while section bodies remain available for research-direction and structured-fact extraction.

#### Scenario: SIGS title remains bounded while tab bodies are extracted

- **WHEN** a SIGS profile contains `Ahmed Elazab 助理教授 ， 博士生导师` and tab labels such as `个人简历`, `研究领域`, and `奖励荣誉`
- **THEN** the extracted title is exactly `助理教授，博士生导师`
- **AND** the title excludes tab labels and tab body text
- **AND** the tab body text remains available for structured extraction

