# Design: add-validated-answer-cache

## Scope

Only a **fresh session's first turn** (`committed is None`, no selection, no
option) is eligible. The query must contain no referent (`他/她/它/这家/该/
其中/上述`) and no time-sensitive marker (`今天/最新/近/目前/本周/今年/新闻/
股价`). The answer must be **local-grounded**: at least one citation type is
professor/paper/patent/company and its id starts with `local-source-` or
`official-source-` (the template lane's enumerated-company id).
Current-web citations may accompany it (the real answers are mixed); a
web-only answer is still excluded.

Web-only answers are excluded because a `WebEntityHandle` id embeds the
originating session id. A cache hit deliberately rehydrates the session with
`prior_web_items=()` and no referent history, so cached web citations are
display-only and cannot become session-scoped handles. Local canonical ids
are pack-scoped and safe to replay.

## Key and invalidation

```
key = sha256(normalized_query)
row = (key, query_text, release_id, data_epoch, payload, validation,
       created_at, expires_at, hit_count)
```

- `release_id` changes whenever the sealed pack changes.
- `data_epoch` hashes `(mtime_ns, size)` of `manual-recall.json` and the
  corrections SQLite file, so an uploaded or reverted document immediately
  misses.
- TTL defaults to 24h (`CANONICAL_V2_ANSWER_CACHE_TTL_SECONDS`).
- `CANONICAL_V2_ANSWER_CACHE=0` disables attach and lookup.

## Write gate (all checks must pass)

1. eligible query (length 2–120, no referent, no time marker);
2. `response_mode == answer`, `render_mode == prose_renderer`;
3. no `fallback_sha256`, no conflicts;
4. citations non-empty, at least one `local-source-*`/`official-source-*`
   citation, and every
   **response** citation id in the response citation map (the cache replays
   the public envelope, not the internal turn result);
5. no protocol marker, no fallback hash, no conflicts;
6. answer length 40–8000 chars.

The gate result is stored with the row; a rejected candidate is logged and
never written.  Current-web citations are allowed alongside the required
local citation (the original all-local rule rejected every real mixed
answer); a web-only answer still fails `local_grounding`.

## Attach point

The serving process is composed by `serve-script/serve_s12e_port.py` →
`complete_candidate_runner`, which mirrors the admin composer and therefore
does **not** call `compose_canonical_v2_consumer_runtime`. The cache is
attached at `backend/main.py`'s single composition choke point (the same place
the turn-trace journal is attached), so both the admin composer and the
pack-mode mirror get it. The composer-level attach is idempotent and remains
as a fallback for non-serving callers.

## Hit path

The adapter checks the cache after `selection` and before the interpreter /
patent-count fast paths. A hit:

1. deserializes `TurnResult`, `ChatResponse`, and `ChatFeedbackCheckpoint`;
2. rebinds `session_id` / `turn_id` (the stored turn ids are from another
   session);
3. emits the `synthesis` stage so the stream UI progresses;
4. commits a `_CommittedSession` with the cached context receipt, displayed
   ids, continuation offer, and checkpoint, using a fresh answer engine from
   `answer_factory` — so follow-ups still resolve against the same local
   universe;
5. returns the cached `ChatResponse`.

A corrupt or schema-incompatible row is treated as a miss and logged.

## Write path

After the normal turn commits, `_store_cached_turn` runs the gate and writes
the payload. Cache I/O failures are logged and never fail the turn.

## Why not cache the HTTP response directly

The chat session keeps `_CommittedSession` state for follow-ups. Returning a
raw HTTP response without rehydrating that state would make the next turn
("其中哪些…") lose the local universe. Rebinding the cached `TurnResult` and
context receipt preserves it.

## Observability

- `logger.info("answer cache skip …")` records the failed gate checks.
- `logger.warning` records corrupt entries and write failures.
- `hit_count` in the sidecar shows which questions are actually hot.
- Access logs keep the normal turn record; the latency column shows the hit.
