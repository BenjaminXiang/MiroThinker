## ADDED Requirements

### Requirement: Synthesis SHALL be intent-aware (profile / list / qa modes)

The synthesis SHALL select its system prompt by a detected answer-intent:
- `profile` for entity-profile queries (A_*_profile, A_company/paper/patent_profile, single-match G)
  → deep multi-field prose covering all surfaced facts (the rich-facts injection already present).
- `list` for topic/list queries (B_*, C_cross_domain_related, D_*) → bullet-list of objects with
  per-item highlights.
- `qa` for knowledge/conceptual questions (E_knowledge_qa, OR any query matching knowledge
  keywords: 几种/路线/方式/方法/原理/分类/趋势/什么是/区别) → the knowledge-augmented regime
  (REUSES the existing `_KNOWLEDGE_QA_SYSTEM` guard): the LLM MAY use its parametric knowledge for
  general/conceptual content, with every specific entity claim (person/institution/number) grounded
  in cited evidence; conceptual content SHALL be labeled `（综合自 AI 推理，非本地数据库结果）`.

The intent detector SHALL be called in `_build_chat_response` before `_build_evidence_blocks`, so
the evidence-block assembly + the synthesis prompt are both intent-aligned.

#### Scenario: a knowledge question (qid18-class) is answered, not refused
- **GIVEN** a conceptual query like "具身智能厂商在数据方面目前存在几种技术路线" (routed B/unknown,
  not E) with insufficient DB evidence (no data-route taxonomy)
- **WHEN** the intent detector matches knowledge keywords → `qa` mode → synthesis uses
  `_KNOWLEDGE_QA_SYSTEM`
- **THEN** the LLM answers from its knowledge + web evidence, labeled `（综合自 AI 推理…）`; it does
  NOT refuse with "证据不足以回答"

#### Scenario: an entity-profile query stays grounded (no regression)
- **GIVEN** an A_prof_profile query (e.g. "介绍清华的丁文伯")
- **WHEN** intent = `profile` → the deepened profile prompt
- **THEN** the answer is evidence-grounded + `[N]`-cited (unchanged behavior); the rich facts
  (awards/education/work) surface; no LLM-knowledge entity claims

#### Scenario: a list query renders as a bullet list
- **GIVEN** a B_semantic_topic_search query (e.g. "做机器学习的教授有哪些")
- **WHEN** intent = `list` → the list prompt
- **THEN** the answer lists the matched objects with per-item highlights (cited), not a single profile

### Requirement: Entity claims SHALL stay evidence-grounded even in qa mode

Specific entity claims about professors, companies, papers, institutions, numbers, or awards SHALL
be grounded in cited evidence. The LLM MUST NOT invent specific entities that are not in the
evidence. In qa mode the LLM MAY use parametric knowledge only for general conceptual or methodology
content, which SHALL be labeled as AI-inferred and not DB-sourced. The existing citation validator
SHALL still enforce citation markers.

#### Scenario: qa mode does not invent entities
- **GIVEN** a qa-mode answer mentioning a specific company or professor
- **WHEN** the entity is not in the cited evidence
- **THEN** the answer is a precision-oracle violation (forbidden_entities gate) — the prompt forbids
  "编造具体人名/机构/数字" (the existing `_KNOWLEDGE_QA_SYSTEM` rule 2)
