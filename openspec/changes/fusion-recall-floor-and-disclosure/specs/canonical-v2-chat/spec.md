## ADDED Requirements

### Requirement: Local-First Dual-Source Weighting

When web results and local canonical evidence are fused, local canonical
evidence SHALL be preferred at equal relevance (local-first tiebreaker in
the merged result ordering).

#### Scenario: local and web at equal relevance

- **WHEN** a local canonical record and a web result have equal relevance
  to the query
- **THEN** the local record ranks first in the merged set

### Requirement: Understanding Disclosure

The SSE answer event SHALL carry `understood_subject` (the resolved
answer subject name or null); the chat UI SHALL render「系统理解为：关于X」
when a subject is present, positioned above the answer text.

#### Scenario: subject-bearing answer shows disclosure

- **WHEN** the system resolves the answer subject to 优必选
- **THEN** the SSE answer event carries understood_subject="深圳市优必选科技股份有限公司"
- **AND** the chat UI displays「系统理解为：关于深圳市优必选科技股份有限公司」

### Requirement: Frontend Convergence (P9)

The backend static streaming page (`/chat`) is the declared reference
frontend. The React SPA (`frontend/`) SHALL display a deprecation notice
directing users to `/chat`.

#### Scenario: React SPA shows deprecation

- **WHEN** a user opens the React SPA
- **THEN** a banner directs them to the streaming `/chat` page
