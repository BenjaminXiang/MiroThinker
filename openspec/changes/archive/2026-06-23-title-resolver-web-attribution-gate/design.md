## Root cause

Investigated 2026-06-23 in
`apps/miroflow-agent/src/data_agents/paper/title_resolver.py`.

The web tier has no attribution vector. The root cause has three parts:

1. **Empty attribution in the candidate.** `_web_hit_to_resolved`
   (title_resolver.py:1357) builds the `ResolvedPaper` with the hard-coded
   `authors: tuple[str, ...] = ()` and `year = None`
   (title_resolver.py:1372-1373). The hit's snippet and structured fields are
   never parsed for authors, so the candidate carries no author signal.

2. **Pure title-Jaccard acceptance.** The caller accepts any `web_match` whose
   `match_confidence >= _CONFIDENCE_THRESHOLD` (0.85) at title_resolver.py:353.
   `match_confidence` is `_confidence_with_hints(_title_jaccard(...), ...)`
   (title_resolver.py:1374-1380), so acceptance is effectively title Jaccard
   alone — the author/year hints only nudge confidence by up to 0.10 and never
   reject.

3. **Metadata, not validation.** DOI and arxiv_id are extracted only from
   `doi.org`/`arxiv.org` hostnames at title_resolver.py:1382-1387. They are set
   as fields on the candidate but never gated on; a hit with no identifier and a
   wrong author set still passes on title tokens alone.

The combined effect is wrong-paper pollution: a web hit that merely shares
enough title tokens is accepted as the canonical Paper, even when its authors,
year, and identifier are all absent or mismatched. This is the D2-style
attribution gap — a single signal (title) treated as proof of identity.

## Fix

Add a web-tier attribution gate at title_resolver.py:353. The gate is a
fail-closed predicate scoped to the web tier only; the five DB tiers are
untouched.

- **Author extraction.** Extend `_web_hit_to_resolved`
  (title_resolver.py:1357) to extract `authors` from the hit's snippet and any
  structured fields the web_search provider returns, replacing the hard-coded
  `()` at title_resolver.py:1372. Extraction is best-effort and may yield `()`
  when the snippet has no author signal; that is acceptable because the gate
  then requires an identifier or fails closed.
- **Author-token Jaccard helper.** Add `_author_token_jaccard`, built on the
  existing `_author_name_tokens` (title_resolver.py:1098) and
  `_normalize_author_name` (title_resolver.py:1105). It tokenizes the caller's
  `author_hint` and the hit's extracted authors into the same normalized token
  space and returns the Jaccard ratio, mirroring `_title_jaccard`
  (title_resolver.py:419) for the title leg. When either side is empty, return
  0.0 so the author leg cannot pass on a missing signal.
- **Gate predicate.** At title_resolver.py:353, accept `web_match` only when:
  `(web_match.doi is not None OR web_match.arxiv_id is not None) OR
  (_title_jaccard(query_title, web_match.title) >= 0.85 AND
  _author_token_jaccard(author_hint, web_match.authors) >= 0.30)`. The title leg
  reuses `_title_jaccard` (title_resolver.py:419); the 0.85 and 0.30 thresholds
  are the gate's own constants and do not touch the DB tiers' 0.85
  `_CONFIDENCE_THRESHOLD`.

## Fail-closed path

When the gate rejects, `resolve_paper_by_title` returns `None`
(title_resolver.py:357) and does not cache the candidate. The paper remains
unresolved at the resolver layer. The caller, `homepage_ingest`
(homepage_ingest.py:2096), already branches on `is_page_only = resolved is None`
(homepage_ingest.py:2106) and synthesizes a page-only resolution
(homepage_ingest.py:2114). No caller change is required; the fail-closed
behavior rides the existing page-only fallback.

## Risks

- **Noisy author extraction from web snippets.** Web snippets are unstructured
  and may embed author names in prose, lists, or metadata. Extraction will be
  imperfect. The `>= 0.30` author-token Jaccard threshold is deliberately
  lenient: it passes real matches where at least a fraction of author tokens
  overlap, while rejecting wrong-attribution hits whose author sets are
  disjoint. The identifier path (DOI/arxiv_id) is the strong signal and bypasses
  the author leg entirely, so the gate's precision rests primarily on
  identifiers and its recall on the lenient author leg.
- **Recall regression.** Papers that currently resolve via a title-only web hit
  with no identifier and no extractable author signal will now fail closed to
  page-only. This is the intended behavior (those hits were the pollution
  source), but the real-evidence dry-run (task 6) must measure the reject rate
  to confirm the regression is acceptable and not silently breaking a large
  share of legitimate web resolutions.
- **Threshold sensitivity.** The 0.30 author threshold is a starting point. If
  the dry-run shows false rejections of legitimate matches, the threshold may
  need tuning; if it shows false acceptances, it should be raised. The threshold
  is a named constant so it can be adjusted without touching gate logic.

## Open questions

- Should the gate also check year consistency between the hit and the caller's
  `year_hint`? A year mismatch is a strong wrong-paper signal, but `year` is
  currently `None` for web hits (title_resolver.py:1373) and extracting a
  reliable year from a snippet is noisier than extracting authors. Defer until
  the author leg is proven.
- Should the scholarly-domain whitelist `_is_scholarly_link`
  (title_resolver.py:1350) be tightened as a complementary filter? The whitelist
  already prunes non-scholarly hosts before the gate runs; tightening it is
  orthogonal to attribution and is out of scope for W1a.
- Should the identifier path also accept OpenAlex IDs or S2 corpus IDs when
  present in the hit? The current web extraction only handles `doi.org` and
  `arxiv.org` hostnames (title_resolver.py:1382-1387). Extending the identifier
  set is a separate, additive change.
