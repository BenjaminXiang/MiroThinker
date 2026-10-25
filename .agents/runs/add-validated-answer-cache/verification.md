# Verification: add-validated-answer-cache

Date: 2026-10-25
Status: **implemented and deployed; live write/hit NOT yet observed.**

## 1. What is in place

- `backend/services/canonical_v2_answer_cache.py`: SQLite store,
  exact-query key, release/epoch/TTL checks, hit counter, purge.
- Write gate: local-only citations, citation-map resolution, no marker, no
  member wall, no fallback, no conflicts, 40–1200 chars, no referent or
  time-sensitive query.
- Adapter: `attach_answer_cache`, hit path before retrieval, session
  rehydration (context receipt, displayed ids, checkpoint), store after commit.
- Attach point: `backend/main.py`'s single composition choke point, because
  the serving runner (`s12a/complete_candidate_runner.py`) mirrors the admin
  composer and does not call `compose_canonical_v2_consumer_runtime`.
- `run.sh`: `CANONICAL_V2_ANSWER_CACHE=1`,
  `CANONICAL_V2_ANSWER_CACHE_DB=$B/var/answer-cache.sqlite3`.

## 2. Unit evidence

`apps/admin-console/tests/test_canonical_v2_answer_cache.py`: **9 passed**
(web citation rejected, marker/member wall rejected, citation-map index→id
accepted, release/epoch miss, TTL purge, referent/time query rejected).

## 3. Live probe (2026-10-25 23:20 CST)

- Service healthy; `var/answer-cache.sqlite3` exists (12KB, table created).
- `answer_cache` rows: **0**.
- `丁文伯创办的公司是哪家`:
  - session A first: 155.36s (cold), 1 local company citation.
  - session B second: 2.72s, answer **not identical** to A → not a cache hit.
- Follow-up in session B `它有哪些专利`: answered a **wrong patent**
  (`内窥镜光学系统和内窥镜`, 深圳康诺思腾) instead of resolving the company
  context. This is a live context/referent defect, independent of the cache
  gate; it must be fixed before claiming the section is clean.
- `严格验收机器人公司是做什么的？`: 4.60s, no local 普渡 citation; the answer
  says no matching company and offers a web near-name (哈工大机器人HRG /
  严格集团) with a disclaimer. The local substitution is fixed; the web
  near-name suggestion remains.

## 4. Blocker

The store gate did not write a row for a response that looks eligible
(`llm_synthesized`, 1 local company citation, citation_map `{"1": id}`,
141 chars, degradation none). The likely rejection is one of the
unobservable TurnResult fields (`render_mode`, `response_mode`,
`fallback_sha256`, `conflicts`), or the serving adapter is not the instance
that owns the attached cache. The next step is a warning-level log of the
`validate_candidate` checks in `_store_cached_turn` and one restart; if
`conflicts` is the only failure, decide whether relationship answers may
cache with conflicts present.

## 5. Not claimed

- Cache hit latency, hit ratio, session rehydration after a hit, and
  invalidation on a real upload are **not** live-verified.
- The cache is enabled in `run.sh` but writes 0 rows today; treat it as
  dormant until the blocker is fixed.

## 6. Update 2026-10-26: gate fixed, live hits observed

**Root cause of the 0-row blocker** (from `answer cache skip` logs):

- `local_only=False`: the old gate required *every* citation to be
  `local-source-*`; real answers mix local and current-web citations.
- `citation_map=False`: the old gate compared `TurnResult.citations` with the
  HTTP envelope's map, which only contains public citations.
- `length=False`: the 1200-char cap rejected normal 1–3k answers.

**Gate now validates the envelope that will be replayed**:

- `citations` from `ChatResponse`, at least one
  `local-source-*` / `official-source-*` citation (`local_grounding`);
- `citation_map` from the same envelope;
- `answer_text` from the envelope;
- length 40–8000; member-wall check removed (bounded coverage tail is normal);
- protocol markers now include `<|end_of_answer|>` and the rest of the
  chat-template terminator family.

**Live evidence (customer 18188, 2026-10-26 01:01–01:10 CST)**:

- `answer_cache` rows: **6**, all with `local_grounding=true`,
  `citation_map=true`, `no_marker=true`.
- `介绍清华的丁文伯`: first call **4.42s** (miss, row written),
  identical second call **0.06s** (hit, `hit_count` 1→3).
- `优必选有哪些专利`: warmup wrote the row; two identical calls **0.16s /
  0.08s**, `hit_count=2`.
- `优必选科技有哪些专利`: first call 13.11s (row written), mixed
  local+web citations accepted.
- Cache hit + cookie-bound follow-up:
  `介绍清华的丁文伯` → `他的研究方向有哪些？` answered in **5.96s**
  with one local citation (context receipt + displayed ids rehydrated).
- A non-cookie probe produced a false negative: `/api/chat` binds sessions
  by the `miroflow_chat_session` cookie, not the JSON `session_id`; the
  follow-up in a new cookie jar is a fresh session.  Re-tested with a cookie
  jar: binding works.

**Still open**: `official-source-*` was accepted only after the last patch;
the lidar enumeration cold→hit probe is re-run after the restart.  The
pre-existing patent-list follow-up (`这些专利…`) still clarifies even without
a cache; it is a referent-resolution defect, not a cache regression.

**2026-10-26 01:20 update — official-source prefix + cold→hit**:

- `_LOCAL_CITATION_PREFIXES = ("local-source-", "official-source-")`:
  enumerated-company answers use `official-source-*`, so the first version
  still rejected the lidar list.
- `深圳有哪些做激光雷达的公司`:
  - first prose call **89.23s** (cold; the answer that wrote the row),
  - second prose call **13.51s** (miss while the first was a template
    variant; the prose variant then wrote the row),
  - next two fresh calls **0.08s / 0.09s** (hits, 15 local company citations).
- Follow-up after the lidar hit (`这些公司主要做哪类产品？`) answered in
  **6.82s** with 7 citations, so the cached session bound the displayed
  company set.
- Cache rows at this point: **7**; all validation receipts have
  `local_grounding=true`, `citation_map=true`.

## 7. Deployed artifacts (2026-10-26)

Customer bundle `/root/deploy/fullstack-v2/code`:

| file | md5 |
|---|---|
| `apps/admin-console/backend/services/canonical_v2_answer_cache.py` | `555784e587fa5a2316b4e04dc35201ef` |
| `apps/admin-console/backend/services/canonical_v2_chat.py` | `ce8afcf405ee68ecb00c37fcdb42befe` |
| `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` | `9b507137ef1c1ac0bbb60f666b83b4a2` |

The unified diff against the pre-change backups is saved at
`.agents/runs/add-validated-answer-cache/patches/customer-20261026.diff`
(174 lines, 60 added lines).  The customer bundle remains the deploy source;
the local checkout does not yet carry these three files in identical form.
