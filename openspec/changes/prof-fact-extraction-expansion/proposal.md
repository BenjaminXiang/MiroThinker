---
change_id: prof-fact-extraction-expansion
type: feat (professor structured fact extraction and backfill)
weight: Standard
behavior_change: true
code_change: yes
adds_requirements: true
created: 2026-05-14
parent: prof-admin-workbench
canonical_input:
  - openspec/changes/prof-admin-workbench/
  - docs/Data-Agent-Shared-Spec.md
  - docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md
---

# Proposal: prof-fact-extraction-expansion

## Why

The professor canonical schema already permits structured
`professor_fact` rows for `education`, `work_experience`, `award`, and
`academic_position`, but the current collected population only carries
`contact`, `homepage`, and a limited number of `research_topic` facts.
The admin and retrieval surfaces therefore lack the experience fields
needed to judge whether a profile was scraped and cleaned correctly.

After `prof-quality-status-rework`, incomplete but trustworthy rows
will correctly move to `needs_enrichment`. This child reduces that
enrichment gap by extracting facts and factual `profile_summary` values
from existing `profile_raw_text`.

## What Changes

- Add an LLM structured extractor for `education`, `work_experience`,
  `award`, and `academic_position`.
- Write extracted facts into `professor_fact` with provenance,
  evidence spans, confidence, status, and run id.
- Add a preflight that measures the eligible professor set instead of
  assuming counts from join-inflated queries.
- Add a batch runner that performs fact extraction and
  `generate_summaries` over eligible rows.
- Invoke the Child 1 re-evaluation entry point after backfill so
  quality status reflects the new facts.

## Non-goals

- No schema migration. The fact types already exist in the check
  constraint.
- No admin UI. The workbench consumes these facts in
  `prof-admin-workbench-ui`.
- No new quality-status rules beyond calling the Child 1 evaluator.
