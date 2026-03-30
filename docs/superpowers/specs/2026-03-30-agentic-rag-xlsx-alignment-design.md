# Design: Align Agentic RAG PRD With Real Query Scenarios in 测试集答案.xlsx

**Date:** 2026-03-30
**Status:** Approved for PRD update
**Scope:** `docs/Agentic-RAG-PRD.md`

---

## 1. Background

`docs/Agentic-RAG-PRD.md` defines the product as a Shenzhen sci-tech conversational retrieval entry point across professor, company, paper, and patent data.

`docs/测试集答案.xlsx` contains 25 real query-and-answer examples that better reflect the desired user-facing behavior. During review, several gaps were identified:

- Some query behaviors in the workbook are not explicitly covered in the PRD.
- Some PRD rules conflict with workbook expectations.
- The PRD is still biased toward abstract module descriptions, while the workbook reflects scenario-level acceptance expectations.

The workbook should be treated as the target effect reference for real query scenarios, but not as a source of permanent factual truth.

---

## 2. Governing Principles

### 2.1 Workbook-As-Scenario-Source

`docs/测试集答案.xlsx` is the primary source for clarifying:

- real user query types
- expected answer depth
- follow-up interaction style
- acceptable answer organization

When the PRD is vague or underspecified, it should be clarified in the direction implied by the workbook.

### 2.2 Facts Override Frozen Samples

The workbook defines target answer effects, not frozen facts.

- The system should aim to match workbook-style coverage and answer form.
- Concrete facts must come from the knowledge base or externally verifiable sources.
- If workbook content becomes stale, the system should return the current verifiable truth instead of copying outdated details.

### 2.3 Product Positioning Remains Focused

The product remains primarily a Shenzhen sci-tech information entry point centered on:

- professors
- companies
- papers
- patents

It does not become a general local-life assistant. However, limited real-scenario exceptions are allowed when they are already represented in the workbook and expected in practice.

---

## 3. Required PRD Alignment Changes

### 3.1 System Boundary Exception for Local Safety Guidance

The current PRD classifies clearly non-sci-tech local-life questions as out of scope and requires refusal.

This rule conflicts with the workbook entry:

- "在深圳旅游旅游有哪些涉及黄赌毒的地方是不能去的"

Updated rule:

- The system may answer a narrow class of Shenzhen local public-safety / travel-risk reminder questions in a concise, polite, safety-oriented way.
- This is an explicit exception, not a broad expansion into general local lifestyle Q&A.
- Clearly unrelated entertainment or idle-chat questions may still be refused.

### 3.2 Ambiguous Entity Handling Should Be Lightweight

The current PRD requires the system to stop and ask for clarification whenever there are multiple high-confidence matches.

This is too heavy for workbook-aligned behavior.

Updated rule:

- For ambiguous entities, the system should default to answering the most relevant / highest-confidence target.
- The answer should start with a short note such as: if you mean another entity, please specify.
- If the user corrects the entity, the conversation should immediately switch to the user-specified target.

### 3.3 Source Display Should Be Conditional

The current PRD requires all answers to visibly show data source and last-updated information.

This does not match workbook answer style.

Updated rule:

- Pure knowledge-base hits do not need explicit source / timestamp text in every answer.
- Answers that rely on Web Search, real-time supplementation, or external fallback should explicitly mention that they include network or real-time information.
- Knowledge-base accuracy is a hard requirement regardless of whether the source is displayed in the answer body.

---

## 4. Query Taxonomy Updates

The existing PRD query taxonomy remains useful, but several categories need clearer behavior definitions.

### 4.1 Type A: Direct Single-Target Queries

Extend Type A to include:

- direct paper-detail lookup by explicit paper title

Behavior:

- Answer directly when the target is explicit.
- Use the local knowledge base first.
- If the local knowledge base misses, external authoritative sources may be used as fallback.

### 4.2 Type B: Result-Set Narrowing and Deepening

Type B should explicitly include not only filtering, but also structured deepening of previous results:

- narrowing the prior result set
- comparing prior entities
- continuing from a technical concept mentioned in the previous answer

Examples from the workbook:

- hotel delivery robot suppliers -> Shenzhen subset -> elevator-capable subset
- company overview -> explanation of a technical concept mentioned in the company answer

### 4.3 Type C: Context-Driven Cross-Object Jumps

Type C should explicitly cover natural jumps between:

- professor -> company
- company -> patent
- paper -> link / method / related entity
- entity -> associated founder / professor / patent / paper

The user should not need to restate the full entity name after it has been established in context.

### 4.4 Type E: Knowledge Explanation and Industry Synthesis

Type E should explicitly include:

- industry route summaries
- method taxonomy explanations
- technical concept expansion from prior turns
- comparative explanation questions

Answers should prefer:

- concise conclusion first
- structured expansion second
- representative companies / methods / platforms where appropriate

### 4.5 Type F: Out-of-Scope Queries

Type F should be narrowed from a hard refusal bucket to:

- still refuse clearly irrelevant or low-value non-product queries
- allow the specific local safety/travel-risk reminder exception noted above

### 4.6 Type G: Ambiguous Queries

Type G should be updated to match the lightweight ambiguity policy:

- answer the most likely target first
- include a short correction invitation
- switch immediately when corrected

---

## 5. Company Module Additions

The workbook reveals that company capability requirements are broader than the current PRD states.

### 5.1 Rich Company Portrait Answers

Company answers should support a combined response containing:

- company overview
- core products and technology direction
- founders / key personnel
- business landing scenarios
- financing / industrial positioning
- related patents / professors / technologies when relevant

This supports questions like:

- company profile + founder info + market evaluation in one answer

### 5.2 Evidence-Based Company Evaluation

The PRD should explicitly allow answering:

- market competitiveness
- market evaluation
- technical strength

Constraint:

- evaluative conclusions must be grounded in enumerated facts such as product capability, financing stage, team background, customers, IP, media / industry reputation, and market position.

Preferred answer style:

- overall judgment first
- supporting evidence second

### 5.3 Company Key-Person Filtering

The company module should explicitly support queries filtering by founder / executive / key-person attributes, including:

- education background
- work background
- current role
- city / Shenzhen scope
- industry or technical direction

This is required to support questions like:

- "毕业于早稻田，且在深圳专注在机器人行业的企业家有谁"

### 5.4 Searchable Key-Person Data Model

To support the above, the PRD should strengthen `key_personnel` as a searchable data structure, not only a display field.

Recommended subfields:

- `name`
- `role`
- `education`
- `work_experience`
- `description`

Structured forms should be supported where possible for:

- education institution / degree / year / field
- work organization / role / start_year / end_year

### 5.5 Company Technology-Route Answers

The company module should support answers about:

- company-level data route / technology route
- cross-company route comparisons
- route explanations grounded in company examples

This is necessary for workbook-aligned embodied-intelligence queries.

---

## 6. Paper and Patent Module Additions

### 6.1 Explicit-Paper Queries by Title

The paper module should explicitly support:

- lookup by exact or near-exact paper title
- local-first retrieval
- external fallback when not present locally

This includes returning:

- basic paper details
- summary
- link / PDF link

### 6.2 Follow-Up After Paper Detail Answer

After a paper detail answer, the system should support further user turns such as:

- asking for the paper link
- asking for the PDF link
- asking for the method
- asking for the contribution

The paper should remain the active context object.

### 6.3 Patent Continuation Chains

The patent module should explicitly support:

- company -> patent list
- patent number -> patent detail

with conversation continuity preserved across turns.

### 6.4 External Fallback Policy

Paper and patent answers should follow this fallback rule:

- local knowledge base first
- external authoritative sources as fallback when needed
- explicit indication when the answer depends on external or real-time supplementation

---

## 7. Cross-Turn Technical Concept Expansion

The workbook shows that users often continue from a concept mentioned in a prior answer instead of asking a fresh entity query.

The PRD should explicitly require:

- recognition of technical concepts mentioned in prior company / paper / patent answers
- preservation of the originating object context
- transition into knowledge-style explanation when the user asks for concept expansion

Examples:

- company answer mentions "光基多维力传感" -> user asks for principle expansion
- paper answer mentions a method -> user asks for more detail on the method

This should be treated as an explicit product capability, not left implicit under generic multi-turn support.

---

## 8. Knowledge-QA Expansion

The embodied-intelligence questions in the workbook require a stronger knowledge-QA definition than the current PRD provides.

### 8.1 Required Coverage

The PRD should explicitly cover at least these knowledge-QA patterns:

- route overview
- method breakdown
- difference comparison
- implementation-path explanation
- representative company / platform / method synthesis

### 8.2 Preferred Answer Form

Workbook-aligned answers should prefer:

- conclusion first
- structured breakdown second
- examples third

rather than returning only hit lists or abstract definitions.

### 8.3 Local + External Evidence Mixing

When relevant local entities exist, the system should prefer using them as examples.

When local coverage is insufficient, external verifiable material may be added.

### 8.4 Style Target

The user-facing style should be:

- direct
- complete
- polite
- naturally organized

and should resemble the workbook's target effect without copying stale facts.

---

## 9. PRD Edit Plan

The PRD update should be a structured rewrite within the same file, not a patchwork of isolated sentence edits.

Recommended edit locations in `docs/Agentic-RAG-PRD.md`:

1. update product boundary section to add workbook-alignment principles and the narrow local-safety exception
2. revise query taxonomy in Section 2 to reflect lightweight ambiguity handling, direct paper-title lookup, concept-expansion follow-ups, and conditional source display
3. expand the company module to include evaluative answers, key-person filtering, and technology-route answers
4. expand the paper module to allow explicit-paper-title lookup and link follow-ups
5. refine the patent and cross-module sections to describe continuous follow-up chains
6. expand knowledge-QA requirements and answer-style expectations
7. revise acceptance criteria to include scenario-level workbook-aligned query chains, not only abstract retrieval metrics

---

## 10. Out of Scope

This design does not:

- freeze workbook facts as permanent truth
- require implementing all new abilities immediately in code
- redefine the product into a broad general assistant
- resolve the separate Company-Data-Agent source migration conflicts outside the Agentic RAG PRD scope
