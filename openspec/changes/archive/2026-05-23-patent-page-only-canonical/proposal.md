---
change_id: patent-page-only-canonical
type: feat (page-only patent canonical strategy)
weight: Standard
behavior_change: true
code_change: yes
adds_requirements: true
created: 2026-05-15
parent: prof-paper-patent-from-page-flow
canonical_input:
  - openspec/changes/prof-paper-patent-from-page-flow/
  - apps/miroflow-agent/src/data_agents/patent/homepage_ingest.py
---

# Proposal: patent-page-only-canonical

## Why

Professor pages can list patent titles without patent numbers. The
current patent canonical schema requires `patent_number`, so title-only
page candidates are recorded as data-quality issues instead of
canonical rows. The page-flow spec expected title-only patent
candidates to exist as `needs_enrichment`; that decision needs a
dedicated storage and quality contract.

## What Changes

- Decide and implement the canonical strategy for page-only patents.
- Preserve evidence from professor pages even when patent number is
  absent.
- Define deduplication, quality status, and professor link behavior for
  title-only patents.
- Keep current strict patent-number matching for numbered patents.

## Non-goals

- No patent external enrichment provider.
- No professor patent aggregate summary; that depends on accepted
  patent links and belongs to `prof-summary-fields`.
