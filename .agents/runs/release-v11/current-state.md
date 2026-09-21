# release-v11 — current state

**Slice**: cut the **v1.1** release of the serving stack. Base = `delivery-v1` =
`36df47b8` (frozen v1 code point). One branch `release/v1.1` merges the three
completed sibling branches, the merged tree is verified, and the run16 serving
pack is **re-sealed against the v1.1 code** so a v1.1 boot keeps the fast path
(the recorded reader digest is the reading code's identity; a mismatch silently
costs ~190 s per boot).

**Out of scope (deliberately not done)**: switching the live service, editing the
live command file (`s12g/serve-18188-command.sh`), touching
`serving-pack-run16-readerbound/`, `index-v3-v2/`, the state dirs, or
`docs/plans/` (human-side docs are owned elsewhere).

## Where things stand

| Item | State | Evidence |
|---|---|---|
| `release/v1.1` branch (3 merges, conflict-free) | done | `verification.md` §1–2, `evidence/union-check.txt` |
| merged tree == union of the three branches | verified | `union-check.py` → "union holds" |
| lint (ruff on changed paths) | 2 pre-existing errors, 0 new | `verification.md` §3 |
| admin-console full suite before/after | 25F/105E/1481P → 25F/105E/1543P, identical failure ids | `evidence/test-runs.txt` |
| miroflow-agent canonical_v2 targeted before/after | 2F/346P → 2F/375P, same 2 pre-existing reds | `evidence/test-runs.txt` |
| re-seal of the pack against v1.1 code | done, 42.08 min, exit 0 | `verification.md` §5, `reseal-command.sh`, `evidence/reseal-phases.txt` |
| delta vs the mounted pack | only `manifest.json` changed | `verification.md` §6, `delta-proof.sh`, `evidence/delta-proof.txt` |
| a v1.1 boot takes the fast path with the new pack | yes: 119.9 s vs 284.4 s replaying the old pack | `fastpath-check.py`, `evidence/reseal-phases.txt` |
| live 18188 service | untouched (never restarted/killed/bound) | `verification.md` §7, `evidence/protected-paths.txt` |

## Files in this run dir

| File | What it is |
|---|---|
| `current-state.md` | this file |
| `verification.md` | the evidence report (numbers, command lines, deltas) |
| `reseal-command.sh` | the exact sealer invocation (the official s12c sealer, v2 pack contract) |
| `delta-proof.sh` | file-by-file comparison of the new pack vs the mounted one |
| `union-check.py` | proves the merged tree is exactly the union of the three branches |
| `fastpath-check.py` | opens the new pack in a fresh process, with and without the reconstruction replay, to show which branch a v1.1 boot takes |
| `evidence/` | raw command output: union check, preflight hashes, test runs, reseal phases, delta proof |

## Reading the two reader digests

* The pack the live service mounts records `ebc22047cc9bef912201da5292809935c619705a2b8d8eb718cfec081b0da362`.
* The merged v1.1 tree's reader digest is `79e7492bb1d8a26d536d86c7d6b8b90bc5cb014ffe0e2b6f5bc4460591300d67`
  → **the live pack must not be served under v1.1 code** (it would replay the
  reconstruction on every boot); this is exactly what the new pack fixes. The
  digest is `sha256(python=3.12.12 + pydantic=2.12.5 + every canonical_v2/*.py)`,
  so the *interpreter patch* and *pydantic* version are part of it — the sealer
  was run with the deployment venv (root `.venv`, 3.12.12 / 2.12.5).
