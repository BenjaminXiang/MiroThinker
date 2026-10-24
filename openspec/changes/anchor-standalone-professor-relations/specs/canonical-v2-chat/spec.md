## ADDED Requirements

### Requirement: Anchor a standalone named subject for relation queries

A single-turn chat query that names a pack entity and asks for a relation MUST
be planned with that entity as its displayed anchor, so the relationship lane
and the web subject-consistency gate execute. Exact-name resolution MUST decline
when the name maps to more than one canonical entity.

#### Scenario: Professor asks for founded companies

- **WHEN** a new session sends `丁文伯创办的公司是哪家`
- **THEN** the planning request carries the professor canonical id as its
  displayed anchor and the plan executes `professor_company_role` plus web
- **AND** the answer identifies 深圳无界智航科技有限公司 rather than a
  near-name person

#### Scenario: Company asks for its founder

- **WHEN** a new session sends `无界智航的创始人是谁`
- **THEN** the planning request carries the company canonical id as its
  displayed anchor and the plan executes `professor_company_role` in the
  company-to-professor direction

#### Scenario: Ambiguous name declines to anchor

- **WHEN** the named form maps to two distinct canonical entities
- **THEN** the planning request keeps no displayed anchor and existing
  behavior is unchanged

### Requirement: Named-person patent claims require the person in local evidence

For a query of the form `<person>有哪些专利`, a local patent evidence item MUST
contain the person's name in its evidence text before it can become a claim.
Web evidence remains eligible; unrelated local patent handles must not appear in
the answer's citations.

#### Scenario: Unrelated local patents are not cited

- **WHEN** the local patent lane returns generic patents with empty inventor
  lists for `丁文伯有哪些专利`
- **THEN** those items are excluded from claims and the answer cites only the
  web evidence that names 丁文伯
