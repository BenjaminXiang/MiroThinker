# paper-web-attribution-gate Specification

## Purpose
TBD - created by archiving change title-resolver-web-attribution-gate. Update Purpose after archive.
## Requirements
### Requirement: Web-tier attribution gate

The title resolver MUST accept a `web_search` result as a resolved Paper only
when the hit passes the web-tier attribution gate. The gate SHALL accept the hit
when at least one strong identifier is present **or** the title leg is backed by
an author-token leg:

`(doi is not None OR arxiv_id is not None) OR (title Jaccard >= 0.85 AND
author-token Jaccard >= 0.30)`.

The title leg MUST reuse `_title_jaccard` (title_resolver.py:419). The
author-token leg MUST reuse `_author_name_tokens` (title_resolver.py:1098) and
`_normalize_author_name` (title_resolver.py:1105) through a new
`_author_token_jaccard` helper. The gate MUST apply only to the web tier at
title_resolver.py:353 and MUST NOT alter the five DB resolution tiers (cache,
OpenAlex, Crossref, arXiv, S2) or their 0.85 threshold.

#### Scenario: Web hit with a DOI is accepted

- **WHEN** a `web_search` hit produces a `ResolvedPaper` with `doi is not None`
  (for example a `doi.org` link at title_resolver.py:1384)
- **THEN** the gate SHALL accept the hit regardless of the author-token Jaccard
- **AND** `resolve_paper_by_title` SHALL cache and return the resolved Paper
  (title_resolver.py:354-356)

#### Scenario: Web hit with an arxiv_id is accepted

- **WHEN** a `web_search` hit produces a `ResolvedPaper` with `arxiv_id is not
  None` (for example an `arxiv.org` link at title_resolver.py:1386)
- **THEN** the gate SHALL accept the hit regardless of the author-token Jaccard
- **AND** `resolve_paper_by_title` SHALL cache and return the resolved Paper

#### Scenario: Web hit with title and author agreement is accepted

- **WHEN** a `web_search` hit has no DOI and no arxiv_id
- **AND** the title Jaccard against the query title is >= 0.85
- **AND** the author-token Jaccard between the hit's extracted authors and the
  caller's author hint is >= 0.30
- **THEN** the gate SHALL accept the hit
- **AND** `resolve_paper_by_title` SHALL cache and return the resolved Paper

#### Scenario: Web hit with title match but no identifier and author mismatch is rejected

- **WHEN** a `web_search` hit has no DOI and no arxiv_id
- **AND** the title Jaccard is >= 0.85
- **AND** the author-token Jaccard is < 0.30
- **THEN** the gate SHALL reject the hit
- **AND** `resolve_paper_by_title` SHALL return `None` (title_resolver.py:357)
- **AND** the rejected hit MUST NOT be cached

#### Scenario: Web hit with a low title Jaccard is rejected

- **WHEN** a `web_search` hit has a title Jaccard < 0.85
- **THEN** the gate SHALL reject the hit even when an author-token Jaccard is
  available
- **AND** `resolve_paper_by_title` SHALL return `None`

### Requirement: Fail-closed rejection triggers page-only fallback

When the web-tier attribution gate rejects a hit, `resolve_paper_by_title` MUST
return `None` and MUST NOT cache or return the rejected candidate. The paper
remains unresolved at the resolver layer, and the caller MUST fall back to
page-only synthesis. No LLM verification, no partial confidence boosting, and no
silent acceptance is permitted in the rejection path.

#### Scenario: Rejected web hit falls back to page-only synthesis

- **WHEN** the web-tier attribution gate rejects the best `web_search` hit
- **THEN** `resolve_paper_by_title` SHALL return `None`
- **AND** `homepage_ingest` SHALL observe `is_page_only = resolved is None`
  (homepage_ingest.py:2106)
- **AND** the caller SHALL synthesize a page-only resolution
  (homepage_ingest.py:2114) instead of recording the rejected web hit as a
  canonical Paper

