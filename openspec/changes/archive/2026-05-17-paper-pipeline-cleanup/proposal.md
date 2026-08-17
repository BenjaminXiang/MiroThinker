---
change_id: paper-pipeline-cleanup
type: refactor (retire legacy paper discovery path)
weight: Standard
behavior_change: true
code_change: yes
adds_requirements: true
created: 2026-05-15
parent: prof-paper-patent-from-page-flow
canonical_input:
  - openspec/changes/prof-paper-patent-from-page-flow/
  - apps/miroflow-agent/src/data_agents/professor/paper_collector.py
  - apps/miroflow-agent/src/data_agents/paper/hybrid.py
  - apps/miroflow-agent/src/data_agents/paper/pipeline.py
---

# Proposal: paper-pipeline-cleanup

## Why

`prof-paper-patent-from-page-flow` changed the discovery rule: papers
are discovered from professor pages, while OpenAlex, Crossref,
Semantic Scholar, and arXiv are enrichment sources only. The codebase
still carries active legacy discovery callers in
`professor.paper_collector`, `paper.hybrid`, `paper.pipeline`, and the
old release E2E script. This keeps a silent path where future work can
reconnect author-name database discovery and bypass the page-first
contract.

## What Changes

- Remove or hard-deprecate legacy paper discovery callers outside tests.
- Convert `professor.paper_collector` to consume page-extracted paper
  candidates or to call no external DB discovery path.
- Keep DOI/metadata enrichment helpers available.
- Add an import/caller guard test so new code cannot import retired
  `discover_*` surfaces.
- Update or remove old release scripts that still advertise hybrid/S2
  discovery as a runnable mainline path.

## Non-goals

- No change to paper canonical schema.
- No professor summary aggregation; that belongs to
  `prof-summary-fields`.
- No PDF full-text ingestion; that belongs to
  `paper-pdf-fulltext-ingest`.
- No change to paper quality-promotion semantics.
