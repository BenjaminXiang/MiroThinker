## ADDED Requirements

### Requirement: Canonical quality_status enum

The system SHALL maintain one canonical `quality_status` enum across all four
domains with exactly the values
`{ready, needs_review, low_confidence, needs_enrichment, partial, rejected}`
(matching `data_agents/contracts.py::QualityStatus`). Legacy values
(`incomplete`, `shallow_summary`) SHALL be normalized to `needs_review` via the
existing `QUALITY_STATUS_CANONICAL_MAP`.

#### Scenario: Legacy status is normalized
- **GIVEN** a row carries a legacy `quality_status='incomplete'`
- **WHEN** it is written through any canonical writer
- **THEN** the persisted `quality_status` is `needs_review`

### Requirement: Forward-monotonic promotion

Promotion SHALL be forward-monotonic: once a row's `quality_status` is `ready`,
no automated gate SHALL degrade it; degrading a `ready` row SHALL require an
explicit admin action. Automated gates SHALL only promote upward or hold.
`rejected` is terminal.

#### Scenario: A ready row is not auto-degraded
- **GIVEN** a paper row with `quality_status='ready'`
- **WHEN** a re-ingest write-path gate re-evaluates it and it still meets
  `ready` criteria
- **THEN** `quality_status` remains `ready`

#### Scenario: Ready cannot be auto-lowered
- **GIVEN** a row with `quality_status='ready'` that no longer meets `ready`
  criteria, with no admin action
- **WHEN** the write-path gate re-evaluates it
- **THEN** `quality_status` remains `ready`

### Requirement: Paper write-path uses the promotion state machine

The paper canonical writer SHALL compute `quality_status` by calling
`paper/quality_promotion.py::evaluate_paper_promotion`. It SHALL NOT assign
`quality_status` via an inline SQL `CASE` or any ad-hoc expression. The
existing inline `CASE` in `paper/canonical_writer.py` SHALL be removed.

#### Scenario: A ready-worthy paper is promoted at write time
- **GIVEN** a paper being upserted that has title + year + venue + authors +
  abstract + non-boilerplate `summary_zh`
- **WHEN** the paper canonical writer computes `quality_status`
- **THEN** it calls `evaluate_paper_promotion` and the row is `ready`
- **AND** no inline `CASE` participates in the assignment

### Requirement: Retrieval-readiness invariant and rebackfill coupling

The set of rows indexable by Milvus SHALL equal the set of rows the write-time
gate promotes to `ready`, subject only to the per-domain identity/merge
exclusions. The Milvus indexability filters (`_is_indexable_*`) are the
retrieval-readiness consumer and SHALL key on `quality_status` (and, for paper,
`identity_status`). A write-path transition of a row into or out of `ready`
SHALL be followed by a Milvus rebackfill so the transition is reflected in
retrieval. No second, independent readiness signal SHALL exist.

#### Scenario: A newly-ready paper becomes retrievable after rebackfill
- **GIVEN** one of the 66 ready-worthy papers previously stuck at
  `needs_enrichment` under the bypassed-gate path
- **WHEN** the write-path gate promotes it to `ready`
- **AND** a Milvus rebackfill runs
- **THEN** the paper is present in `paper_chunks` and retrievable via the
  retrieval service

#### Scenario: No second readiness signal
- **GIVEN** two rows with identical `quality_status` and `identity_status`
- **WHEN** Milvus indexability is evaluated
- **THEN** both receive the same verdict — no parallel "indexed" flag disagrees
  with `quality_status`

### Requirement: Batch promotion delegates to the write-time gates

The batch module `quality/promotion_rules.py` SHALL compute `quality_status` by
delegating to the per-domain state machines (not re-computing independently),
and SHALL include `evaluate_patent` so all four domains are covered. For any
given row, the batch path and the write path SHALL produce the same
`quality_status`.

#### Scenario: Batch and write agree
- **GIVEN** a paper row
- **WHEN** its `quality_status` is computed by the write path and separately by
  the batch `run_quality_promote.py` path
- **THEN** both paths return the same value

#### Scenario: Patent is covered by the batch system
- **GIVEN** a patent row
- **WHEN** the batch promotion module runs
- **THEN** `evaluate_patent` is invoked (patent is no longer absent from the
  batch system)
