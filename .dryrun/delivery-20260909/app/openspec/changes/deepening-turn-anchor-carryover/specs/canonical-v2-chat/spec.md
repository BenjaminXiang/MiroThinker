## ADDED Requirements

### Requirement: Deepening turns SHALL carry the session subject

The chat layer SHALL recognize a subject-carryover deepening follow-up — a continuation
intent, a generic referential institution noun (该/这个/此 + 中心/机构/组织/平台/单位/项目/
实验室/研究院/研究所/基地/联合体), or a domain-unconstrained singular referent — provided the
query names no explicit subject of its own. On such a turn over a session holding a soft
subject anchor, the chat layer SHALL inject the stored subject as
`soft_context_subject`, SHALL keep it on the committed session, and SHALL NOT emit a
referent clarification. When a canonical anchor is active, an anaphoric subject reference
SHALL bind it into planning under the same domain guard as typed singular referents.
Person-typed pronouns over an organization-level soft subject SHALL remain a clarification,
and explicit named subjects SHALL keep winning over any carried anchor.

#### Scenario: referential deepening keeps the org subject

- **GIVEN** turn 1 established the web-only subject `国际先进技术应用推进中心（深圳）`
- **WHEN** turn 2 is `这个中心的企业培育情况怎么样`
- **THEN** the planning request carries the subject, the turn is not a clarification or a
  topic switch, and the committed session still holds the subject

#### Scenario: bare pronoun deepening answers about the subject

- **GIVEN** the same session after an elaboration follow-up
- **WHEN** turn 3 is `它有哪些布局和进展`
- **THEN** the turn answers about the carried subject instead of clarifying or
  free-retrieving unpinned topic views

#### Scenario: typed pronoun mismatch still clarifies

- **GIVEN** a session anchored on an organization-level soft subject
- **WHEN** the follow-up is `他有哪些论文`
- **THEN** the turn still yields a referent clarification (person pronoun over an
  organization subject is a genuine mismatch)

### Requirement: Vector-lane records SHALL NOT capture the session anchor on soft-anchored turns

On a turn that planned no canonical displayed ids and carried a soft subject, the chat
layer SHALL commit the answer's canonical `active_anchor` only when its display name
plausibly matches the turn's subject (qualifier-stripped containment, or a shared contiguous
run of at least three characters); otherwise the anchor SHALL be dropped from the committed
receipt with a journal line. Web handles SHALL never be dropped, and turns that planned
canonical displayed ids SHALL never be sanitized.

#### Scenario: leaked professor record does not poison later turns

- **GIVEN** a web-only org turn whose answer returned a receipt anchored on an unrelated
  canonical professor record
- **WHEN** the turn commits
- **THEN** the committed receipt carries no canonical anchor, and the next referential
  turn binds the soft subject rather than the leaked record

#### Scenario: matching canonical anchor survives

- **GIVEN** a soft-anchored turn whose subject is `优必选` and whose answer anchored the
  canonical entity `优必选科技`
- **WHEN** the turn commits
- **THEN** the canonical anchor is kept

### Requirement: Rewrite views SHALL stay pinned to the soft subject

Whenever `soft_context_subject` is present on a planning request, every non-deterministic
query view SHALL contain the subject text; the existing protected-slot missing-append SHALL
re-pin rewrite views that dropped it, and a journal marker SHALL be logged whenever a re-pin
fires so the tripwire rate is observable in production journals.

#### Scenario: rewriter drops the subject

- **GIVEN** a planning request with `soft_context_subject` and rewriter views that omit the
  subject
- **WHEN** the plan is assembled
- **THEN** every rewrite view contains the subject and the journal marker is logged
