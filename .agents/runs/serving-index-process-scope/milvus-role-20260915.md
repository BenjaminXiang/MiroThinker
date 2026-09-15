# Milvus in serving: role and the 60s open stall (code-level attribution, 2026-09-15)

Change: `serving-index-process-scope` (input for T5). Method: read-only code trace
in the serving-line worktree (`codex/canonical-v2-s12a-ready`, HEAD `10dd2bd1`) +
git history + pymilvus source. No process was disturbed.

## Facts (file:line)

1. **Serving scores locally, by design.** `write_persisted_vector_matrix`
   (`index_projection_isolated.py:615-668`) docstring: the build embeds every
   point once and also persists `vector_matrix.npz` so the serving process loads
   the scoring matrix at boot "instead of re-embedding all ~6k points on the
   first vector request (~77s cold spike)". Introduced by perf commit
   `3336aabe` (2026-08-03): "Scoring is float64-identical to the previous path."
2. **Zero milvus references in the serving read/serve modules**:
   `knowledge_read_isolated.py` 0, `knowledge_serving_isolated.py` 0. Nonzero only
   in build (`knowledge_build_isolated.py`), verification/loader
   (`serving_pack_loader.py`, `index_projection_isolated.py`), admin status
   (`canonical_v2_admin_status.py`), jobs and build-side adapters.
3. **The pack still carries Milvus as a first-class artifact**:
   `serving_pack_loader.py:131` `PACK_INDEX_FILENAMES = ("lookup.sqlite3",
   "milvus.db")`; boot opens the index at `:642` via
   `open_manifest_verified_index_snapshot`.
4. **The open reads every Milvus point row**:
   `_read_all_points_with_client` (`index_projection_isolated.py:826-860`) using
   `client.query_iterator(batch_size=128, output_fields=[point_id, release_id,
   projection_id, canonical_object_id, embedded_content_sha256, point_json,
   vector])`.
5. **The 60s stall is a pymilvus iterator artifact, not Milvus search**:
   `pymilvus/orm/iterator.py:243-260` `__setup_ts_by_request` queries the server
   for an mvccTs; Milvus Lite (embedded) returns none → warning "failed to get
   mvccTs from milvus server, use client-side ts instead" after a 60s-class
   timeout → falls back to client-side ts. The sibling read path
   `_read_points_with_client` (`:791-823`) uses `client.get(ids=...)`, which needs
   no mvccTs.
6. **Why Milvus still matters at boot**: `knowledge_read_isolated.py:7563-7569`
   validates the persisted npz matrix against `snapshot.points` — and
   `snapshot.points` come from the Milvus readback. Milvus is today the
   *validation anchor* for the npz, not a query engine.
7. **Boot philosophy, self-described**: `serving_pack_loader.py:1-33` — per-file
   hashes fully verified, "Every reconstructed giant model is re-hashed at boot
   … any drift refuses the boot".

## Reading

- "Milvus is not used at serve time" is **design** (npz local scoring since
  `3336aabe`), not a wiring mistake.
- Defect-shaped costs are: (a) the boot readback of the whole Milvus copy
  through a pymilvus iterator that cannot work on Lite — ≈50s of pure timeout
  per open (measured 59.9 / 65.3 / 60.5s on a warm index copy, see
  `attribution-20260915.md`); (b) 1.03GB of pack payload with no query consumer,
  proven three times over (build, seal, boot) and read back again at every open.
- `query_iterator` → batched `get`/`query` removes the 50s without weakening the
  row-level verification; moving the row-level proof to the seal side removes the
  cost entirely (options in the human doc, §5).

## Commands used

```bash
grep -rc "milvus\|Milvus" apps/miroflow-agent/src/data_agents/canonical_v2/*.py
grep -rn "open_manifest_verified_index_snapshot\|audit_isolated_index_snapshot" apps/ --include="*.py"
git log --oneline -S "vector_matrix" -- apps/miroflow-agent/src/data_agents/canonical_v2/
git log -1 --format="%B" 3336aabe
sed -n '230,285p' apps/admin-console/.venv/lib/python3.12/site-packages/pymilvus/orm/iterator.py
```

## Limits

- The copy measurement gives the per-open cost; whether the live line pays it per
  process or per session is being settled by the `serving-index-process-scope`
  T2 counters (this note only establishes that the readback sits on the open
  path).

## Design-correctness probe (2026-09-15, follow-up)

Question: is local numpy scoring the right choice versus the in-pack Milvus copy?

Method (read-only; Milvus opened on a `/tmp` copy of `index-v2/milvus.db`):
`MilvusClient(uri=copy)` → `list_collections` → `list_indexes` →
`search(limit=10)` with a fixed float32 query; the same query scored by numpy
over `vector_matrix.npz` (cosine via stored norms).

| probe | numpy matrix (current design) | Milvus Lite copy |
|---|---|---|
| per-query search | **18.5 ms** (51,026×4096 float64 gemv) | **116.4 ms** warm / 2762 ms first (TOP10) |
| top-10 result | exact cosine | **identical ids, identical order, identical scores** |
| index state | — | `AUTOINDEX` M=18 efC=240, but `indexed_rows=0` → Lite scans, no real ANN |
| open cost | npz load 1.41 s | client open 0.57 s; iterator readback pays the 60s-class mvccTs stall |
| resident | 1.68 GB float64 (float32: 0.836 GB / 11.8 ms gemv) | 1.03 GB file + engine |

Reading: "switch to Milvus for speed" is false in this environment — Lite has no
real ANN, and the local path is both faster and exact. The defect is not the
scoring choice; it is (a) shipping and re-verifying a second full copy with no
query role, and (b) the local path's own debt (float64 is a free 2×; O(N)
ceiling — at 10× corpus ≈ 185 ms/query and 16.8 GB resident; the per-session
reload is being fixed by this change).
