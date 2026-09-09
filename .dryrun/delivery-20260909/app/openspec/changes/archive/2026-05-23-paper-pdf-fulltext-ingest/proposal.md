---
change_id: paper-pdf-fulltext-ingest
type: feat (professor-page PDF full-text ingest)
weight: Standard
behavior_change: true
code_change: yes
adds_requirements: true
created: 2026-05-15
canonical_input:
  - docs/Paper-Data-Agent-PRD.md
  - apps/miroflow-agent/src/data_agents/paper/full_text_fetcher.py
  - apps/miroflow-agent/alembic/versions/V011_add_paper_full_text.py
---

# Proposal: paper-pdf-fulltext-ingest

## Why

The paper full-text path exists for arXiv-style PDFs, but professor
pages often link direct PDF files or publication PDFs. Current
collection cannot reliably persist raw PDF bytes by hash, cap fetches,
or attach direct professor-page PDFs to paper canonical rows.

## What Changes

- Discover direct PDF links from professor Publications sections.
- Fetch PDFs with size/time/content-type caps.
- Persist raw PDFs by sha256 or approved blob reference.
- Extract text into `paper_full_text` with source provenance.
- File diagnostic issues for cap violations and unsupported PDFs.

## Non-goals

- No external author-profile discovery.
- No OCR requirement for scanned PDFs in v1.
- No change to paper summary-generation prompt.
