# serving-model-sync — run16 null-field pack-load coupling

Governing change (data line, not created here): `openspec/changes/data-cleaning-batch1/`
(D0-a) in the `data-rebuild` worktree, branch `data/p4-serving-pack-rebuild`.
This slice is the serving-line counterpart: run16 will publish JSON `null` for
nine projection fields that the serving pack loader still requires, so the
run16 pack would be rejected at boot with `ServingPackIntegrityError`.

## 1. What changed

| File | Change |
|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/domain_projection_models.py` | The nine fields become `X \| None = None` with the data line's D0-a comments (`CompanyProjection.profile_summary` L398-400, `.technology_route_summary` L407; `ProfessorProjection.department` L490, `.email` L491, `.homepage` L494, `.paper_summary` L503, `.patent_summary` L505, `.profile_summary` L507, `.title` L512). No other line touched. |
| `apps/miroflow-agent/tests/canonical_v2/test_serving_projection_optional_fields.py` | New regression test (6 cases): run15 record round-trip, null-record validation + hash binding, and the loader's own `_parse_model` entry point. |
| `apps/miroflow-agent/tests/canonical_v2/fixtures/run15_public_domain_projection_records.json` | Fixture: one company + one professor record decoded (read-only) from the sealed run15 pack, de-identified (see §2). |

The model file is **byte-identical** to the data line's copy:

```bash
diff .worktrees/serving-model-sync/apps/miroflow-agent/src/data_agents/canonical_v2/domain_projection_models.py \
     .worktrees/data-rebuild/apps/miroflow-agent/src/data_agents/canonical_v2/domain_projection_models.py
# (no output)
```

Nothing else on the serving line was changed: no parse-side counterpart proved
necessary (§5), and no data-line cleaning module was imported.

## 2. Fixture provenance (faithful envelope, de-identified values)

Decoded read-only from `/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed/relationships.json`
→ `candidate_projection_result.public_domain_projections` (mmap + `json.raw_decode`;
the 3.4 GB file was never copied into the repo and never written):

| domain | source record `content_sha256` |
|---|---|
| company | `dc245ba8a1bbf2c470856817fa62048f4ed068bcca5a182b63ccda1c9699cf12` |
| professor | `6f5230e0aeb2193decba3d5bd83a40833ce45b1bea24f6705aabb694e1671970` |

The committed fixture keeps every key, type, `field_lineage` entry, `evidence`
edge and placeholder string verbatim (company `profile_summary = "未找到"`,
professor `paper_summary`/`patent_summary` = "No dedicated summary was supplied
by the full-column workbook source.", `department.name`/`title` = "Not supplied
by the historical source.") and replaces identifying text values (names, email,
homepage, address, website, summaries) with synthetic stand-ins. Placeholder
strings are kept because they are exactly the values D0-a turns into `null`.
The test re-binds `content_sha256` the way the models recompute it, so a
passing validation also proves the fixture is byte-faithful (`model_dump` ==
payload, asserted in the test).

## 3. RED → GREEN

RED (model before the change; `git stash` of the model file):

```bash
cd apps/miroflow-agent && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/canonical_v2/test_serving_projection_optional_fields.py
# 4 failed, 2 passed in 6.90s
```

The failing cases name exactly the nine fields (`_parse_model` wraps the
pydantic error in `ServingPackIntegrityError`, so the field list is captured
from the underlying `ValidationError`):

```text
company   -> [(('profile_summary',), 'string_type'), (('technology_route_summary',), 'string_type')]
professor -> [(('department',), 'model_type'), (('email',), 'string_type'), (('homepage',), 'string_type'),
              (('paper_summary',), 'string_type'), (('patent_summary',), 'string_type'),
              (('profile_summary',), 'string_type'), (('title',), 'string_type')]
E  ServingPackIntegrityError: serving pack relationships.candidate_projection_result.public_domain_projections[0] failed typed validation
```

GREEN (after the change):

```bash
cd apps/miroflow-agent && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/canonical_v2/test_serving_projection_optional_fields.py
# 6 passed in 7.05s
```

Test names: `test_run15_record_round_trips_through_serving_model[company|professor]`,
`test_projection_accepts_null_d0a_fields[company|professor]`,
`test_loader_parse_helper_accepts_null_d0a_fields[company|professor]`.

## 4. Unmodified run15 records under the new models

The two real records (no de-identification, straight from the sealed pack)
validate, dump back byte-identically and keep their declared hash:

```text
company   validated: True dump==payload: True hash preserved: True
professor validated: True dump==payload: True hash preserved: True
```

## 5. Hash recomputation (step 4 of the contract)

Recomputation over these models exists, and it is bound to the *dump*, so the
type/default change cannot alter it for records whose values are present:

* `candidate_projection.py:325-331` — `CandidateProjectionResult` recomputes
  `_canonical_sha256(model_dump(mode="json", exclude={"content_sha256"}))` over
  the whole bundle (including `public_domain_projections`); this runs inside the
  loader's `_parse_model(CandidateProjectionResult, ...)` at
  `serving_pack_loader.py:844-853`.
* `candidate_projection.py:_published_projection_manifests` /
  `_projection_manifest` — each `ProjectionManifest.content_sha256` is recomputed
  from the record dumps and compared (`validate_projection_bundle`).
* `domain_projection_models.py:371-377` — each record's own `content_sha256`.
* `index_projection.py` sha256 uses (`lookup_content_sha256`,
  `embedded_content_sha256`, `source_projection_content_sha256`,
  `index_point_content_sha256`, `_document_content_sha256`) are materialization-time.
  The pack boot `model_construct`s `IndexProjectionResult` from the opened
  snapshot (`serving_pack_loader.py:789`) and re-reads stored strings
  (`json.loads(point.embedded_content)`, `serving_pack_loader.py:1352`); no
  boot-time re-derivation from the projection models.
* `_public_embedded_content` (`index_projection.py:738`) is called only from
  `IndexProjectionBuilder.build` (`index_projection.py:478`); the pack path
  never calls it.

Consequences, both proven rather than argued:

1. run15 (values present): per-record dumps are byte-identical (§4) and the
   whole-bundle hash recomputed by the models equals the manifest value at
   boot (§6) — the pack loads with identical hashes.
2. run16 (nulls): test `test_projection_accepts_null_d0a_fields` proves
   `model_dump == payload` and `_canonical_sha256(payload) == content_sha256`,
   i.e. the hash the data line computes over its dump is the hash the serving
   side recomputes at load.

## 6. The run15 pack still loads (scratch process, no port, no writes)

Byte-identical copies under `/tmp/run15-boot` (the sealed pack and the index
target were only read; `ls --time-style=long-iso` shows their mtimes unchanged
and no new files under `/var/tmp/mirothinker-data-v2`). The only edits in the
copy are the index-root redirect strings (marker `root`, manifest
`index_root`/`index_marker_sha256`); `CANONICAL_V2_SERVING_RECEIPT_PATH` forced
the mount receipt into `/tmp`. Port 18188 was never touched.

```bash
CANONICAL_V2_SERVING_RECEIPT_PATH=/tmp/run15-boot/pack.mount-receipt.json \
  uv run python /tmp/run15-boot/boot_run15_copy.py
```

| run | path exercised | result |
|---|---|---|
| 1 | full file hashing (no receipt) | `MOUNT OK in 336.1s` |
| 2 | mount-receipt path (production) | `MOUNT OK in 333.5s` |

Both runs: `public domain projections: {company: 7086, paper: 24520, patent:
11504, professor: 3958}`, `index points: 51026`, `lookup documents: 47068`,
`run15 null counts for the 9 D0-a fields: none`, and

```text
candidate result content_sha256 recomputed by the models: 6ad4c090aa0a067479f632e0e1e27dfaffd6cd5eae6f7fa1e7802d92c6b3951a
manifest candidate_projection_result_content_sha256:       6ad4c090aa0a067479f632e0e1e27dfaffd6cd5eae6f7fa1e7802d92c6b3951a
byte-identical bundle hash: True
```

## 7. Pre-existing regression suites (same command before/after)

```bash
cd apps/miroflow-agent && uv run pytest -q -p no:randomly -p no:cacheprovider \
  tests/canonical_v2/test_serving_pack_loader.py \
  tests/canonical_v2/test_domain_projection_contract.py \
  tests/canonical_v2/test_index_projection_embedded_content.py \
  tests/canonical_v2/test_fast_boot.py \
  tests/canonical_v2/test_placeholder_scrub.py \
  tests/canonical_v2/test_path_eligibility_contract.py \
  tests/canonical_v2/test_domain_inclusion_contract.py \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  tests/canonical_v2/test_relationship_projection_contract.py \
  tests/canonical_v2/test_serving_supplemental_person_criteria.py \
  tests/canonical_v2/test_ambiguity_gate_serving.py \
  tests/canonical_v2/test_ambiguity_switch_execution.py \
  tests/canonical_v2/test_serving_projection_optional_fields.py
```

| run | result |
|---|---|
| before (model stashed) | `4 failed, 204 passed, 2 skipped in 389.57s` |
| after | `208 passed, 2 skipped in 368.37s` |

Failure-set diff (comm-style): the before-failures are exactly the four new RED
cases and nothing else; the after-run has no failures at all.

```text
< FAILED .../test_serving_projection_optional_fields.py::test_projection_accepts_null_d0a_fields[company]
< FAILED .../test_serving_projection_optional_fields.py::test_projection_accepts_null_d0a_fields[professor]
< FAILED .../test_serving_projection_optional_fields.py::test_loader_parse_helper_accepts_null_d0a_fields[company]
< FAILED .../test_serving_projection_optional_fields.py::test_loader_parse_helper_accepts_null_d0a_fields[professor]
> (no failures)
```

## 8. Not verified / residual risk

* The heavy `canonical_v2` suites that exercise the **build** pipeline
  (`test_knowledge_build_isolated.py`, `test_knowledge_serving_isolated.py`,
  `test_knowledge_read_isolated.py`, `test_knowledge_answer_*`,
  `test_lexical_index.py`, the two `*_postgres.py` projection suites) were not
  re-run before/after: a first attempt stalled for >25 minutes inside
  `test_knowledge_build_isolated.py::test_complete_build_uses_verified_*` and
  was stopped. Their subject is the build/data side (run16 is produced on the
  data line); the read path was reviewed statically (last bullet).
* The run16 pack does not exist yet, so it was not served; the null-shape
  evidence is the fixture test plus the loader `_parse_model` call.
* `index_projection.py:754` (`if projection.department.name != _PROFESSOR_MISSING_FIELD_FALLBACK`)
  would raise `AttributeError` on a `null` department. Its caller chain
  (`_vector_points` → `_public_embedded_content`) is reached only from
  `IndexProjectionBuilder.build` — i.e. index materialization, which on run16
  runs on the data line (whose copy already guards `department is not None`) —
  and from the envelope (non-pack) replay path. The serving pack boot/query
  paths do not call it, so no change was made here; it is recorded as a
  follow-up if the serving line is ever asked to materialize an index from
  run16-shaped projections.
* Read-path None-safety was checked statically: `knowledge_serving_isolated`
  renders through `payload.get()` + `isinstance(value, str)`,
  `knowledge_read_isolated` normalizes through `scrub_projection_payload`
  (`placeholder_scrub.py:104-118`, `None`-safe) and filters `None`
  (`_normalized_values`, `_normalized_scalar_values`).

### Merge-order dependency for run16 (checked read-only, not part of the diff)

The run16 sealer (`data-rebuild/.agents/runs/full-column-serving-pack-rebuild/build_run16_serving_pack.sh`)
runs from the serving worktree and requires **both** P1 (`fix/slim-serving-pack`,
v2 pack schema) and this model-sync change there:

* the sealer parses `CompleteCandidateBuildEnvelope`
  (`s12c/build_serving_pack.py:224`), which types
  `index_projection_request.candidate_projection_result` as
  `CandidateProjectionResult` (`index_projection.py:263-265`) — every public
  projection is validated through the same nine fields, so sealing fails on
  run16 nulls without this change;
* P1's loader still parses `CandidateProjectionResult` at boot
  (`git show fix/slim-serving-pack:.../serving_pack_loader.py:877`), so the boot
  gate needs it too.
* Neither branch contains the other today (`git merge-base --is-ancestor
  fix/slim-serving-pack codex/canonical-v2-s12a-ready` fails) and the live
  worktree is clean at `5afdb6f6`; the run16 *build* itself (staging-v3 /
  index-v3 materialization) runs from the data-rebuild worktree
  (`build-run16.sh`), whose `index_projection.py` already guards nulls.

## 9. Commands cheat-sheet

```bash
# new test
cd apps/miroflow-agent && uv run pytest -q -p no:randomly \
  tests/canonical_v2/test_serving_projection_optional_fields.py
# style
uv tool run ruff@0.8.0 check apps/miroflow-agent/src/data_agents/canonical_v2/domain_projection_models.py \
  apps/miroflow-agent/tests/canonical_v2/test_serving_projection_optional_fields.py
uv tool run ruff@0.8.0 format --check <same files>
```
