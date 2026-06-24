# Acceptance

## A1 — Gate correctness

- A web hit with `doi is not None` is accepted (identifier path).
- A web hit with `arxiv_id is not None` is accepted (identifier path).
- A web hit with no identifier, title Jaccard >= 0.85, and author-token Jaccard
  >= 0.30 is accepted (title+author path).
- A web hit with no identifier, title Jaccard >= 0.85, and author-token Jaccard
  < 0.30 is rejected.
- A web hit with title Jaccard < 0.85 is rejected.

## A2 — Fail-closed triggers page-only fallback

- When the gate rejects, `resolve_paper_by_title` returns `None` and does not
  cache the candidate.
- `homepage_ingest` observes `is_page_only = resolved is None`
  (homepage_ingest.py:2106) and synthesizes a page-only resolution
  (homepage_ingest.py:2114). No caller change is required.

## A3 — DB tiers unchanged

- The cache, OpenAlex, Crossref, arXiv, and S2 resolution tiers return exactly
  as before. The web-tier gate does not alter their 0.85
  `_CONFIDENCE_THRESHOLD` or their acceptance paths. A regression test confirms
  a DB hit still resolves regardless of the web gate.

## A4 — No LLM in the gate

- The gate is a pure deterministic predicate over DOI, arxiv_id, title Jaccard,
  and author-token Jaccard. No LLM call, no `paper_identity_gate` reuse, no
  confidence boosting is introduced in the rejection path.
