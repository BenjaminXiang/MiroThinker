## ADDED Requirements

### Requirement: Recall candidate window includes deep-but-relevant candidates

The retrieval service SHALL present a candidate window wide enough that the cross-encoder
reranker can rescue relevant rows that rank beyond the top of raw ANN. The default candidate
limit SHALL exceed 30 so ready+embedded rows ranking ~32–50 in raw ANN (e.g. broad-profile
market leaders) reach the reranker before truncation.

#### Scenario: A broad-profile market leader is recallable
- **GIVEN** a company that is `ready`, embedded, and semantically relevant but ranks ~32 in
  raw ANN for a topic query
- **WHEN** the topic query is retrieved
- **THEN** the candidate window includes it (it reaches the reranker); it is no longer
  excluded purely by the candidate-limit cutoff

### Requirement: Cross-filter professor queries reach recall (not refuse)

A professor query combining multiple attributes (e.g. origin/graduation school AND field of
focus) SHALL be classified so it reaches professor semantic recall, not fall through to the
`unknown` refuse path.

#### Scenario: school + field cross-filter query is recalled
- **GIVEN** a query like "毕业于早稻田，且在深圳专注在机器人行业的企业家"
- **WHEN** it is classified and routed
- **THEN** it is routed to professor recall (not `unknown`); relevant professors can be returned

## UNCHANGED Requirements
<!-- baseline retrieval behavior (recall per domain, rerank, A–G routing semantics,
     _VALID_DOMAINS, _is_indexable_paper, evidence shape) is unchanged; see
     docs/Agentic-RAG-PRD.md / docs/Agentic-RAG-Operating-Guide.md for the legacy baseline. -->
