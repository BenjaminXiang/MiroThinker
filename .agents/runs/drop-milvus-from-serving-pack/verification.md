# Verification — drop-milvus-from-serving-pack

Change: P1 of `docs/plans/2026-09-15-requirements-gap-plan.md` §3.2.
Branch `fix/slim-serving-pack`, baseline `2fe4c16c`.
Commit: `f1184bd4` (contract + tests + sealer + run scripts).
Contract: `verification-contract.md` (written before the code edits).

## Layer ① — tests written in this slice

`apps/miroflow-agent/tests/canonical_v2/test_serving_pack_no_milvus.py` —
**14 tests**. Fixture: the real contract fixture
(`test_serving_pack_loader._build_fixture_once`) plus the real migration and the
real sealer; nothing is a hand-written stand-in for the pack format.

| Test | Locks |
|---|---|
| `test_v2_boot_opens_without_touching_milvus` | v2 authority opens while `_open_milvus_client` is a raising probe **and** every `pymilvus` import is poisoned (`sys.meta_path` guard + `sys.modules` purge); points equal the release points |
| `test_v1_boot_would_fail_without_pymilvus` | the v1 path is untouched: with the same poison it must fail (it still reads Milvus) |
| `test_v2_points_come_from_the_lookup_point_table` | `index_point` holds exactly the release point ids and byte-equal `point_json` bodies |
| `test_v2_pack_without_point_store_is_refused` | dropped table ⇒ `IndexProjectionIntegrityError` |
| `test_v2_pack_with_milvus_copy_is_refused` | stray `milvus.db` in the v2 index root ⇒ refuse |
| `test_v2_point_store_drift_is_refused` | one missing point vs the receipt ⇒ refuse |
| `test_v1_pack_still_boots_through_milvus` | v1 registry `{lookup, milvus, marker, relationships, catalog}` + identical points |
| `test_v1_and_v2_read_the_same_index_to_the_same_points` | store equivalence: points, receipt and lookup documents identical across stores |
| `test_v2_npz_anchor_rejects_extra_and_missing_points` | npz ⊄ store and store ⊄ npz both raise; the healthy npz loads |
| `test_v2_mount_receipt_registers_only_v2_files` | first boot `verification: full` with `files = {lookup, marker}`; second boot `receipt`; no `milvus.db` in `file_sha256` |
| `test_sealer_v2_pack_carries_no_milvus_file` | pack dir + manifest registry, and the version→registry/store mapping refusals |
| `test_sealer_refuses_a_v2_seal_over_a_v1_index_root` | sealer refuses with the actionable "run the migration first" message |
| `test_index_point_migration_preserves_points_and_drops_milvus` | migration: points preserved, no `milvus.db`, npz copied, marker rebound to the new root, `removed_milvus_bytes > 0` |
| `test_placeholder_census_is_deleted_but_matcher_survives` | `scan_lookup_index` / `classify_field_value` / `SCAN_FIELD_LISTS` gone, scrub kept, sealer source has no `placeholder` reference at all |

RED before the change: the new symbols (`PACK_SCHEMA_VERSION_V2`,
`index_point`, `pack_schema_version=`, `convert_isolated_index_to_v2`,
`point_store=`) did not exist; the v2 pack could not even be sealed.

## Layer ② — pre-existing suites

`cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_serving_pack_no_milvus.py tests/canonical_v2/test_serving_pack_loader.py tests/canonical_v2/test_placeholder_scrub.py -q`
→ **51 passed** (14 new + 37 pre-existing; `test_placeholder_scrub` is 9
instead of 10 because the census test was deleted with the census).

`uv run pytest tests/canonical_v2/test_fast_boot.py tests/canonical_v2/test_knowledge_read_isolated.py tests/canonical_v2/test_index_projection_embedded_content.py -q`
→ **52 passed** (details in the second batch at the end of this file).

`uv run ruff check` on every touched file → clean (format: the two edited
modules keep their pre-existing `ruff format` drift — 4 and 3 hunks before and
after this change, none inside the new code).

## Layer ③ — scratch line (port 18296, run15 artifacts copied read-only)

Recipe (all paths outside the production tree; nothing under
`/var/tmp/mirothinker-data-v2/` was written):

- `/var/tmp/slimpack-296/v1/index` ← copies of `index-v2/{lookup.sqlite3,milvus.db,vector_matrix.npz}`
- `/var/tmp/slimpack-296/v1/pack` ← `seal_scratch_pack.py --pack-schema-version v1`
- `/var/tmp/slimpack-296/v2/index` ← `convert_index_to_v2.py` (migration)
- `/var/tmp/slimpack-296/v2/pack` ← `seal_scratch_pack.py --pack-schema-version v2`
- launcher: `.agents/runs/drop-milvus-from-serving-pack/serve-18296-command-{v1,v2}.sh`,
  generated from the 18295 command file with only port/paths/identity replaced
  (no hand-written parameter lists)

### Sizes and authority equivalence

| Artifact | v1 | v2 | Delta |
|---|---|---|---|
| index root | 3,423,984,035 B | 2,573,691,299 B | **−850,292,736 B (−811 MiB, −24.8%)** |
| pack dir | 5,149,214,638 B | 4,298,921,823 B | **−850,292,815 B (−811 MiB, −16.5%)** |
| `lookup.sqlite3` | 668,884,992 B | 896,868,352 B | +227,983,360 B (51,026 points) |
| `milvus.db` | 1,078,276,096 B | absent | −1,078,276,096 B |

Migration report (`conversion_report`, 57.8s wall):
`point_count 51026`, `dest_lookup_sha256 3957c6ee…`, `dest_marker_sha256 f3fae859…`.

`index_result_content_sha256` is **identical** in the run15 sealed manifest, the
v1 scratch pack and the v2 scratch pack (`690946f3a4f00ae52ec…`). The loader
recomputes that hash from the snapshot points at boot, so "the sqlite point set
is the Milvus point set" is proven by the boot itself, not by inspection.

### v2 boot (pack schema v2, port 18296)

- launched 17:01:28; `/api/health` 200 by 17:16:28 (polls at 17:12:58 = 000)
  ⇒ boot-to-health ≈ 12–15 min, of which the mount phase is measured exactly:
  the boot wrote `pack.mount-receipt.json` at 17:06:20 with
  `verification: receipt`, `mount_seconds 289.081` → **−56.8s vs the same-machine
  v1 full mount (345.886s)** and −31s vs the 320s mount in the R9 baseline.
- `grep -ci milvus serve-18296-v2.log` → **0**; no `mvccTs` line; no
  `snapshot.milvus_*` step (the v2 steps are `snapshot.lookup_docs` +
  `snapshot.lookup_points`).
- mount receipt `files` keys: `{lookup.sqlite3, marker}` only.

### Probes (verbatim, on the v2 pack)

| Probe | Result |
|---|---|
| `字节跳动` | answer contains **`ByteDance Ltd.`**; 8 web items; 1105 chars |
| `优必选有哪些专利` | **32 distinct local `CN…` numbers** (≥30 required) |
| `详细介绍一下 国先中心（深圳）` | answer complete (723 chars), `web_items: []` — same shape as `baseline-20260915/guoxian-f2.txt` (answer 完整、web 轨 0 条) |

Raw SSE + summaries: `.agents/runs/drop-milvus-from-serving-pack/scratch/`.

### Replay gate

`uv run python scripts/replay_fix_round1.py --base-url http://127.0.0.1:18296`
→ **RESULT: ALL PASS** (G1_framing, G2_bare_name ×3, G3_person_pronoun,
G4_patents, G5_expansion, G6_anaphoric_opener, G7_enumeration ×3).
Per-turn wall clock 7.7–24.8s, inside the R9 baseline band (entity ≤14s,
citation-dense ≤25s). Report + raw SSE:
`.agents/runs/drop-milvus-from-serving-pack/replay-18296/`.

### v1 compatibility (same code, run15 copy pack)

- launcher `serve-18296-command-v1.sh` (index root `/var/tmp/slimpack-296/v1/index`,
  pack `/var/tmp/slimpack-296/v1/pack`, both v1 form) on port 18296, same code.
- boot-to-health ≈ 14 min (launched 17:49:34, health 200 at 18:03:35).
- the v1 boot log contains the `mvccTs` warning and the Milvus steps — the v1
  path is unchanged (this is exactly the cost v2 removes).
- v1 boot mount receipt: `verification: receipt`, `mount_seconds 340.712`,
  `files = {lookup.sqlite3, milvus.db, marker}` → **the v2 boot (289.081s, two
  files) is 51.6s faster on the same machine, same cache state**.
- `replay_fix_round1.py --only G1_framing,G4_patents` → **RESULT: ALL PASS**
  (report + SSE in `replay-18296-v1smoke/`).

## Layer ② (final) — pre-existing suites, second batch

`uv run pytest tests/canonical_v2/test_fast_boot.py tests/canonical_v2/test_knowledge_read_isolated.py tests/canonical_v2/test_index_projection_embedded_content.py -q`
→ **52 passed**.

## Incident note (live line, unrelated to this branch)

At 18:03:22 the **live 18188 unit was stopped by systemd and auto-restarted**
(journal: `Stopping Canonical V2 knowledge platform backend…` → `Started` at
18:03:24; SIGTERM/143, i.e. a `systemctl --user stop|restart`, not a kill).
No command of this session did that — the only process signals sent here were
two `pkill -f "…serve_s12e_port.py 18296"` invocations against the scratch port
(the second one killed its own shell, which is why two tool calls report
`exit -1`); neither pattern can match `…serve_s12e_port.py 18188`. No timer or
cron is configured for the unit. Recorded here because the slice's ground rule
is "do not restart 18188", so any restart in the window must be accounted for.
The unit was healthy again after its own boot.

## Scratch teardown

Both scratch servers stopped (`18296` refuses connections at 18:04:31); the
scratch bundles/packs stay under `/var/tmp/slimpack-296/` for the record.
Nothing under `/var/tmp/mirothinker-data-v2/` was written (all reads were copies;
the production pack's own mount receipt/metadata were not touched), and the live
18188 pack/index were never opened for write.

## External calls

bocha/serper: 3 probe turns + 11 replay turns; no other network use. Counted
honestly against the shared quota.

## Gaps / not verified here

1. **No deploy.** 18188 still serves run15 (v1); the run16 pack switch with the
   rollback drill is a separate window by decision.
2. The build-side `create_isolated_index_projection_builder` still writes
   Milvus; run16 uses the migration script (follow-up F-1/F-2 in tasks.md).
3. `audit_isolated_index_snapshot` (full vector re-derivation) and the non-pack
   envelope serve path remain v1-only by design (design.md §1.4).
