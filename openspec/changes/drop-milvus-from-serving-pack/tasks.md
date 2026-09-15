# Tasks: drop-milvus-from-serving-pack

Change id: `drop-milvus-from-serving-pack`. Evidence dir:
`.agents/runs/drop-milvus-from-serving-pack/`.

## T1 — point authority decided

- [x] T1.1 Record where `IndexProjectionPoint` objects live today (Milvus
      `point_json` only; lookup carries `lookup_content`, npz carries vectors +
      ids) and rule out derivation from either.
- [x] T1.2 Choose the store: `index_point` table inside the release
      `lookup.sqlite3`. Rejection table for the separate-file option.
- [x] T1.3 Choose the v1/v2 switch: `manifest.schema_version`, never file
      sniffing; marker schema unchanged.
- [x] T1.4 Placeholder census: delete (design §5 reasons), not gate.

## T2 — v2 pack contract implemented

- [x] T2.1 `index_point` store: `write_lookup_index_points` /
      `_read_index_points_from_path` (metadata columns mirroring the Milvus row
      binding), fail-closed when the table is missing.
- [x] T2.2 `_open_verified_index_snapshot` branches on an explicit
      `point_store`; v2 path imports/calls nothing from `pymilvus` and refuses a
      `milvus.db` present in the index root.
- [x] T2.3 Loader: `PACK_SCHEMA_VERSION_V2`, `PACK_INDEX_FILENAMES_V2`,
      `pack_index_filenames()`, v2 registry in the manifest check, the mount
      receipt, and the full-hash loop.
- [x] T2.4 Lane factory (`create_serving_pack_knowledge_read`) threads the store
      derived from `authority.manifest.schema_version`.
- [x] T2.5 Sealer: `--pack-schema-version`, v2 manifest + registry, no
      `milvus.db` copy, refuses a v2 seal over a v1 index root.
- [x] T2.6 Migration: `convert_isolated_index_to_v2` + CLI in the run dir.
- [x] T2.7 Delete the placeholder census (sealer phase + census-only code and
      its test); keep the read-side matcher.

## T3 — verification

- [x] T3.1 Layer ① RED/GREEN: 11 tests in
      `apps/miroflow-agent/tests/canonical_v2/test_serving_pack_no_milvus.py`
      (R1–R11 of the verification contract).
- [x] T3.2 Layer ② regression: `test_serving_pack_loader.py`,
      `test_placeholder_scrub.py`, `test_fast_boot.py`,
      `test_knowledge_read_isolated.py`, `test_index_projection_isolated*`
      suites.
- [x] T3.3 Layer ③ scratch 18296: v2 index + v2 pack synthesized from copies of
      the run15 artifacts; boot log without any Milvus step; replay 7/7; the two
      verbatim probes; the user case (`web_items=[]`); boot timing against the
      721s baseline.
- [x] T3.4 v1 compatibility on the same code: run15 copy pack boots and passes
      a replay smoke.
- [x] T3.5 Scratch stopped and cleaned; production tree untouched (verified).

## T4 — deliverables

- [x] T4.1 OpenSpec change files + `change-ledger.md` row (`in-verification`).
- [x] T4.2 Human log `docs/plans/2026-09-15-drop-milvus-from-serving-pack-log.md`
      + one line in `docs/plans/index.md`.
- [x] T4.3 Evidence: `verification-contract.md`, `verification.md`, conversion
      and seal scripts, scratch logs, replay report, probe captures.

## Follow-ups (not this slice)

- [ ] F-1 Align the build path (`create_isolated_index_projection_builder`) and
      `audit_isolated_index_snapshot` with v2 so a future full rebuild can emit a
      v2 index root directly instead of migrating a v1 one.
- [ ] F-2 Fold the migration into the run16 pack-switch window (deploy + rollback
      drill live there, not here).
- [ ] F-3 Decide the data-line home for placeholder *rate* reporting (R15/D1)
      if the product owner still wants the measurement.
