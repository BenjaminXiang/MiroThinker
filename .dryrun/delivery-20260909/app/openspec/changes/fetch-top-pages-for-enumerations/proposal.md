# Proposal: fetch-top-pages-for-enumerations

> Phase 5 of Epic `fix-round-1-serving-pipeline` (opened 2026-08-18,
> agent-governed per AGENTS.md §3; scope extended by the user ruling
> 2026-08-18 — iterative research loop, recorded in the Epic change-log).
> Human docs: plan `docs/plans/2026-08-17-systematic-fix-round-1.md` ·
> log `docs/plans/2026-08-17-systematic-fix-round-1-log.md`.
> Behavior-affecting: YES. Capability: `canonical-v2-chat`.

## Why

P8's evidence-acquisition half: enumeration answers grazed listicle content
through search snippets only (the aibangbots case — the reference answer's
10 companies live in one listicle page the system never fetched). Phase 3
made enumerations stable; Phase 5 makes them RICH: fetch the actual pages,
and when round-1 evidence is thin, refine the search once more.

## What Changes

1. **Deep enumeration fetch (5.1)**: enumeration-shaped requests fetch the
   top-8 pages (up from 5), and the snippet window for fetched pages grows
   1200 → 2400 chars so listicle bodies survive the cut.
2. **One refinement round (5.2)**: after round 1, when the request is
   enumeration-shaped and the merged distinct-organization signal is thin
   (< 6 org-looking results), issue ONE refined view set
   （"{query} 榜单/名单/盘点" variants）, fetch its tops, and merge.
3. **Budget guards (5.3)**: total rounds ≤ 2; the refinement round consumes
   no additional wall-clock beyond the lane's existing budget; provider
   searches flow through the Phase 1 quota counters (watermark respected).
4. **Trace visibility (5.4)**: refinement views are ordinary web outcomes
   (view names carry the round-2 queries); no new tokens needed.
5. Out of scope: SSE streaming of in-lane progress (lands with P7/P9
   frontend convergence per the ruling record); LLM gap-judging of round-1
   sufficiency (v1 uses the deterministic org-count signal).

## Impact

- `knowledge_serving_isolated.py` — `_DualWebLaneAdapter.__call__`
  (enumeration detection exists via `_ENUMERATION_QUERY_MARKERS`), fetch
  depth, snippet window, refinement views.
- Tests: adapter-level fakes (providers + page fetcher); replay G7 as the
  RAG-level gate.
