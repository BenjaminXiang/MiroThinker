## ADDED Requirements

### Requirement: Prose answers never expose protocol markers

Every provider-echo marker family in the canonical-v2 namespace MUST be removed
from user-visible prose, including the closing form with a slash and any
half-width/full-width bar variant.

#### Scenario: Closing answer marker echoed into prose

- **WHEN** the model emits `前文</|canonical_v2_answer_v1|>后文`
- **THEN** the rendered answer contains `前文后文`
- **AND** the marker is recorded as a redaction, not shipped

### Requirement: A named company only uses its own local claims

On a non-enumeration turn whose query names a company, a local `company` claim
MUST be eligible only when its handle name plausibly denotes that company.
Other local companies MUST NOT be profiled or cited; web evidence remains
eligible so a real company absent from the pack can still be answered.

#### Scenario: Unknown company name

- **WHEN** a fresh turn asks `严格验收机器人公司是做什么的`
- **AND** the pack has no company matching that name
- **THEN** no local company claim for a neighbour (for example 普渡科技) is
  selected or cited

#### Scenario: Partial name of a known company

- **WHEN** the turn asks `普渡科技公司是做什么的`
- **THEN** the local handle `深圳市普渡科技有限公司` remains eligible

#### Scenario: Enumeration phrasing

- **WHEN** the turn asks `深圳有哪些机器人公司`
- **THEN** no named-company filter runs and the normal enumeration path applies

#### Scenario: Relation phrasing

- **WHEN** the turn asks `丁文伯创办的公司是哪家`
- **THEN** the phrase `丁文伯创办的公司` is not treated as a company name and
  the relationship answer keeps its local company claim

### Requirement: Enumeration disclosure is compact

The member-coverage sentence MUST name at most 8 recalled companies in
recall-rank order and report the remainder as a count. The former 64-name
window made list answers end in a wall of names; the top of the recall order
(including the G7 rank-5 member) still ships.

#### Scenario: Eighty recalled members

- **WHEN** an enumeration answer recalls 80 unmentioned companies
- **THEN** the disclosure lists the first 8 and appends `等（共 80 家）`
- **AND** the ninth name does not appear

### Requirement: Thing-pronoun attribute follow-ups bind the displayed company

When the previous turn displayed exactly one company and the follow-up uses
`它` / `该公司` with a company attribute (`专利/论文/产品/业务/公司/简介/做什么`),
the planning anchor MUST be that company even if the answer receipt captured an
incidental patent or web handle. Person pronouns (`他/她`) keep their existing
anchor decision.

#### Scenario: Company answer then thing-pronoun patent follow-up

- **WHEN** the previous answer displayed 深圳无界智航科技有限公司
- **AND** the follow-up asks `它有哪些专利`
- **THEN** the plan binds the company anchor, not an incidental patent handle
