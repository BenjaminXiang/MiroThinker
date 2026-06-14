## ADDED Requirements

### Requirement: Professor detail exposes official research overview
The admin professor detail payload MUST include a `research_output.research_overview` string when the persisted raw profile text contains a labeled official research overview section.

#### Scenario: SIGS research overview is returned
- **WHEN** an admin opens a SIGS professor whose raw profile text contains a `研究领域` section
- **THEN** the admin detail payload includes the section body as `research_output.research_overview`

### Requirement: Professor detail groups facts by meaning
The professor detail UI MUST display typed professor facts in user-facing groups instead of one mixed fact table.

#### Scenario: Reviewer can inspect Ahmed-like profile content
- **WHEN** an admin opens a professor detail page with research topics, education, work experience, awards, and academic positions
- **THEN** research topics are shown with the research content
- **AND** education, work experience, awards, and academic positions are shown in their own labeled areas
