## ADDED Requirements

### Requirement: News-Headline Anchor Guard

A name is headline-shaped when it carries a source-suffix pattern
（「X - 来源」/「X——来源」/「X_|来源」), contains event-verb markers
（打造/推进/揭牌/成立/建设/发布/签署/合作/落地 …), or reads as a sentence
(length beyond entity scale). Headline-shaped names SHALL NOT become the
session's active anchor. When the receipt anchor on a soft-anchored turn is
headline-shaped, the session SHALL keep its previous anchor if one exists,
else fall back to the soft subject; the headline is never bound.

#### Scenario: G1 headline does not anchor the session

- **WHEN** turn 1 asks about a web-only subject and the answer layer
  registers a web handle titled 「河套深圳园区打造深港科技创新聚集地 - 香港中联办」
  as the receipt anchor
- **THEN** the committed session anchor is NOT the headline (soft subject or
  prior anchor retained)
- **AND** turn 2 ("它有哪些布局和进展") answers about the queried subject

### Requirement: Expansion Base Is the Session Subject

Expansion-family turns（「还有哪些类似/同类/相关的…」）SHALL derive their
retrieval base from the session subject/anchor (its domain and, where
available, its peer set). The system SHALL NOT substitute an unrelated base.

#### Scenario: G5 expansion answers from the session subject's peers

- **WHEN** the session subject is 优必选 and the user asks 「还有哪些类似的公司」
- **THEN** the answer set consists of robot/embodied-AI peers of 优必选
- **AND** the turn trace's answer subject is not an unrelated company (微众银行 form banned)

### Requirement: Bare Entity Name Is a Subject

A bare entity-name query（an institution/person name with no other
operators）SHALL be treated as a subject statement for that entity — the
anti-echo guard SHALL NOT force a referent clarification loop on it.

#### Scenario: bare-name opening does not enter a clarification loop (P3)

- **WHEN** turn 1 is a bare institution name and turn 2 deepens
- **THEN** no "您指的是哪家机构" clarification fires on either turn

### Requirement: Type-Aware Referent Handling

When a personal referent（他/她/该教授…）operates over an
organization-anchored session — or an organization referent over a
person-anchored session — the clarification gate SHALL engage BEFORE
synthesis, and synthesis SHALL verify the answer subject type matches the
referent type; a mismatched binding（article title as institution, person
treated as org）SHALL NOT ship as the answer subject.

#### Scenario: G3 person-referent over headline-poisoned session

- **WHEN** the user asks 「他有哪些论文」 and the session anchor is an
  organization (or headline) rather than a person
- **THEN** the turn answers in the person domain or asks a typed
  clarification — never binds an article title as the institution answer
