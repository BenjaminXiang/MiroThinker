# Design: drop-milvus-from-serving-pack

## 1. T1 — where the 51k `IndexProjectionPoint` objects live

### 1.1 Facts that constrain the choice

- The complete point object (`point_id`, `canonical_object_id`,
  `release_id`, `projection_id`, `projection_scope`, `domain`,
  `reference_type`, `projection_view`, `projection_version`,
  `schema_version`, `embedding_model`, `eligibility_*`,
  `source_projection_content_sha256`, `embedded_content`,
  `embedded_content_sha256`, `source_evidence_ids`, serialized by
  `point.model_dump_json()`) exists today only in the Milvus row column
  `point_json` (`index_projection_isolated.py:737-794`).
- It is **not** derivable from the lookup store: `LookupProjectionDocument`
  carries `lookup_content` / `lookup_content_sha256`, the point carries
  `embedded_content` / `embedded_content_sha256` — different fields, different
  hashes (`index_projection.py:108-216`).
- It is **not** derivable from `vector_matrix.npz`: the npz carries
  `point_ids` + the float64 matrix + norms only.
- Boot already reads the whole release `lookup.sqlite3`
  (`_read_lookup_documents_from_path`, 47,068 documents / 575MB JSON in run15)
  and the whole Milvus inventory every boot. The point read is an *additional*
  pass, not the only one.
- The pack directory is a hash **registry**, not the data source: the loader
  verifies the pack's file hashes and then opens the artifacts under
  `manifest.index_root`. Points therefore have to live in the **index root**
  (the release directory), which is where `vector_matrix.npz` already lives.

### 1.2 Decision: `index_point` table in the release `lookup.sqlite3`

```sql
CREATE TABLE index_point (
    point_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    projection_id TEXT NOT NULL,
    canonical_object_id TEXT NOT NULL,
    embedded_content_sha256 TEXT NOT NULL,
    point_json TEXT NOT NULL
) STRICT;
CREATE INDEX index_point_owner
  ON index_point(release_id, projection_id, canonical_object_id);
```

The four metadata columns mirror the Milvus row columns the current read
validates (`_validate_physical_point_rows`), so the proof strength —
"the physical row metadata must agree with the JSON body" — is preserved
verbatim; `point_json` is the authority.

Why not candidate B (a separate `points.jsonl` / `points.sqlite3`):

| Criterion | `index_point` in lookup.sqlite3 | separate file |
|---|---|---|
| Boot open cost | 0 extra files: the same read-only connection that reads documents also reads points | +1 open, +1 file to place, hash and register |
| Hash/receipt binding | free: `manifest.files["lookup.sqlite3"]` and the mount-receipt fingerprint already cover it | new manifest entry + new receipt entry + new sealer copy step |
| Change surface | one `CREATE TABLE` in the existing sqlite schema owner | new file contract, new manifest field, new zip/copy logic, new refusal paths |
| "One authority copy per fact" (proof-chain §5) | yes | a third artifact for the same fact |

A JSONL side file would additionally have to carry its own framing, ordering
and duplicate rules — pure new surface for no benefit.

### 1.3 v1 vs v2: manifest schema version, never file sniffing

`manifest.schema_version` is the single switch:

- `canonical-v2-serving-pack-v1` → registry `(lookup.sqlite3, milvus.db)`,
  Milvus point read, exactly today's code path (run14/run15 packs keep booting;
  the ~50s mvccTs stall stays where it already is, on v1 packs only).
- `canonical-v2-serving-pack-v2` → registry `(lookup.sqlite3,)`, sqlite point
  read, no `pymilvus` import anywhere on the path.

The marker file keeps its v1 schema in both cases: it is a *target safety*
artifact (`root`/`target_id`/`release_id`/`forbidden_milvus_paths`), and its
"the isolated target must not be the original Milvus" checks are still the right
guard for v1 and harmless for v2 (no file, no resolution).

Fail-closed rules added for v2 (`_open_verified_index_snapshot`):

- `index_point` table missing → `ServingPackIntegrityError` (never an empty or
  partial point set);
- `milvus.db` present in the index root → refuse: the v2 contract says the
  serving index carries no Milvus copy, so a half-migrated directory is caught
  at boot instead of being silently carried;
- points read back must equal `receipt.point_ids` (sorted/unique), each row's
  metadata must equal its JSON (same rule as the Milvus read).

The `vector_matrix.npz` anchor is unchanged in form: it compares against
`snapshot.points`, which now come from the sqlite store. Both mismatch
directions stay fail-closed.

### 1.4 Known boundary (deliberately untouched)

`audit_isolated_index_snapshot` — the full physical audit that re-derives every
vector through the embedding adapter — stays Milvus-only (it is the non-pack
build/audit path and it needs the stored vectors, which v2 deliberately does not
keep). Serving the v2 release through the **pack** is unaffected; the v2
evidence story is seal-time proof + npz + marker/receipt, per
`2026-09-15-proof-chain-first-principles.md` §5. Aligning the build path
(`create_isolated_index_projection_builder`) and this audit variant with v2 is a
follow-up slice, named in tasks.md.

## 2. Boot path after the change

```
open_serving_pack_authority
  manifest.schema_version ─┬─ v1 → registry (lookup, milvus) ; milvus point read   [unchanged]
                           └─ v2 → registry (lookup)        ; sqlite point read     [no pymilvus]
  mount receipt: identities over the version's registry (F1 mechanism unchanged)
  npz load (unchanged)  →  anchors on snapshot.points
```

Timing step names change on the v2 path only
(`snapshot.lookup_points` replaces `snapshot.milvus_client_open` /
`snapshot.milvus_list_collections` / `snapshot.milvus_read_points` /
`snapshot.milvus_close`), so the boot delta is readable from the same
`serving_timing` output.

## 3. Sealer

`build_serving_pack.py` gains `--pack-schema-version {v1,v2}` (default v1 = no
behaviour change for existing callers):

- v2 copies `lookup.sqlite3` + marker + relationships + catalog, writes a v2
  manifest, and refuses if the index root still carries `milvus.db` or lacks the
  `index_point` table (the "produce v2 from a v1 index" step is the migration
  script, not a silent in-sealer conversion);
- the dogfood open and the dogfood comparison are unchanged in substance
  (the sealer still refuses a pack whose rebuilt authority differs).

## 4. Migration

`convert_isolated_index_to_v2(source_root, dest_root, ...)` in
`index_projection_isolated.py`:

1. verify the source marker/receipt identity;
2. copy `vector_matrix.npz` to the destination, write the marker for the new
   root;
3. read every point from the source Milvus (one offline pass) and stream it into
   the destination lookup store, which starts as a byte copy of the source
   `lookup.sqlite3` (so documents, manifests, build metadata and the
   materialization receipt stay identical);
4. cross-check: point ids == `receipt.point_ids`, npz point set == point set;
5. report counts, sizes and hashes; the destination never contains `milvus.db`.

The scratch CLI in `.agents/runs/drop-milvus-from-serving-pack/` is a thin
wrapper over it, used both for the T3 acceptance and as the run16 recipe.

## 5. Placeholder census: deleted, not gated

`placeholder_scan` is a warn-only, read-only census of the source lookup index
written as a side-car report next to the pack. Its only caller is the sealer;
**nothing reads the report** — the repo already names it an anti-pattern
(`2026-09-15-proof-chain-first-principles.md:170`: *"a number nobody reads"*;
R9 §9.1 question 2).

Decision: **delete** it, with these reasons:

1. **Wrong layer.** Placeholder density is a property of the *source data*; the
   sealer cannot repair it. A gate there blocks a release for a defect the
   release engineer cannot fix, which reliably degrades into threshold-lowering
   (a bypass built into the process).
2. **No sound threshold.** Counts scale with corpus size (7,086 companies →
   3,097 field hits), so an absolute ceiling is arbitrary; a *rate* gate would
   need a per-domain policy that belongs to the data-quality line (R15/D1), not
   to packaging.
3. **No user-visible gap.** The read path already scrubs placeholders before
   they reach terms/categories (`placeholder_scrub.scrub_placeholder_value` /
   `scrub_projection_payload`, used by `knowledge_read_isolated` and
   `knowledge_serving_isolated`); the matcher and its tests stay.
4. Deletion is cheap to reverse from git history (§9.3 rule 6 forbids keeping
   removed logic "as insurance").

Deleted: `scan_lookup_index`, `classify_field_value`, `_first_text`,
`_flatten_texts`, `SCAN_FIELD_LISTS`, the `_SCAN_*` constants,
`test_scan_lookup_index_counts_and_is_read_only`, and the sealer's
`placeholder_scan` phase + side-car report. Kept: the four matcher families,
`is_placeholder_value`, `scrub_placeholder_value`, `scrub_projection_payload`,
`PLACEHOLDER_MAX_LEN`, `PLACEHOLDER_IDENTITY_FIELDS`, and the nine remaining
tests in `test_placeholder_scrub.py`.

## 6. Compatibility and rollback

- v1 packs: untouched semantics, covered by a fixture-level boot test and a
  scratch boot + replay on the run15 copy.
- v2 packs: no Milvus anywhere on the boot/query path.
- Rollback: code — revert this branch and restart; data — the migration writes a
  new directory, the v1 index root and run15 pack stay as they are.
