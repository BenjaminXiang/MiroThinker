## ADDED Requirements

### Requirement: Hybrid RRF SHALL rescue broad-profile entities into the candidate window

The retrieval service SHALL fuse vector-rerank, lexical-coverage, and rerank signals via
reciprocal-rank fusion (RRF) so that entities ranking deep in raw ANN but lexically relevant
(broad-profile market leaders) are rescued into the candidate window via a second signal,
rather than being excluded purely by the ANN candidate-limit cutoff. (Web-search augmentation
is a separate recall lever, owned by the `add-web-augment` change — not this requirement.)

#### Scenario: a broad-profile company is rescued by RRF
- **GIVEN** a company that is `ready`, embedded, and lexically relevant to a topic query but
  ranks ~32 in raw ANN
- **WHEN** the topic query is retrieved with hybrid RRF
- **THEN** the candidate window includes it via the lexical-coverage fusion path, not purely by
  the ANN candidate-limit cutoff

### Requirement: Cross-filter professor queries SHALL reach recall

The classifier SHALL route a professor query combining multiple attributes (origin/graduation
school AND field of focus) to professor semantic recall, not fall through to the `unknown`
refuse path.

#### Scenario: school + field cross-filter query is routed to recall
- **GIVEN** a query like "毕业于早稻田，且在深圳专注在机器人行业的企业家"
- **WHEN** it is classified and routed
- **THEN** it is routed to professor recall (not `unknown`)

### Requirement: Retrieval evidence SHALL be auditable

Every returned candidate SHALL carry its source domain (`object_type`/`type`), identifier, and
a renderable label, so evidence remains source-traceable per the audit invariant (CLAUDE.md §5).
Web-rescued candidates' source-url provenance is owned by the `add-web-augment` change.

#### Scenario: a candidate carries its domain and label
- **GIVEN** a retrieval result rendered to the chat response
- **WHEN** the candidate is emitted
- **THEN** it exposes its `type` (professor/paper/company) and a `label` usable for precision
  labeling

## UNCHANGED Requirements
<!-- A–G routing semantics, _VALID_DOMAINS, _is_indexable_paper, evidence shape, per-domain
     recall mechanics, rerank cascade unchanged; baseline = docs/Agentic-RAG-PRD.md.
     Note: the candidate_limit raise (FM1b original) was eval-NEUTRAL and reverted — NOT a
     requirement here. Web-search augmentation is OUT of this change (see add-web-augment). -->
