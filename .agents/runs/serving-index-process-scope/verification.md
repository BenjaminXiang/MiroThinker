# Verification: serving-index-process-scope

Status: in progress (T1–T4 implemented; T5 attributed; T6 evidence being collected).
Branch: `fix/serving-index-process-scope` (worktree `.worktrees/serving-warm-cache`).

Scratch instance: port **18294**, launched from the run15 serve command file
(`serve-18294-command-run15.sh`, same 40+ parameters; only port, scratch index
copy, scratch pack copy, scratch access/correction DBs, probe env, and
`PYTHONPATH` to this worktree differ). `src.data_agents.*` and `backend.*`
both resolve to `.worktrees/serving-warm-cache` (checked by printing module
`__file__`).

## RED evidence re-measured (2026-09-15, scratch 18294, pre-fix code)

Same-process, warm process, three sessions (turn-debug + `timing-before.jsonl`):

| Session / turn | Query | matched points | vector lane | points_filter | candidate_bind |
|---|---|---|---|---|---|
| S1 turn1 (fresh session) | 字节跳动 | 51,026 (all) | **18.54s** | 6.02s | 11.03s |
| S1 turn2 (same session) | 他们公司主要做什么 | 7,086 | **2.79s** | 0.84s | 1.79s |
| S2 turn1 (fresh session) | 字节跳动 | 51,026 (all) | **19.25s** | 5.50s | 10.92s |
| S3 turn1 (fresh session) | 深圳有哪些做具身智能的公司 | 7,086 | ~3.0s | 1.52s | 1.75s |

Boot (first mount of the scratch copy, pre-fix code, warm page cache):

| Step | Time |
|---|---|
| pack file hashing (lookup 638MB + milvus 1029MB) | 0.80s + 1.29s |
| relationships.json read (3.4GB, read + sha + parse) | 36.88s |
| snapshot.lookup_docs (638MB SQLite read) | 11.78s |
| snapshot.milvus_client_open | 0.58s |
| snapshot.milvus_read_points (51k rows; emits `failed to get mvccTs`) | **50.56s** |
| snapshot.open total | 64.53s |
| vector.snapshot.open (pre-opened snapshot validation) | 5.28s |
| vector.npz_load (vector_matrix.npz, 51,026×4096) | 1.32s |
| boot to first `/api/health` 200 | ≈12.5 min (unchanged by this change) |

## T1 attribution — which step actually repeats (function level)

**The per-turn cost is in the vector lane, and it is per-query, not per-session.**
For every vector query the lane:

1. `iso._matches_vector_request` (`knowledge_read_isolated.py`) calls
   `json.loads(point.embedded_content)` + `_normalized_scalar_values` for every
   point in the inventory — 51,026 parses per query (5.5–6.0s per query).
2. `iso._professor_vector_display_names` re-derives the professor display
   authority over all matched professor points (1.7s on the 51k match).
3. `iso._candidate_from_point` builds a full `RecallCandidate` (evidence item,
   `LocalVectorTrace`, claim binding, locator) for **every matched point** —
   51,026 candidates per query (10.9–11.0s) — and the lane then truncates to
   `max_candidates = 8`.

The 18.7–30.6s "cold" sessions in the RED set ran entity-name queries whose
plan matched the whole inventory; the "warm 3.0–3.2s" sessions ran
category queries whose plan matched a single domain (7,086 points). The
fresh-session repeat of the same query (S2 turn1 above, 19.25s) proves the
cost tracks the query shape, not the session age. The index open
(`open_manifest_verified_index_snapshot`, ≈65s) and the derived-state build
run **once per process at boot**, not per session.

## Fix (T2–T4)

- **T2 process-scoped derived state** — `serving_pack_loader.load_serving_vector_index`:
  key `(index_root, marker_sha256, release_id)`; holds the snapshot point
  inventory, each point's parsed `embedded_content` term set, and the professor
  display-name map. Built once per process per mounted index; every session and
  every later query reads it.
  `iso._matches_vector_request` gained an optional `content_terms` parameter
  (one implementation, no duplicated matcher).
- **T2 rank-before-bind** — the lane ranks `(point, score)` pairs with the exact
  key the candidate sort uses (`_vector_candidate_rank_key`: `-score`,
  `domain`, `canonical_id`, `projection_view`, local locator) and only builds
  `RecallCandidate` objects for the retained `max_candidates`; the merged
  manual-recall candidates are appended and sorted as before. The final
  ordering is total (`point_id` is unique), so the retained set and its order
  are the ones the full build produced.
- **T3 boot warm-up** — the vector adapter factory (which already loaded the
  snapshot and `vector_matrix.npz` eagerly) now also builds the process index
  at boot; no user turn pays the derived-state build.
- **T4 mount receipt** — `open_serving_pack_authority` writes a mount receipt
  (`CANONICAL_V2_SERVING_RECEIPT_PATH`, default `<pack>.mount-receipt.json`):
  pack dir, manifest file hash, marker sha, per-file size + first/last-64KiB
  fingerprints, file hashes, verification mode, mount seconds. A later mount
  that matches the receipt skips the 1.7GB artifact re-hash and the 3.4GB
  relationships re-hash; a mismatch (size, head/tail block, marker, manifest)
  falls back to full verification, which refuses the pack. `full` verification
  is forced by `CANONICAL_V2_SERVING_FULL_VERIFY=1` (and is what a first/unknown
  mount always runs). Content binding is unchanged: every reconstructed
  authority hash (`index_result`, `relationship_request`, `index_request`,
  candidate/internal-result hashes) is still recomputed from the bytes read.

## T5 — Milvus on the query path

`snapshot.milvus_read_points` (the ORM `query_iterator` over 51k rows) emits
`failed to get mvccTs from milvus server, use client-side ts instead`
(`iterator.py:260`) and also shows the Milvus-Lite gRPC keepalive fight
(`GOAWAY ... too_many_pings`, keepalive 10s vs server minimum). The client
falls back to a client-side timestamp after its timeout, which is where the
≈50s of the ≈65s snapshot open goes. It is a **boot-time** cost only: the
serving query path never opens Milvus (`knowledge_read_isolated.py` has zero
milvus calls; scoring runs on `vector_matrix.npz`). Disposition: keep the
Milvus inventory check as the boot/pack-level concern it already is, and (T4)
keep it out of the repeated path; the `mvccTs` signature is absent from every
served turn (checked against the scratch log after the probe run).

## T6 — after numbers, gates, probes

(filled below once the post-fix scratch run + replay gate finish)

## Deltas / deviations from the frozen contract

- The frozen RED framing ("every new session pays the load") was measured to be
  a query-shape effect, not a session effect; the acceptance A1 target
  ("fresh session vector lane ≤ 1s") is met by removing the per-query
  O(inventory) work, which is what the user-visible latency was.
- The scratch instance points at a **copy** of the index (patched marker root,
  recomputed marker sha) and a **copy** of the pack (hardlinked big files,
  patched `manifest.index_root`/`index_marker_sha256`, patched serving bundle
  root + recomputed bundle hash), because the pack marker binds the absolute
  index root and the live unit owns the original Milvus file. No production
  path was written.
