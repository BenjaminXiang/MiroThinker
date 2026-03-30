# Design: Reconcile Agentic RAG PRD and Data-Agent PRDs Under a Multi-DB PostgreSQL + Milvus Architecture

**Date:** 2026-03-30
**Status:** Approved for PRD updates
**Scope:** `docs/Agentic-RAG-PRD.md`, `docs/Data-Agent-Shared-Spec.md`, `docs/Company-Data-Agent-PRD.md`, `docs/Professor-Data-Agent-PRD.md`, `docs/Paper-Data-Agent-PRD.md`, new `docs/Patent-Data-Agent-PRD.md`

---

## 1. Problem Statement

The repository currently contains:

- one top-level product PRD for the Shenzhen sci-tech conversational retrieval system
- three existing data-agent PRDs for company, professor, and paper data
- one shared technical spec for the data-agent group

These documents are no longer internally consistent.

The main conflicts are:

1. company data assumptions diverged between old `企名片 API + credit_code` and newer `企名片导出 xlsx + company-name dedupe`
2. the top-level product PRD now targets workbook-aligned answer effects that the data-agent PRDs do not yet fully support
3. the shared spec still assumes a single `PostgreSQL + pgvector` architecture, while the intended long-term system is now multi-database and service-layer aggregation
4. the patent module exists at the product level but has no dedicated Patent-Data-Agent PRD

This design establishes a single reconciliation direction before any PRD edits.

---

## 2. Architecture Decisions

### 2.1 Long-Term Storage Architecture

The unified architecture is:

- **PostgreSQL + Milvus**

This replaces the old shared-spec assumption of a single `PostgreSQL + pgvector` service database.

### 2.2 Multi-DB, Multi-Collection by Domain

The system should be designed for:

- professor data in its own PostgreSQL database and Milvus collection(s)
- company data in its own PostgreSQL database and Milvus collection(s)
- paper data in its own PostgreSQL database and Milvus collection(s)
- patent data in its own PostgreSQL database and Milvus collection(s)

### 2.3 Service Layer Responsibilities

The online service layer is explicitly responsible for:

- query orchestration
- multi-source retrieval
- result fusion
- reranking

The service layer should not assume that all data lives in one relational database.

### 2.4 Contract-Strong, Schema-Loose Rule

Each data-collection agent may maintain its own physical schema as needed.

However, all agents must conform to shared logical contracts:

- stable object identity rules
- required outward-facing fields
- consistent filter semantics
- consistent service-layer query interface meanings

In short:

- **logical contracts must be strongly unified**
- **physical schemas do not need to be identical**

### 2.5 Recommended Storage Independence Rule

The recommended default is:

- each data agent may own its own PostgreSQL database and Milvus collection(s)
- the online service should integrate these domain stores through shared contracts and service adapters
- the PRDs should not require all domains to collapse into one physical relational schema

This is the preferred direction because professor, company, paper, and patent data have materially different:

- source structures
- cleaning rules
- update cadence
- deduplication logic
- summary-generation pipelines

Forcing one physical schema would create artificial coupling and slow down agent evolution without improving answer quality.

### 2.6 Non-Negotiable Shared Contract Layer

Physical independence does not reduce contract discipline.

All domains must still standardize:

- outward-facing object IDs
- main display fields
- evidence / provenance fields
- `last_updated`
- filter semantics exposed to the service layer
- retrieval / rerank input payload shape

In practice, this means the service layer may adapt to different domain schemas internally, but it must not see different meanings for the same contract field.

---

## 3. Cross-System Source and Cost Principles

### 3.1 Primary Collection Principle

For periodic dataset construction, the default strategy is:

- self-built crawlers and deterministic import pipelines first
- Web Search only as an auxiliary capability

This is required for cost control and predictable periodic updates.

### 3.2 Web Search Role

Web Search should be treated as:

- auxiliary discovery
- auxiliary supplementation
- auxiliary validation

It should not be the primary periodic data-ingestion mechanism for any major data domain.

---

## 4. Domain Decisions

### 4.1 Company Domain

#### 4.1.1 Primary Source

The company data backbone is:

- `企名片导出 xlsx`

This is the unified company-source assumption across all documents.

#### 4.1.2 Primary Deduplication Anchor

The primary deduplication anchor should be:

- normalized company name

`credit_code` should be treated as:

- optional supplementary field
- useful for consistency checks when available
- not the primary identifier
- not a required Phase contract field

#### 4.1.3 Secondary Disambiguation Signals

When company-name collisions or ambiguous matches occur, the system may use:

- registered region
- legal representative
- official website
- financing information
- industry / product clues

#### 4.1.4 Required User-Facing Summary Fields

The company pipeline must pre-generate at least:

- `profile_summary`
- `evaluation_summary`
- `technology_route_summary`

These are necessary to support workbook-aligned company answers.

#### 4.1.5 Searchable Key Personnel

`key_personnel` must be upgraded from a display-only field to a searchable structured field.

It should support at least:

- `name`
- `role`
- `education_structured`
- `work_experience`
- `description`

This is required to support queries like entrepreneur education-background filtering.

### 4.2 Professor Domain

#### 4.2.1 Primary Source

Professor data must be grounded in:

- Shenzhen university official websites
- teacher directory pages
- teacher profile pages

This is the primary source of truth for professor identity and affiliation coverage.

#### 4.2.2 Auxiliary Sources

The following remain auxiliary:

- personal homepages
- Google Scholar
- Semantic Scholar
- Web Search

They supplement and validate official-school data, but do not replace university websites as the primary anchor.

#### 4.2.3 Company Association Logic

Professor-company association should no longer depend on `企名片 API` as the primary path.

It should instead be based on:

- company database matching
- official or public web evidence
- auxiliary Web Search when needed

This change must be reflected in the professor PRD, the shared spec, and the Phase 0 → Phase 1 contract.

### 4.3 Paper Domain

#### 4.3.1 Periodic Collection Scope

`Paper-Data-Agent` should periodically collect:

- papers related to Shenzhen university professors

This remains the scope of the periodic paper pipeline.

#### 4.3.2 Explicit Paper Title Queries

Queries for arbitrary explicit paper titles should not force the periodic paper pipeline to become universal.

Instead:

- the online service layer may use real-time external retrieval as fallback for explicit paper-title queries not present in the local paper database

This preserves a bounded periodic collection scope while still meeting product-level answer requirements.

#### 4.3.3 Required User-Facing Summary Fields

The paper pipeline already produces a strong user-facing summary layer.

At minimum it must continue to support:

- `summary_zh`
- `summary_text`

and remain suitable for direct user-facing explanation.

### 4.4 Patent Domain

#### 4.4.1 Dedicated Patent Agent Required

The product-level patent module requires a dedicated:

- `Patent-Data-Agent`

This document does not yet exist and must be added.

#### 4.4.2 Primary Source

The patent backbone should be:

- platform-exported patent `xlsx`

The sample file `docs/2025-12-05 专利.xlsx` demonstrates that a structured xlsx-based ingestion path is feasible.

#### 4.4.3 First-Stage Coverage Rule

The first-stage patent ingestion rule should be:

- import the full exported patent dataset

Do not prematurely restrict the stored scope to only robot or only strongly linked entities at ingest time.

Filtering should happen at query time.

#### 4.4.4 Required User-Facing Summary Fields

The patent pipeline should pre-generate at least:

- readable explanation / summary fields for user-facing patent interpretation
- fields supporting company and professor linkage

---

## 5. Data Product Layering

To keep the roles of collection agents and online service clear, all domains should use the same three-layer field model.

### 5.1 Fact Fields

These store directly collectible or normalizable facts, for example:

- name / title
- institution / company
- filing date
- financing round
- applicant
- patent number

### 5.2 Structured Relation Fields

These store cross-object relationships and filter-ready nested data, for example:

- `company_roles`
- `patent_ids`
- `professor_ids`
- `key_personnel.education_structured`

### 5.3 User-Facing Summary Fields

These are pre-generated by data agents to reduce online answer cost and improve consistency.

At minimum, the reconciled PRDs should support:

- `profile_summary`
- `evaluation_summary`
- `technology_route_summary`
- paper `summary_zh`
- paper `summary_text`

More context-heavy comparisons may still be generated online by the service layer.

---

## 6. Shared Contract Requirements

The shared spec should be rewritten around contracts, not a shared single physical schema.

### 6.1 Required Identity Rules

Each domain must define stable object IDs with domain-distinguishable prefixes, for example:

- `PROF-*`
- `COMP-*`
- `PAPER-*`
- `PAT-*`

### 6.2 Required Outward-Facing Fields

Each domain must expose a minimum outward-facing object contract to the service layer, including:

- `id`
- main display field (`name` or `title`)
- core fact fields
- summary fields
- evidence / source fields
- `last_updated`

### 6.3 Required Filter Semantics

Shared filter meanings must be standardized even if physical columns differ.

Examples:

- `institution`
- `industry`
- `year_range`
- `patent_type`
- key-person education filters

### 6.4 Service Query Interface

The shared spec should no longer model only direct single-database query functions.

It should instead describe service-layer orchestration across domain stores and vector collections.

---

## 7. Required PRD Rewrite Boundaries

### 7.1 `docs/Agentic-RAG-PRD.md`

Keep this document focused on:

- product goals
- user query classes
- answer behavior
- service-layer routing / aggregation / fusion / rerank behavior

Remove hidden assumptions about:

- single-database architecture
- company collection depending on real-time `企名片 API`
- direct coupling to agent internals

### 7.2 `docs/Data-Agent-Shared-Spec.md`

Rewrite this document as the true contract source for:

- `PostgreSQL + Milvus`
- multi-database architecture
- service-layer orchestration
- shared logical field contracts
- Phase handoff contracts

It must stop assuming:

- a single final PostgreSQL service database
- `pgvector` as the long-term vector strategy
- required `credit_code` for company identity

### 7.3 `docs/Company-Data-Agent-PRD.md`

Keep and strengthen:

- xlsx ingestion as the backbone
- company-name dedupe
- structured searchable key personnel
- pre-generated evaluation and technology-route summaries

### 7.4 `docs/Professor-Data-Agent-PRD.md`

Rewrite professor-company linkage logic to remove old `企名片 API` dependence as the main path.

Professor data should be anchored in:

- official Shenzhen university sources first

### 7.5 `docs/Paper-Data-Agent-PRD.md`

Clarify that:

- periodic collection scope is bounded to Shenzhen-university-professor-related papers
- explicit arbitrary paper-title queries may be served online via external fallback

### 7.6 New `docs/Patent-Data-Agent-PRD.md`

Create a full dedicated patent-agent PRD covering:

- source xlsx ingestion
- normalization
- deduplication
- summary generation
- company/professor linkage
- update cadence
- outward-facing contract
- acceptance criteria

---

## 8. Rewrite Order

To avoid document drift during edits, the rewrite should happen in this order:

1. write this reconciliation design
2. update the shared spec
3. update the top-level Agentic RAG PRD
4. update company, professor, and paper agent PRDs
5. add the patent agent PRD

The shared spec must be revised first because it defines the cross-document contract layer.

---

## 9. Out of Scope

This design does not:

- require identical physical schemas across all agent databases
- require all service behavior to be precomputed offline
- require arbitrary paper retrieval to be fully moved into the periodic paper agent
- freeze stale workbook facts into the long-term data contract
