---
name: data-agents-implementation
description: Build the multi-domain data-agent implementation on top of the current MiroThinker runtime with independently verifiable issues and test-gated delivery.
status: backlog
created: 2026-03-30T11:19:22Z
---

# PRD: data-agents-implementation

## Executive Summary

Implement the reconciled company, professor, paper, and patent data agents inside the current `miroflow-agent` codebase. The implementation must reuse the existing MiroThinker orchestration stack, add a structured JSON output mode for data-agent tasks, expose stable cross-domain contracts, and publish release-ready objects for a future `PostgreSQL + Milvus` serving architecture.

The implementation must also use the locally available model and API capabilities already present in this repository during validation and data-cleaning flows:

- `recommended_client_template_mirothinker17_fp8.py` as the preferred high-capability local reasoning / extraction client
- `recommended_client_template_35b_a3b.py` as a lower-cost local fallback client
- `web—search-api.py` as the Serper-style Web Search API example for data discovery and validation

## Problem Statement

The reconciled PRDs are now aligned, but the codebase still lacks:

- a non-`\boxed{}` structured-output mode suitable for record generation
- a shared data-agent contract and runtime layer
- domain implementations for company, professor, paper, and patent data collection
- a release adapter layer that matches the intended `PostgreSQL + Milvus` target architecture

Without these pieces, the product-level PRDs remain descriptive only and cannot be executed as an end-to-end, verifiable implementation roadmap.

## User Stories

### As a data-agent implementer
- I need a sequence of independently verifiable issues so that each change can be validated with targeted tests before the next issue starts.
- Acceptance Criteria:
  - Every issue has a deterministic verification command.
  - No issue depends on “the rest of the system probably working.”

### As a data quality owner
- I need the local MiroThinker-1.7-235B-FP8 and Qwen3.5-35B-A3B endpoints to be usable during validation, extraction, and cleaning so that the data pipeline can run against the locally deployed model stack.
- Acceptance Criteria:
  - Shared adapters exist for the local OpenAI-compatible endpoints.
  - Validation / enrichment tasks specify when to use `mirothinker-1.7-235b-fp8` versus `qwen3.5-35b-a3b`.

### As a future online service layer
- I need stable release objects from each domain so that the service can perform multi-source retrieval, fusion, and rerank without caring about each domain’s internal schema.
- Acceptance Criteria:
  - Every domain produces contract-valid release records with `id`, `object_type`, `display_name`, `core_facts`, `summary_fields`, `evidence`, and `last_updated`.
  - Release adapters can target PostgreSQL and Milvus.

## Functional Requirements

1. Add a structured JSON output mode to the existing `miroflow-agent` runtime without breaking current benchmark-style `\boxed{}` behavior.
2. Build a shared `src/data_agents/` layer with contracts, normalization, evidence, linking, runtime helpers, and local provider adapters.
3. Implement a company data-agent vertical slice using xlsx import, normalized company-name deduplication, structured key personnel, and required summary fields.
4. Implement a professor data-agent vertical slice anchored on Shenzhen university official websites and teacher roster/profile pages.
5. Implement a professor-anchored paper data-agent vertical slice that both publishes paper objects and emits professor enrichment outputs.
6. Implement a patent data-agent vertical slice using exported xlsx as the primary backbone and structured entity linking to company / professor releases.
7. Implement release adapters and validation scripts for `PostgreSQL + Milvus`.
8. Ensure each issue is gated by tests that fail first and pass before the issue can be considered complete.

## Non-Functional Requirements

- All implementation issues must be independently verifiable.
- Parallel implementation is allowed only when file scopes are disjoint and dependencies are satisfied.
- Worktree-based isolation must be used for parallel implementation.
- The local model endpoints and Web Search API examples must be incorporated into validation or cleaning flows rather than ignored.
- Shared-file collisions should be front-loaded into early issues so later domain slices can run in parallel safely.

## Success Criteria

- A CCPM epic exists with a task set that matches the implementation plan and exposes clear dependency edges.
- Every task has deterministic verification commands centered on `uv run pytest`.
- The first two foundational issues unblock true parallel development for later domain slices.
- The implementation path explicitly uses `recommended_client_template_mirothinker17_fp8.py`, `recommended_client_template_35b_a3b.py`, and `web—search-api.py` where appropriate.

## Constraints & Assumptions

- Implementation stays inside the current repository and current runtime.
- Local model endpoints are OpenAI-compatible HTTP APIs.
- `recommended_client_template_mirothinker17_fp8.py` should be preferred for higher-accuracy extraction and validation; `recommended_client_template_35b_a3b.py` is acceptable for cheaper secondary cleaning or fallback paths.
- Web Search is auxiliary, not the primary periodic ingestion backbone.
- Physical domain schemas may diverge internally, but outward release contracts must remain consistent.

## Out of Scope

- WeChat frontend integration
- Online query router implementation
- Production deployment / scheduler setup
- Broad non-Shenzhen expansion
- Any greenfield replacement of the current `miroflow-agent` orchestration runtime

## Dependencies

- `docs/superpowers/plans/2026-03-30-data-agents-implementation.md`
- `docs/Data-Agent-Shared-Spec.md`
- `docs/Company-Data-Agent-PRD.md`
- `docs/Professor-Data-Agent-PRD.md`
- `docs/Paper-Data-Agent-PRD.md`
- `docs/Patent-Data-Agent-PRD.md`
- `recommended_client_template_mirothinker17_fp8.py`
- `recommended_client_template_35b_a3b.py`
- `web—search-api.py`
