# Design: synthesis-depth-min (slice ①min)

## Drop points (confirmed on the live line, 2026-10-16)

All three live in the sealed pack file
`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`,
so the slice shares the 片② reseal window (manifest-only reseal, `reseal_manifest.py`).

### DP1 — Web window gate (the binding one for the reported case)

`_proposal_provider`, ~line 865:

```python
enumeration_window_widened = local_scope_foothold and (
    (request.enumeration_context is not None and request.enumeration_context.requested)
    or any(marker in request.original_query for marker in _ENUMERATION_QUERY_MARKERS)
)
...
max_web_results=(
    max(bundle.max_web_results, _ENUMERATION_CANDIDATE_WINDOW)
    if enumeration_window_widened
    else bundle.max_web_results          # 8 — the Web-only concept case lands here
),
```

A Web-only turn has `local_scope_foothold=False` by construction, so a list-shaped
concept question keeps an 8-wide Web window while its own rewrite views hold
material at ranks 11+.

**Change**: add a Web-only branch that widens `max_web_results` to
`bundle.max_candidates + bundle.max_web_results` (16 today — "keep what the lane
can already gather"), keeping `max_candidates` and the local path untouched.
Kill switch `CANONICAL_V2_WEB_WIDE_WINDOW` (default on; `0/false/off/no` disables),
read per call so tests can flip it in-process (same idiom as
`CANONICAL_V2_ALIAS_FOOTHOLD`).

**Marker set (decided during implementation)**: the branch reuses the rewrite
gate's marker set (`_QUERY_REWRITE_ENUMERATION_MARKERS` — 哪些/推荐/分别/几种/多少/
列出/所有), **not** the planning set (`_ENUMERATION_QUERY_MARKERS`, which also
contains the bare question word 谁). A "X 是谁" turn is not list-shaped and must
keep the bundle window; the first test run caught exactly that with the negative
control 「世界上最美丽的女人是谁」.

### DP2 — Web query-rewrite views (the depth enabler)

`_QUERY_REWRITE_SYSTEM_PROMPT` (~line 2058) asks only for 简短的中文关键词式 queries.
Measured: the Chinese views yield 4/12 + 4/11 relevant; an English full-name query
yields **11/11**. One clause is added: when the subject is an abbreviation or a
technical term, one query may be its English full name / English keywords.

Gate unchanged (`_should_rewrite_serving_query`: enumeration markers, multi-intent,
attribute questions, topic-without-named-subject) — the clause changes what the
model returns, not when the rewriter runs. Failure semantics unchanged (any error
→ no rewrite views → deterministic view only).

### DP3 — Merge order (contingency, TRIGGERED and implemented)

`_merge_web_results_across_views` concatenates views in order, so the
question-shaped deterministic view's head owns the window. T7's first scratch run
showed DP1 alone is not enough: the lane held 45+ results across four views
(including the English view's arXiv material) while the kept list was **10 items,
all from view 1, 0 relevant** — the rewrite views' material sat past the window
in merge order. So the declared contingency was implemented in the same slice:

- `_merge_web_results_across_views(..., per_view_head=N)` — a view may contribute
  at most N results before the next view gets its turn (the discovery path's
  existing `plain_head_limit` idiom, applied here to the plain merge).
- The lane computes `per_view_head = max(4, web_window // len(views))` for
  list-shaped turns under the same kill switch. Web-only list turns (window 16,
  4 views) → 4 per view, so all four views land inside the window; local
  enumeration turns (window 128) → the slice (≥ 32) exceeds what any view
  returns, so the cap is a no-op there and the tuned enumeration merge is
  untouched.
- One shared predicate `_web_list_shaped(text)` now serves both consumers (the
  plan's window branch and the lane's merge cap).

### Explicitly not touched

- The answer renderer prompt (既有的「按行业常见分类分条组织答案」 stays).
- `max_candidates`, `_ENUMERATION_CANDIDATE_WINDOW`, local lanes, provider order.
- Any parametric-knowledge policy.

## Verification path (contract in `.agents/runs/synthesis-depth-min/`)

1. RED (already captured): the live-line transcript + provider probe table.
2. Unit: window-gate matrix (Web-only list → wide; Web-only non-list → 8; local
   list → 128; kill switch off → 8) + rewrite-prompt clause presence.
3. In-process probe: the rewriter returns an English/full-name view for the JEPA
   question with the new prompt (the rewriter is directly callable — cheap loop).
4. Scratch E2E (a copy of the live stack, own port): before/after ask of the
   reported question + the short form + 优必选 + 深圳具身 + the negative control;
   replay gate; recall gate; TTFT.
5. Dual-line cutover with the 片② machinery (reseal → dogfood → dev line → site),
   rollback assets kept.
