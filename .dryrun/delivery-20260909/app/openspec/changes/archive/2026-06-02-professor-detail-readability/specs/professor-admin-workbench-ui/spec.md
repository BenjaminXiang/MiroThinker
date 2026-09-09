## MODIFIED Requirements

### Requirement: Workbench frontend
The professor detail route MUST render a professor-specific audit workbench with the quality diagnosis visible on initial render and provenance reachable from key fields. The workbench MUST group typed facts by user-facing meaning, including research topics, official research overview text when available, academic positions, education, work experience, awards, papers, and patents, rather than rendering all fact types in one undifferentiated table.

#### Scenario: Experience placeholder remains contract-compatible

- **GIVEN** no structured experience facts exist for a professor
- **WHEN** the workbench renders the experience section
- **THEN** it renders a `not_extracted` state without breaking the
  layout

#### Scenario: Official research overview is readable

- **GIVEN** the admin detail payload includes `research_output.research_overview`
- **WHEN** the workbench renders the professor detail page
- **THEN** the overview text is visible in the research section
- **AND** typed facts are grouped into labeled areas instead of a single mixed fact table
