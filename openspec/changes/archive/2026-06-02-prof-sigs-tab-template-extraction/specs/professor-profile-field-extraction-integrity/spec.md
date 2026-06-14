## ADDED Requirements

### Requirement: SIGS tab labels are parsed as sections, not title content

The Professor extractor MUST treat Tsinghua SIGS tab labels and tab bodies as sectioned profile content. Tab labels and body content MUST NOT contaminate the bounded academic title field, while section bodies remain available for research-direction and structured-fact extraction.

#### Scenario: SIGS title remains bounded while tab bodies are extracted

- **WHEN** a SIGS profile contains `Ahmed Elazab 助理教授 ， 博士生导师` and tab labels such as `个人简历`, `研究领域`, and `奖励荣誉`
- **THEN** the extracted title is exactly `助理教授，博士生导师`
- **AND** the title excludes tab labels and tab body text
- **AND** the tab body text remains available for structured extraction
