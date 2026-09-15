# Proposal: drop-milvus-from-serving-pack

## Why

`milvus.db` (1.03GB) is a first-class member of every Canonical V2 serving pack
and is opened on every boot, although **no serving query ever reads it**: vector
scoring runs on the persisted `vector_matrix.npz` (`3336aabe`, 2026-08-03). Its
three real costs, all measured on the live line (2026-09-15):

| Cost | Number | Evidence |
|---|---|---|
| Bytes in every pack + index root | 1.03GB of a 5.03GB pack | `ls -l` on `serving-pack-run15-sealed` |
| Boot time in the Milvus read-back | ~50s of the open path (pymilvus iterator waits on an `mvccTs` the Lite server never returns) | `docs/plans/2026-09-15-milvus-role-in-serving-analysis.md` §2/§5 |
| Start-up failures | 2 in 5 days, single-writer lock (`.milvus.db.lock`) | same document §4 |

The only reason Milvus is still load-bearing at boot is that the **complete
`IndexProjectionPoint` objects live nowhere else**: the lookup store carries
`LookupProjectionDocument`s (`lookup_content`), the npz carries vectors keyed by
`point_id`, and the `point_json` column of the Milvus row is the sole authority
for `embedded_content` / `embedded_content_sha256`. Dropping the file therefore
requires naming a new authority for the point objects — that is what this change
does.

User decision (2026-09-15): P1 of
`docs/plans/2026-09-15-requirements-gap-plan.md` §3.2 — `milvus.db` leaves the
serving pack; the placeholder census ("no reader") is either made a real gate or
deleted. Confirmed go on 2026-09-15.

## What changes

1. **New point authority: `index_point` table inside the release
   `lookup.sqlite3`.** One file per fact: the release directory becomes
   `lookup.sqlite3` (documents + points) + `vector_matrix.npz` +
   `relationships.json` + `institution_catalog.json` + `manifest.json` +
   marker. No new file, no new manifest entry, no new hash registration.
2. **Pack schema v2 (`canonical-v2-serving-pack-v2`).** Its file registry is
   `lookup.sqlite3` + marker + relationships + catalog; `milvus.db` is neither
   copied nor registered. v1 stays byte-for-byte supported (run14/run15 packs
   keep booting through the Milvus path).
3. **Boot branches on the manifest, not on file presence.** A v2 boot performs
   no `pymilvus` import and no Milvus call at all; points come from the sqlite
   store with the same row-level metadata binding the Milvus read had, and the
   npz anchor is now the sqlite point set.
4. **Sealer emits v2** (`--pack-schema-version`), refuses a v2 seal over a v1
   index root, and no longer copies `milvus.db`.
5. **Migration path**: `convert_isolated_index_to_v2` (+ a thin CLI) turns one
   v1 index root into a v2 index root by extracting the 51k points from
   `milvus.db` once, offline.
6. **Placeholder census deleted** from the seal path (see design §5).

## Out of scope / invariants

- No retrieval, routing, ranking, evidence or citation semantic change.
- The data-line build (`create_isolated_index_projection_builder`) still writes
  Milvus; aligning the build path is a later slice.
- Not deployed here: 18188 keeps run15 (v1). Deploy and the run16 pack switch
  happen in the dedicated switch window with the rollback drill.
- `docs/Data-Agent-Shared-Spec.md` contracts and the release/publication
  authority graph are unchanged; the same packed facts are re-derived from the
  same bytes.

## Rollback

Branch-level: `2fe4c16c` is the pre-change serving commit; revert this branch's
commits and restart the unit. Data-level: the v1 index root and run15 pack are
untouched by this change (migration writes to a new directory), so a rollback is
"point the command file back at the v1 pack".
