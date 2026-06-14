# Design: prof-double-milvus-collection

## Scope

Create two professor collections:

- `professor_identity_profiles`
- `professor_research_profiles`

The old `professor_profiles` collection can remain during migration but
must not be the only retrieval path after this change verifies.

## Embedding inputs

Identity input:

- canonical name and English name;
- institution, department, title;
- email/homepage where available;
- official source labels.

Research input:

- active `research_topic` facts;
- `profile_summary`;
- `paper_summary`;
- `patent_summary`;
- selected academic metrics only if already present and textualized
  without dominating the semantic content.

## Retrieval routing

Identity-style queries route to identity collection. Research-topic,
expert-finding, and capability queries route to research collection.
Ambiguous queries may query both and fuse results with source labels
preserved.

## Backfill

The backfill can run both collections or a selected collection. It must
report counts, skipped rows, and rows lacking required input text.

## Rollback

Keep the old collection until verification passes. Rollback switches
retrieval config to the old collection and drops or ignores the new
collections.
