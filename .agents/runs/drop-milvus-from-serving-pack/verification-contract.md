# Verification contract — drop-milvus-from-serving-pack (P1)

Written **before** any production-code edit (AGENTS.md §4 TDD boundary).
Layer ① artifacts are the tests listed here; layer ③ is the scratch run on
port 18296. Nothing in this file may be relaxed to make a change pass.

## Contract under test

1. A pack whose `manifest.json` declares
   `schema_version = "canonical-v2-serving-pack-v2"` boots **without opening
   Milvus and without importing `pymilvus`**, and its points come from the
   `index_point` table of the release `lookup.sqlite3`.
2. A pack that declares `canonical-v2-serving-pack-v1` (run14/run15 shape)
   boots exactly as before: Milvus path, same file registry, same receipt.
3. Every v2 failure is **fail closed** (no silent empty/degraded point set).
4. The `vector_matrix.npz` anchor (point-set equality) keeps failing in both
   directions under the new store.
5. The mount receipt (F1) still works and for v2 registers only the v2 files.
6. The seal-time placeholder census (warn-only, no reader) is gone; the
   read-side placeholder matcher is untouched.

## RED assertions (test → what it locks)

New file `apps/miroflow-agent/tests/canonical_v2/test_serving_pack_no_milvus.py`.
Fixture: the existing contract fixture (`test_serving_pack_loader.py` helpers)
extended with a **v2 index root + v2 pack** built through the real sealer; the
`pymilvus` import is poisoned by a `sys.meta_path` finder so any Milvus open on
the v2 path raises.

| # | Test | Locks (RED before the change) |
|---|---|---|
| R1 | `test_v2_boot_opens_without_pymilvus` | v2 authority opens; `snapshot.points` == index points; no `pymilvus` import attempted |
| R2 | `test_v2_points_come_from_lookup_point_table` | the boot read hits `index_point` (delete/rename the table → R3 fires, not a silent `()`), and `snapshot.points == index_result.points` |
| R3 | `test_v2_pack_without_point_store_is_refused` | v2 + missing `index_point` table ⇒ `ServingPackIntegrityError` |
| R4 | `test_v2_pack_with_milvus_copy_is_refused` | v2 + a `milvus.db` inside the index root ⇒ refuse |
| R5 | `test_v1_pack_still_boots_through_milvus` | v1 registry (`lookup.sqlite3`, `milvus.db`) + Milvus point read unchanged |
| R6 | `test_v2_npz_anchor_rejects_extra_and_missing_points` | npz ⊄ store and store ⊄ npz both raise `IndexProjectionIntegrityError` |
| R7 | `test_v2_mount_receipt_registers_only_v2_files` | first boot ⇒ `verification: full`, receipt `files` keys == {lookup, marker}; second boot ⇒ `verification: receipt` |
| R8 | `test_sealer_v2_pack_carries_no_milvus_file` | `build_serving_pack_from_authority(..., pack_schema_version=v2)` writes no `milvus.db`, manifest `files` == v2 registry, and the loader dogfoods it |
| R9 | `test_v2_and_v1_read_the_same_index_to_the_same_points` | equivalence: the same index artifacts read through both stores yield identical points (point objects are the authority; only the storage form changed) |
| R10 | `test_index_point_migration_preserves_points_and_drops_milvus` | `convert_isolated_index_to_v2` on a v1 root ⇒ dest has the points table, no `milvus.db`, rewritten marker, copied npz, and identical points |
| R11 | `test_placeholder_census_is_deleted_but_matcher_survives` | `placeholder_scrub.scan_lookup_index` / `classify_field_value` gone; `scrub_placeholder_value` still present; the sealer writes no `*.placeholder-scan-report.json` |

RED state before implementation: R1–R4, R6–R11 refer to symbols
(`PACK_SCHEMA_VERSION_V2`, `index_point`, `pack_schema_version=`,
`convert_isolated_index_to_v2`) that do not exist yet ⇒ collection/attribute
errors. R5 is the regression guard and must stay green throughout.

## Layer ③ — scratch acceptance (port 18296)

Recipe (no production writes, no live-line touch):
`/var/tmp/slimpack-296/{v1,case}/{index,pack}` built from **copies** of
`/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed` +
`/var/tmp/mirothinker-data-v2/index-v2`; launcher copied from the 18295 command
file with port/paths replaced.

| # | Assertion | Evidence |
|---|---|---|
| S1 | v2 boot log has **no** `milvus` open/list/read step and no `mvccTs` timeout | `logs/serve-18296-v2.log` grep + `snapshot.*` timing steps |
| S2 | v2 boot-to-health time recorded against the 721s baseline | boot log timestamps |
| S3 | replay gate 7/7 on the v2 pack | `replay_fix_round1.py --base-url http://127.0.0.1:18296` report |
| S4 | probe `字节跳动` answer contains `ByteDance Ltd.` | probe SSE capture |
| S5 | probe `优必选有哪些专利` returns ≥30 local CN citations | probe SSE capture |
| S6 | user case `详细介绍一下 国先中心（深圳）` complete, `web_items=[]` | probe capture vs `.agents/runs/baseline-20260915/guoxian-f2.txt` |
| S7 | v1 pack (run15 copy) still boots on the same code; replay smoke passes | `logs/serve-18296-v1.log` + replay report |
| S8 | scratch stopped, no production/other-scratch dir written | cleanup log + `find` output |

## Not in this contract (out of scope)

Deploying to 18188 / run16 pack switch (that window owns deploy + rollback
drill), the build-side isolated index builder (still writes Milvus for the data
line), and the non-pack envelope serve path.
