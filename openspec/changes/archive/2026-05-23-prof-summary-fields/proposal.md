---
change_id: prof-summary-fields
type: feat (professor paper/patent aggregate summaries)
weight: Standard
behavior_change: true
code_change: yes
adds_requirements: true
created: 2026-05-15
canonical_input:
  - openspec/changes/prof-paper-patent-from-page-flow/
  - docs/Professor-Data-Agent-PRD.md
---

# Proposal: prof-summary-fields

## Why

Professor retrieval needs concise research-output summaries derived
from verified papers and patents. The codebase currently has paper and
patent canonical rows and professor links, but no durable
`professor.paper_summary` or `professor.patent_summary` fields. Without
these fields, later research-vector splitting has no stable text input
for output-based research direction embeddings.

## What Changes

- Add additive professor-level summary fields for aggregated paper and
  patent output.
- Generate summaries only from verified or accepted professor-paper and
  professor-patent links.
- Make the generator deterministic enough for rebuilds and attributable
  by run id.
- Feed changed summaries into the later professor research-vector
  refresh path.

## Non-goals

- No Milvus collection split. That belongs to
  `prof-double-milvus-collection`.
- No page-only patent schema decision. That belongs to
  `patent-page-only-canonical`.
- No professor lifecycle state.
