# Change Log

## 2026-06-23

- Proposed `title-resolver-web-attribution-gate` (W1a). Grounded by
  investigation of `title_resolver.py` web tier on 2026-06-23: the web tier
  accepts on title-Jaccard >= 0.85 alone (title_resolver.py:353) with
  `authors=()`/`year=None` in the candidate (title_resolver.py:1372-1373) and
  DOI/arxiv_id extracted only as ungated metadata
  (title_resolver.py:1382-1387). The change adds a fail-closed web-tier
  attribution gate `(doi OR arxiv_id) OR (title Jaccard >= 0.85 AND author-token
  Jaccard >= 0.30)` with author extraction and an `_author_token_jaccard`
  helper, returning `None` on rejection so `homepage_ingest` falls back to
  page-only synthesis (homepage_ingest.py:2106-2117). Phase 3 prerequisite;
  unblocks W2a (abstract-web-reader-fallback).
