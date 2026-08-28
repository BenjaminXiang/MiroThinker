# Proposal: fix-page-cache-extraction-budget

> P2-A of the P0–P2 campaign. Human docs:
> `docs/plans/2026-08-28-testset-first-principles-review.md` (§五) and the
> G7 essence analysis in the web-lane fix log.

## Why

Enumeration completeness rides on page-fetch outcomes that currently vary
turn to turn: the tiered fetcher re-fetches every URL with no cache (full
TCP+TLS each time, 2s race), and `extract_main_text` caps at 3000 chars
(browser tier 4000) while the enumeration snippet window is 2400 —
leaderboard tails and route wording beyond those budgets never reach the
selector. Strict-ruler failures G2 (missing 开普勒/九号/擎朗), G5 (missing
深南), G11/G12 (missing route words) all trace to this budget chain.

## What Changes

1. `page_fetch.py`: URL→text cache in `create_tiered_page_fetcher` — TTL
   900 s (env `CANONICAL_V2_PAGE_CACHE_TTL`), max 1024 entries, LRU-ish
   eviction, thread-safe. Search-lane results already cache day-scope;
   page text at 15 min keeps freshness while killing intra-session races.
2. `page_fetch.py`: the tiered direct tier fetches with
   `max_chars=8000` (default stays 3000 for other callers);
   `_BROWSER_TEXT_LIMIT` 4000 → 8000.
3. `knowledge_serving_isolated._enrich_with_page_text`: enumeration
   (depth ≥ 5) snippet window 2400 → 6000 so the larger extraction
   actually reaches the selector.

## Impact

- Affected: web lane + probe page enrichment; enumeration answers
  (G2/G5/G7/G11/G12), fused web statistics (P1-B groundwork).
- TTFT: cache hits make repeat turns FASTER; first fetches unchanged.
- Non-goals: selector preference for local canonical entities (G6,
  separate slice), local alias vocabulary (data line), citations (P2-B).
