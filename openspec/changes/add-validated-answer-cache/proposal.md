# Proposal: add-validated-answer-cache

Human docs: `docs/plans/2026-10-25-validated-answer-cache.md`;
`docs/plans/2026-10-26-testset-alignment-and-manual-knowledge-log.md`.

## Why

TTFT is dominated by the retrieval lanes plus the prose LLM call (10–20s on
the customer site). The same high-frequency questions arrive repeatedly —
demo questions, customer onboarding questions, and the operations team's
regression probes. Serving a previously validated answer for an identical,
context-free question removes both costs.

The risk is obvious: a stale or wrongly grounded answer would be served fast
and confidently. The cache therefore needs a validation gate before write, a
release/pack/epoch check before read, and a strict scope that excludes
anything context-dependent.

## What Changes

1. New sidecar `var/answer-cache.sqlite3` (WAL) keyed by
   `sha256(normalized_query) + release_id + pack_sha + data_epoch`.
2. Cache only **fresh, standalone, local-grounded** turns:
   - `committed is None`, no selection, no option, no referent/pronoun;
   - no time-sensitive marker (今天/最新/近/目前/现在/本周/今年/新闻/股价…);
   - at least one citation is pack-local (`company`/`professor`/`paper`/
     `patent` with a `local-source-*`/`official-source-*` id). Current-web
     citations may accompany
     it, but a web-only answer is never cached.
3. Validation gate before write:
   - `response_mode == "answer"`, `render_mode == "prose_renderer"`;
   - validate the **HTTP envelope the cache will replay**: citations
     non-empty, at least one local citation, every response citation id
     present in the response citation map;
   - no protocol marker, no fallback hash, no conflicts, answer length
     within 40–8000 chars (real answers are routinely 1–3k);
   - the validation receipt is stored with the entry.
4. Read-side checks: TTL (24h default), release/pack identity, and a data
   epoch derived from the manual-recall file and corrections database stat;
   any change misses.
5. A cache hit rehydrates the session from the stored context receipt,
   displayed ids, and checkpoint, so follow-up turns ("其中哪些…") still
   resolve against the same local universe.
6. Kill switch `CANONICAL_V2_ANSWER_CACHE=0`, TTL env, and hit/miss counters
   in the access log.

## Impact

- A hit returns the cached `ChatResponse` and commits a session equivalent to
  the original turn; no retrieval and no LLM call.
- A miss is byte-identical to today's path.
- The cache never stores web-only answers; a hit rehydrates the session with
  an empty web-item list, so session-scoped web handle ids cannot leak across
  sessions.
- Manual-recall uploads/corrections invalidate via the epoch; release/pack
  changes invalidate via the key.

## Non-goals

- Semantic/fuzzy caching; only the normalized exact query is a key.
- Caching multi-turn, referential, or web-only turns.
- A cache admin UI in this slice (purge is a CLI/env operation); stats are
  logged.
