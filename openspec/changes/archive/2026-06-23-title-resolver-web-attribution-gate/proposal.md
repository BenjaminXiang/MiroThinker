## Why

The paper title resolver's web tier accepts a web-search hit on title-Jaccard
≥ 0.85 alone. `_web_hit_to_resolved` (title_resolver.py:1357) constructs the
candidate with `authors=()` and `year=None` (title_resolver.py:1372-1373), and
the caller accepts any `web_match` whose `match_confidence` clears the 0.85
threshold (title_resolver.py:353). DOI and arxiv_id are extracted only from
`doi.org`/`arxiv.org` hostnames as metadata (title_resolver.py:1382-1387); they
are never validated as an attribution vector. The result is wrong-paper
pollution: a web hit that merely shares enough title tokens passes attribution
even when its authors, year, and identifier are all absent or mismatched. This
is the D2-style attribution gap — a single signal (title) is treated as proof of
identity.

## What Changes

- Add a web-tier attribution gate at title_resolver.py:353. Accept a web-search
  hit only when at least one strong identifier is present **or** the title leg
  is backed by an author-token leg:
  `(doi non-None OR arxiv_id non-None) OR (title Jaccard ≥ 0.85 AND author-token
  Jaccard ≥ 0.3)`.
- Add author extraction to `_web_hit_to_resolved` (title_resolver.py:1357) so
  the web hit carries real `authors` parsed from the hit's snippet/structured
  fields instead of the hard-coded `()`.
- Add an `_author_token_jaccard` helper built on the existing
  `_author_name_tokens` (title_resolver.py:1098) and `_normalize_author_name`
  (title_resolver.py:1105), mirroring the title leg that reuses `_title_jaccard`
  (title_resolver.py:419).
- Fail closed: when the gate rejects, `resolve_paper_by_title` returns `None`
  (title_resolver.py:357). The caller, `homepage_ingest` (homepage_ingest.py:2096),
  already treats `resolved is None` as the page-only fallback
  (homepage_ingest.py:2106-2117), so a rejected web hit falls back to page-only
  synthesis rather than polluting the canonical Paper record.

## Capabilities

### New Capabilities

- `paper-web-attribution-gate`: Defines the attribution gate that the
  title-resolver web tier must pass before a web-search hit is accepted as a
  resolved Paper. The gate is a fail-closed predicate; rejection leaves the
  paper unresolved and triggers the existing page-only fallback.

### Modified Capabilities

- None. The five DB tiers (cache, OpenAlex, Crossref, arXiv, S2) are untouched.
  The 0.85 title-Jaccard threshold for DB tiers is unchanged. No LLM
  verification is introduced.

## Impact

- `apps/miroflow-agent/src/data_agents/paper/title_resolver.py`:
  - title_resolver.py:353 — add the web-tier attribution gate before accepting
    `web_match`.
  - `_web_hit_to_resolved` at title_resolver.py:1357 — add author extraction
    from the hit's snippet/structured fields (replaces the hard-coded
    `authors=()` at title_resolver.py:1372).
  - New `_author_token_jaccard` helper based on `_author_name_tokens`
    (title_resolver.py:1098) and `_normalize_author_name`
    (title_resolver.py:1105); reuses `_title_jaccard` (title_resolver.py:419)
    for the title leg.
- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`: no change.
  The existing `is_page_only = resolved is None` branch
  (homepage_ingest.py:2106-2117) is the fail-closed consumer.

## Non-goals

- Does NOT change the five DB resolution tiers or their 0.85 threshold.
- Does NOT change the 0.85 title-Jaccard threshold used inside `_title_jaccard`.
- Does NOT add LLM-based paper-identity verification (the existing
  `paper_identity_gate` LLM verifier is not reused).
- Does NOT tighten the scholarly-domain whitelist `_is_scholarly_link`
  (title_resolver.py:1350).
- Does NOT change the cache, OpenAlex, Crossref, arXiv, or S2 acceptance paths.
