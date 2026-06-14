## ADDED Requirements

### Requirement: Extract SIGS tab template sections

The Professor pipeline MUST parse Tsinghua SIGS official profile pages that use the `.sudy-tab` template. The parser MUST read tab content from the initial HTML and MUST NOT require browser hover execution to access tab bodies.

#### Scenario: Ahmed Elazab tab content is available from HTML

- **WHEN** the extractor processes the official Ahmed Elazab SIGS profile page
- **THEN** it identifies the tab menu labels `个人简历`, `教学`, `研究领域`, `研究成果`, and `奖励荣誉`
- **AND** it extracts non-empty content from the `个人简历`, `研究领域`, `研究成果`, and `奖励荣誉` tab bodies

### Requirement: Extract SIGS research directions from the research tab

SIGS research text under the `研究领域` tab MUST be extracted as a research-direction candidate even when the official content is a long paragraph. Generic navigation labels or empty tab labels MUST NOT become research directions.

#### Scenario: Long research paragraph becomes a research direction

- **WHEN** the Ahmed Elazab page contains a long `研究领域` paragraph about trustworthy artificial intelligence for medical image analysis
- **THEN** the extracted Professor profile includes a research direction derived from that official paragraph
- **AND** the direction does not include unrelated tab labels such as `个人简历`, `教学`, `研究成果`, or `奖励荣誉`

### Requirement: Preserve SIGS structured facts from labeled sections

SIGS labeled sections under the tab template MUST be available as structured Professor facts with source-grounded evidence where the official page provides content.

#### Scenario: CV and award sections produce facts

- **WHEN** a SIGS profile contains `教育经历`, `工作经历`, `学术兼职`, and `荣誉奖项` sections
- **THEN** the extraction flow can produce `education`, `work_experience`, `academic_position`, and `award` facts with evidence text from the official page

### Requirement: Verify SIGS repair with random samples

After implementation, the repair MUST be verified by fetching a random sample of SIGS teachers from the roster/API and reporting extracted fields for review.

#### Scenario: Random sample report includes extracted fields

- **WHEN** the post-fix validation samples SIGS teachers
- **THEN** each sampled teacher report includes source URL, name, title, email, research-direction presence, raw tab-section presence, and any structured facts extracted from the official page
