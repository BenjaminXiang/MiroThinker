---
name: data-agents-implementation
status: backlog
created: 2026-03-30T11:19:22Z
updated: 2026-03-30T11:19:22Z
progress: 0%
prd: .claude/prds/data-agents-implementation.md
github:
---

# Epic: data-agents-implementation

## Overview

Implement the reconciled data-agent stack in `apps/miroflow-agent` with a strict “test-gated issue” workflow. The epic starts with runtime and shared-layer foundations, then implements domain slices, then finishes with release adapters and a full validation suite.

## Architecture Decisions

- Reuse the current Hydra + `pipeline.py` + `Orchestrator` + MCP-tool runtime instead of introducing a new orchestration layer.
- Add a JSON-first output mode for data-agent tasks while keeping benchmark `\boxed{}` mode intact.
- Centralize shared contracts, local provider adapters, normalization, linking, and dry-run publishing under `apps/miroflow-agent/src/data_agents/`.
- Treat the locally deployed `mirothinker-1.7-235b-fp8` endpoint as the preferred high-capability extraction / validation model.
- Treat the locally deployed `qwen3.5-35b-a3b` endpoint as a lower-cost fallback for secondary cleaning or non-critical extraction.
- Treat the Web Search API example in `web—search-api.py` as an adapter pattern for auxiliary search and source validation.
- Front-load shared-file changes into the first two issues so later domain slices can run in parallel worktrees safely.

## Technical Approach

### Foundation

- Issue 1 adds structured JSON final output to the existing runtime.
- Issue 2 adds shared contracts, local provider adapters, runtime helpers, and dry-run publishing.

### Domain Slices

- Company, professor, and patent slices should be isolated enough to run in parallel after the shared layer lands.
- Paper should start after professor models are stable because it is professor-anchored.

### Release Layer

- Final release adapters target `PostgreSQL + Milvus`, but validation stays fixture-driven and test-first.

## Verification Strategy

Every issue must:

- start with failing tests
- pass deterministic pytest commands before review
- be reviewable without needing another unrelated issue to “probably be done”

An issue is not complete if it only compiles, only runs manually, or depends on broad end-to-end smoke testing without focused assertions.

## Parallelization Strategy

### Sequential Foundation

1. Runtime JSON output mode
2. Shared data-agent contracts and local provider adapters

### First Parallel Wave

- Company slice
- Professor slice
- Patent slice

These can proceed in parallel once Issue 2 is merged because they live in disjoint domain directories plus disjoint config/script files.

### Second Wave

- Paper slice after professor slice

### Final Sequential Integration

- Release adapters and full validation

## Success Criteria (Technical)

- The first two issues eliminate shared-file contention for later domain work.
- Parallel issues can be assigned separate worktrees with disjoint write scopes.
- Each issue has an explicit pytest verification command.
- The local model and Web Search API examples are reflected in technical details and validation strategy.

## Estimated Effort

Estimated total: 38-52 engineering hours across runtime, shared layer, four domain slices, and release validation.

## Tasks Created
- [ ] 001.md - Add structured JSON output mode to the current runtime (parallel: false)
- [ ] 002.md - Add shared data-agent contracts, runtime helpers, and local provider adapters (parallel: false)
- [ ] 003.md - Implement the company data-agent vertical slice (parallel: true)
- [ ] 004.md - Implement the professor data-agent vertical slice (parallel: true)
- [ ] 005.md - Implement the professor-anchored paper data-agent vertical slice (parallel: false)
- [ ] 006.md - Implement the patent data-agent vertical slice (parallel: true)
- [ ] 007.md - Implement PostgreSQL + Milvus release adapters and full validation (parallel: false)

Total tasks: 7
Parallel tasks: 3
Sequential tasks: 4
Estimated total effort: 38-52 hours
