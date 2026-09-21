# release/v1.1 — merge + re-seal, raw evidence

Slice: cut the **v1.1** bundle. Base = `delivery-v1` = `36df47b8` (the frozen v1
code point). Three completed sibling branches are merged onto
`release/v1.1`, the merged tree is verified, and the run16 serving pack is
**re-sealed against the v1.1 code** so a boot under v1.1 keeps the fast path.

> `docs/plans/` is owned by the human side and is deliberately **not** written by
> this run.

## 1. Release branch

Worktree: `.worktrees/release-v11` (`git worktree add .worktrees/release-v11 -b release/v1.1 36df47b8`),
created from a clean tree (no modified/untracked files at `36df47b8`).

| # | commit | what |
|---|---|---|
| 1 | `5906a7d1` | merge `fix/embedding-lane-f1f2` (`cd606ee5`, 11 commits) — F1 vector-lane fail-open, F2 embedding endpoint configurable (identity frozen), managed wait-cap row, admin embedding-identity check |
| 2 | `289cdf4c` | merge `delivery/docker` (`a0cd5c13`, 9 commits) — container delivery: Dockerfile + compose (postgres:16), install-site.sh, build-site-bundle.sh, CONFIG-GUIDE, runbook |
| 3 | `1817f914` | merge `feat/recall-regression` (`37949d10`, 5 commits) — canonical-v2 recall-regression harness + frozen baseline (tooling/evidence only) |

`release/v1.1` HEAD after the three merges = `1817f914`; 25 branch commits + 3
merge commits = 28 commits ahead of `36df47b8`. All three merges were
**conflict-free** (`git merge --no-ff` on each; nothing to resolve — the
expected `deploy/README.md` / `openspec/change-ledger.md` / `.gitignore`
overlaps did not materialise because the three branches touch disjoint paths:
41 + 33 + 10 = 84 changed paths, no path is changed by two branches).

## 2. The merged tree is exactly the union of the three branches

`evidence/union-check.txt` (produced by `union-check.py`, committed here):

```
base=36df47b8 merge=HEAD
  branch fix/embedding-lane-f1f2: 41 changed paths
  branch delivery/docker: 33 changed paths
  branch feat/recall-regression: 10 changed paths
merged changed paths: 84
paths changed by the merge that no branch changed: []
paths whose merged blob differs from every owning branch: []
paths changed by a branch but missing from the merge: []
status conflicts: []
VERDICT: union holds
```

i.e. no file outside the three branches' diff was touched, every merged file is
byte-identical to the owning branch's blob, and nothing was dropped. No
conflict markers in any changed file; no deletions (`git diff --diff-filter=D`
empty).

Serving-path files that the merge moves (12, all from `fix/embedding-lane-f1f2`):

```
apps/miroflow-agent/src/data_agents/canonical_v2/{embedding_lane_resilience.py (+136),
  knowledge_build_isolated.py, knowledge_read.py, knowledge_read_isolated.py, managed_config.py}
apps/miroflow-agent/src/data_agents/company/vectorizer.py
apps/admin-console/backend/{api/canonical_v2_admin_config.py, services/canonical_v2_connection_tests.py,
  services/canonical_v2_embedding_identity.py (+539), services/canonical_v2_runtime_sources.py,
  static/admin.html, static/admin.js}
```

## 3. Lint

`uv tool run ruff@0.8.0 check <29 changed .py files>` → **2 errors**, both
pre-existing at `36df47b8` and both on lines the merge does not touch
(`knowledge_build_isolated.py:4230` F402 loop variable shadowing a import;
`knowledge_read_isolated.py:8265` E702 semicolon statement — the base tree
reports the same 2 errors on the same two files). **No new lint findings.**

## 4. Test runs, before vs after

Full numbers in `evidence/test-runs.txt`. Method: one scratch worktree
`.worktrees/release-v11-base` (detached at `36df47b8`, own root venv, own
admin-console venv) so both sides run the same commands on the same box.

| Run | after (`release/v1.1`) | before (`36df47b8`) | delta |
|---|---|---|---|
| admin-console full suite (`cd apps/admin-console && uv run pytest -q`) | **25 failed, 105 errors, 1543 passed, 31 skipped** (254.7 s) | **25 failed, 105 errors, 1481 passed, 31 skipped** (192.6 s) | +62 passed, failure set identical |
| miroflow-agent canonical_v2 targeted (root venv) | **2 failed, 375 passed** (70.5 s) | **2 failed, 346 passed** (44.1 s) | +29 passed (the 4 new embedding test files), same 2 reds |

* Failure-id sets: the admin suite's 130 `FAILED`/`ERROR` ids are **identical**
  on both sides (`diff` of the two lists is empty); the +62 passes are the
  branches' new tests. The targeted agent selection's 2 failures are the same
  two ids on both sides.
* **Pre-existing reds (named):**
  `tests/canonical_v2/test_manual_recall_points.py::test_release_bound_vector_validator_exempts_manual_traces`
  and `…::test_runner_serve_manual_recall_store_fails_open` — re-run alone on the
  base tree (`2 failed, 6 passed`), so both are red *before* the merge. The
  admin-console 25 failures + 105 errors are the box's environmental set
  (Postgres-backed APIs, seeds/jobs, `read_turn_trace` date-pinned tests) and are
  unchanged in identity.
* Deviation from the branches' own numbers, stated: the F1/F2 branch reported
  the agent selection under `apps/miroflow-agent/.venv` (pydantic **2.11.7**,
  the app lock) and saw 1 red; this run uses the **root venv** (pydantic
  **2.12.5**, `uv run pytest apps/miroflow-agent/tests/…` from the worktree
  root) because 2.12.5 is what the serving line runs — hence 2 reds, both
  pre-existing. The admin-console suite reproduces the branch's numbers exactly
  (25/105/1481/31 before, +62 passed after).

## 5. Re-seal

Command: `reseal-command.sh` (committed, exact token set reproduced from the
official sealer the reader-bound re-seal used,
`.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py`
`--pack-schema-version canonical-v2-serving-pack-v2`), run from
`.worktrees/release-v11` with `uv run python` → the worktree root venv
(`CPython 3.12.12`, `pydantic 2.12.5`, same as the serving venv).

Inputs (hashed before the run, `evidence/reseal-preflight.txt`):

```
8 303 007 285  43735faa9300fc834bffcea44304462f30128d5dfa0eb048e76075a115ccea20  …/s12a/complete-candidate-build-envelope.json  (read-only)
  896 270 336  2f3e69f4ed0dabe18eb104e296e6dbe4c0ef90683871ab2edf7c1643ecd2ddb8  index-v3-v2/lookup.sqlite3
          316  b6f78a3b1e28c280860a4210bfad286ef65090e758de5b876d7f639eefaa8373  index-v3-v2/.canonical-v2-isolated-index-target.json
1 676 818 545  b4705cccce00f2cebf630e8f4aa93ecb4921ad2961d5fe8219af4b4b9b0be36c  index-v3-v2/vector_matrix.npz
pack dir /var/tmp/mirothinker-data-v2/serving-pack-run16-v11: absent before the run
```

The disposable build DB (`postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_v2_20260916_r1`,
container `canonical-v2-s12c-pg-20260726-r8`) was verified reachable
(`select current_database(), count(*) from information_schema.tables` →
`miroflow_candidate_v2_20260916_r1|297`) — note the **sealer does not use it**:
its inputs are the envelope + the index root only.

Phases (raw, from the sealer's own `phase=` lines) — see §5.1 below.

Expected recorded reader digest of the merged tree, computed independently
before the seal (root venv):

```
reader_contract_digest() = 79e7492bb1d8a26d536d86c7d6b8b90bc5cb014ffe0e2b6f5bc4460591300d67
  (sha256 of `python=3.12.12` + `pydantic=2.12.5` + the 56 canonical_v2/*.py of the merged tree)
  vs the pack the live service mounts: ebc22047cc9bef912201da5292809935c619705a2b8d8eb718cfec081b0da362
```

### 5.1 Phases and wall clock

Raw lines in `evidence/reseal-phases.txt`. Started 2026-09-21T21:35:33+08:00,
finished 22:17:58 (pid 1462948), exit 0, no failure line, no traceback.

| phase | this re-seal (v1.1) | reader-bound re-seal (2026-09-20, `/tmp/boot-prof/reseal3.log`) |
|---|---|---|
| `envelope_validate` | **2024.062 s** (33.7 min) | 2008.628 s (33.5 min) |
| `index_snapshot_verify` | 11.228 s | 10.245 s |
| `index_artifacts_copied` | 1.685 s | 1.639 s |
| `authority_documents_written` | 178.666 s | 161.555 s |
| `manifest_written` | 5.457 s | 5.431 s |
| `dogfood_open` | **303.459 s** | 296.973 s |
| **total** | **2524.557 s = 42.08 min** | 2484.471 s = 41.41 min |

`envelope_validate` is the bulk (86 % of the previous run too), phase-for-phase
within 4 % — i.e. the merge did not move the seal cost. Pack files:
`lookup.sqlite3` 896 270 336 B, `relationships.json` 3 477 354 956 B (3.47 GB),
`institution_catalog.json` 381 B, marker 316 B, `manifest.json` 11 116 227 B.

New pack: `/var/tmp/mirothinker-data-v2/serving-pack-run16-v11` (4.28 GB on disk).
`manifest.json` sha256 = **`588fdd9eb8f357484ad21f9a22ea0abe1bf3efa7f0b12862be8c2c514438276f`**;
recorded `reader_contract_sha256` = **`79e7492bb1d8a26d536d86c7d6b8b90bc5cb014ffe0e2b6f5bc4460591300d67`**,
which equals the digest computed independently from the merged tree before the
seal (above) — the pack records *this* reader.

### 5.2 Does a v1.1 boot actually take the fast path?

`fastpath-check.py` opens the pack in a fresh process (read-only) and prints
whether the recorded reader is this reader; the loader skips the reconstruction
replay when it is *and* the mount receipt binds the manifest.

| run | pack | `receipt_used` | reader matches | open wall |
|---|---|---|---|---|
| A | old (mounted) `serving-pack-run16-readerbound` | false | **False** → replay ran | **284.415 s** |
| B | new `serving-pack-run16-v11` | true | **True** → replay skipped | **119.904 s** |
| C | new pack, forced replay (the seal's own `dogfood_open`) | — | — | 303.459 s (phase) |

A and B are the same code, same content (47 068 lookup docs / 51 026 points /
identical domain counts / identical `relationship_result` sha) and differ only in
the recorded reader, so the **~165 s** difference is the replay this re-seal
removes; at boot level the same effect measured 421 s → 291 s when the
reader-bound pack landed.

Run A is also the read-side equivalence check: the merged v1.1 code, replaying
the mounted pack, **reproduced its recorded relationship-request and
index-request hashes** (both `ServingPackIntegrityError` comparisons passed).
That is behavioural evidence that the merge did not change what the serving read
path builds, not just a structural argument.

## 6. Delta proof — what the re-seal changed

`delta-proof.sh`, raw output in `evidence/delta-proof.txt`.

```
file set: identical
same      .canonical-v2-isolated-index-target.json
same      institution_catalog.json
same      lookup.sqlite3
CHANGED   manifest.json
same      relationships.json
```

Per file (size, sha256):

| file | readerbound | run16-v11 |
|---|---|---|
| `relationships.json` | 3 477 354 956 · `b65794b005ede1aa04e3743307044bbfe0895541c28b4251dc0ddc35be4bca7f` | identical |
| `lookup.sqlite3` | 896 270 336 · `2f3e69f4ed0dabe18eb104e296e6dbe4c0ef90683871ab2edf7c1643ecd2ddb8` | identical |
| `institution_catalog.json` | 381 · `88b5d714c4684518d97b571368f3f990a524d9a0d747b799d2f4332e54f4b057` | identical |
| `.canonical-v2-isolated-index-target.json` | 316 · `b6f78a3b…` | identical |
| `manifest.json` | 11 116 235 · `ce815fc678e27b44ec54b808245cafebf8a93557a847450b5f4cada113cfa94b` | 11 116 227 · `588fdd9e…` |

**"Only the manifest changed" holds** — the parent's measured property
reproduces for this re-seal. Inside the manifest exactly three fields differ:

```
generated_at            2026-09-20T17:59:53.598727+00:00 -> 2026-09-21T14:12:37.669517+00:00
generator_run_id        run16-readerbound-20260921-v2    -> run16-v11-20260921-v1
reader_contract_sha256  ebc22047…                        -> 79e7492b…
```

Every other field is unchanged, including the whole `files` map (the sealer
recomputed the same hashes for the data files), `build_manifest`,
`index_policy_snapshot`, `index_rebuild_decisions`,
`index_result_content_sha256`, both request hashes, both projection content
hashes and `release_verification`.

**Customer-update consequence**: the delta a v1.1 site has to transfer is the new
`manifest.json` (11.1 MB) — not the 4.28 GB pack, provided the site already has
`serving-pack-run16-readerbound` (identical data files) and `index-v3-v2`.


## 7. Live service / protected paths

* The live listener on 18188 (`pid 519941`, up 20 h 15 m at the end of this run)
  was never restarted, killed or bound.
* `serving-pack-run16-readerbound/`, `index-v3-v2/`, the mount receipts, the state
  dirs and the live command file were read-only inputs; nothing under
  `/var/tmp/mirothinker-data-v2/` was modified except creating the new
  `serving-pack-run16-v11/` directory and its own receipt
  (`evidence/protected-paths.txt` shows the untouched mtimes: readerbound files
  2026-09-21 01:59, its receipt 20:50, index root 2026-09-17 05:55, live command
  file 02:10:45).
* The live command file was **not** edited (switching the service is out of scope
  for this slice).
* One deliberate side effect to know about: the fast-path check rewrote the *new*
  pack's own receipt (`verification: "full"` → `"receipt"`); no protected file.

## 8. Not verified here / for a reviewer

1. **No boot-level, end-to-end run of the new pack.** Nothing was started on any
   port (deliberately: the live service and its state dirs are off-limits in this
   slice). The evidence is library-level: the sealer's `dogfood_open` (forced
   replay) plus two independent fresh-process opens. Before the customer switch,
   run the replay gate against a real instance of v1.1 + this pack.
2. **`test_knowledge_build_isolated.py` was not re-run** in this slice. Twelve of
   its tests (the Postgres-fixture family) were never compared on either side —
   an inherited gap from the F1/F2 branch's own verification (≈4 h of wall clock
   for the pair; the exact command is in that branch's `verification.md` §⑤).
3. **The admin-console 25 failures / 105 errors are environmental** (Postgres
   APIs, seeds/jobs, date-pinned `read_turn_trace` tests). They are identical
   before/after; this slice neither fixed nor worsened them.
4. **The delivery artefacts are not rebuilt.** The container image / site kit
   (`delivery/docker`) were built at `36df47b8`; a v1.1 kit needs a rebuild from
   `release/v1.1` plus this `manifest.json` (the site bundle deliberately ships
   without a mount receipt — see `deploy/docker/README.md`).
5. **Interpretation choice, stated for review**: the brief pointed at
   `.agents/runs/…/s12g/reseal_serving_pack.py` as "the earlier reseal", but that
   file's own history says it was *not* the path used for the reader-bound
   re-seal ("顺带把一次性重封工具补成 v2 可用…但它不是本次的路径",
   `docs/plans/2026-09-18-collection-line-log.md` round 23), and the earlier run's
   log (`/tmp/boot-prof/reseal3.log`) shows exactly the phase set of the official
   sealer (`envelope_validate → index_snapshot_verify → index_artifacts_copied →
   authority_documents_written → manifest_written → dogfood_open`). This run
   therefore reproduces the **official sealer** invocation
   (`s12c/build_serving_pack.py --pack-schema-version canonical-v2-serving-pack-v2`).
   Worth knowing for the next round: the one-off `s12g/reseal_serving_pack.py`
   would also produce a valid pack by copying the files verbatim and rewriting
   only the manifest — i.e. it would skip the 33.7 min `envelope_validate` and, by
   construction, could not perturb `relationships.json`. It was not used here to
   stay on the path the brief asked for.
6. **Two venvs disagree on pydantic** (`apps/miroflow-agent/uv.lock` pins 2.11.7,
   the workspace lock 2.12.5). Serving and the seal both use 2.12.5, which is what
   the reader digest records; the app venv's 2.11.7 is what the F1/F2 branch's own
   targeted run used, which is why its agent-suite counts differ slightly from
   this report's.
7. **Reviewer double-checks on the merge**: the three branches are disjoint on
   paths which is why the merge was conflict-free, but `delivery/docker` and
   `feat/recall-regression` add no `openspec/` artifact (only `fix/embedding-lane-f1f2`
   carries a change); and the `.agents/runs/*` evidence files of all three
   branches are now part of `release/v1.1`, which is intended (they are the
   acceptance evidence for the bundle) but changes the release diff size
   (25 333 insertions across 84 files).

