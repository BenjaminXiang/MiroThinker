---
change_id: prof-double-milvus-collection
type: feat (split professor identity and research vector indexes)
weight: Standard
behavior_change: true
code_change: yes
adds_requirements: true
created: 2026-05-15
depends_on:
  - prof-summary-fields
canonical_input:
  - apps/miroflow-agent/src/data_agents/professor/vectorizer.py
  - apps/miroflow-agent/src/data_agents/storage/milvus_collections.py
---

# Proposal: prof-double-milvus-collection

## Why

The current professor vector index mixes identity fields and research
signals in a single embedding. Identity lookup and research-direction
search have different text inputs and ranking expectations. Keeping one
collection causes research queries to be diluted by name, institution,
department, title, and contact fields.

## What Changes

- Split professor embeddings into identity and research collections.
- Build identity vectors from stable identity/contact/affiliation text.
- Build research vectors from research directions, profile summary,
  paper summary, and patent summary.
- Route retrieval to the correct collection by query intent.
- Provide backfill and rollback steps for both collections.

## Non-goals

- No generation of `paper_summary` or `patent_summary`; this depends on
  `prof-summary-fields`.
- No expansion of online RAG domains beyond professor/paper.
