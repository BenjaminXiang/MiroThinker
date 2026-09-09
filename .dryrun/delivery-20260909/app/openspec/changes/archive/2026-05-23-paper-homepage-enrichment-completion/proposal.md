---
change_id: paper-homepage-enrichment-completion
type: feat/refactor (paper page-flow enrichment, status, and vector sync)
weight: Standard
behavior_change: true
code_change: yes
adds_requirements: true
created: 2026-05-15
parent: prof-paper-patent-from-page-flow
canonical_input:
  - openspec/changes/prof-paper-patent-from-page-flow/
  - apps/miroflow-agent/src/data_agents/paper/enrichment.py
  - apps/miroflow-agent/scripts/run_paper_summary_zh_backfill.py
  - apps/miroflow-agent/scripts/run_milvus_backfill.py
---

# Proposal: paper-homepage-enrichment-completion

## Why

The page-first paper flow is partially implemented but still leaves
several completion gaps: tier-specific page evidence is not emitted
literally, arXiv is not part of the enrichment fallback chain,
author/identifier cross-source reconciliation is incomplete, and
`summary_zh` updates are not tied to a deterministic Milvus refresh
contract. These gaps make future recollection hard to trust even if the
current validation rows are discarded.

## What Changes

- Emit the literal `prof_homepage_tier2` / `prof_homepage_tier3`
  evidence source values required by the page-flow spec.
- Complete paper enrichment fallback with arXiv where a supported
  identifier exists.
- Merge author metadata without overwriting stronger source evidence.
- Detect DOI/arXiv/source identifier contradictions and write
  `pipeline_issue` rows.
- Define the `summary_zh` to Milvus refresh contract for rebuild and
  incremental runs.
- Keep external databases as enrichment-only inputs, never discovery
  inputs.

## Non-goals

- No legacy discovery cleanup; that belongs to `paper-pipeline-cleanup`.
- No professor aggregate summaries; that belongs to
  `prof-summary-fields`.
- No raw PDF storage; that belongs to `paper-pdf-fulltext-ingest`.
