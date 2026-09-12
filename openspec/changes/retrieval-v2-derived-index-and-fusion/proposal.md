# Proposal: retrieval-v2-derived-index-and-fusion

## Why

The canonical-v2 serving line answers, but its retrieval core carries three
structural deficits measured on the sealed run14 pack (47,071 lookup
documents) and documented in `.agents/runs/close-workbook-gaps/retrieval-review.md`
(§4/§6/§10) and its §11 external reference (zvec-grep, user-shared
2026-09-12):

1. **The lexical channel has no index and no word segmentation.** Every
   request scans documents with whole-string substring matching
   (`knowledge_read_isolated.py:8372`, `query_phrase in term` over each
   document's flattened `content_terms`). Live lane wall: **0.9-3.6s** per
   turn. Its recall ceiling is the reason category queries leak
   off-category names (generalization r5: lidar off-category **25/64**,
   storage **9/56**) — "激光" matches 激光设备 companies that do not make
   laser radar.
2. **Fusion ignores channel quality.** The reranker interleaves local and
   web candidates 1:1 by position
   (`knowledge_serving_isolated.py:2583-2588`) — no rank fusion, no weights;
   channel quality cannot influence order.
3. **The "structured/SQL channel" is nominal.** `StructuredConstraints`
   carries three fields and `geography` has zero consumers; the library's
   typed fields (industry/tech_tags/geography/founded/quality) are flattened
   into text and scanned rather than filtered.

In addition the stack has no page-level fetch cache and no data-freshness
signal (both cheap wins on the same surface).

Measured feasibility (2026-09-12, this repo, real pack + stdlib only):

| probe | result |
|---|---|
| SQLite 3.37.2 FTS5 + `unicode61` + jieba `cut_for_search` both sides, OR query, `bm25()` ranking | 大疆/优必选/PCB打样/顺易捷 all match, ordering sane; trigram tokenizer rejected (2-char terms never match) |
| Entity-name-form user dictionary (AQ-S7 forms; 17,487 entries) | 优必选/则成电子/深南电路 segment as whole words |
| Build cost | 47k docs ≈ **54s** (93% segmentation), FTS index ≈ **62MB** |
| Query cost | ~**1ms** per query (5 queries over 3k docs = 5ms) |

## What Changes

Behavior-affecting; capability `canonical-v2-retrieval` owns the contract.

1. **Derived lexical index (write-time, persisted).** A build step turns the
   sealed pack's lookup documents into a persisted FTS5 index (jieba-segmented,
   field-tiered columns name/tags/body) plus a facet table, written OUTSIDE the
   sealed pack as a derived artifact keyed by release id + pack hash. The
   serving read replaces the substring scan with indexed BM25 retrieval
   behind a switch; candidate construction keeps the existing lineage binding
   (evidence items, citations and integrity assertions unchanged).
2. **Structured filter channel (facets).** Domain/industry/tech_tags/
   geography/founded/quality facets become real SQL predicates feeding
   `StructuredConstraints`.
3. **Rank fusion (RRF).** Replace the 1:1 positional interleave with
   reciprocal-rank fusion (k=60, unweighted first), keeping local/web quota
   semantics as explicit weights and stable tie-breaking.
4. **Page cache + freshness (same surface, small).** URL→text TTL cache for
   the web lane; answers carry a data as-of signal.

## Non-goals

- Not importing `zvec-grep` or `@zvec/zvec` as a component (file/chunk
  retrieval unit, Node/MCP runtime, data re-export; see design.md §"Options").
- Not changing the retrieval unit from typed entities to text chunks; not
  touching Milvus or the embedding model; not re-embedding anything.
- Not touching sealed-pack contents or any historical migration.
- Incremental refresh of the derived index is staged last (full rebuild of
  the derived artifact stays the boring path).

## Impact

- Serving read path (`canonical_v2/knowledge_read_isolated.py`,
  `knowledge_serving_isolated.py`, `serving_pack_loader.py`) behind
  switches; new module + build script; pack release cycle gains one
  idempotent build step.
- Acceptance: retrieval-review §6/§10 targets + generalization P2 + replay
  gate + TTFT, with baselines frozen in the verification contract.
