# Tasks: serving-index-process-scope

## T1 — attribute the live path (instrument, do not guess)

- [x] T1.1 Attribute the serving vector path: snapshot acquisition, lookup
      enumeration, `vector_matrix.npz` load, Milvus open, scoring, candidate
      binding. *(Done 2026-09-15 without touching live code: read-only py-spy
      sampling of the live process + isolated micro-tests on an index copy —
      see `.agents/runs/serving-index-process-scope/attribution-20260915.md`.)*
- [x] T1.2 Recorded cold vs warm vs turn≥2 numbers from the live 18188 line and
      the `turn-debug` traces (cold new-session turn=1 18.7–30.6s; warm 3.0–3.2s;
      turn≥2 0.1–0.9s).
- [x] T1.3 Where the per-session re-entry happens: snapshot open + 1.68GB npz
      load per session; `bind_trace` recomputes 3 canonical hashes per trace
      object (90.8% of `_canonical_sha256`); Milvus check burns ≈50s of the
      60s open path while never being queried at serve time.

## T2 — process-scope the heavy state

- [x] T2.1 Move the snapshot / vector matrix / index handles into a
      process-scoped cache keyed by `(index_root, marker_sha256, release_id)`,
      shared across sessions.
- [x] T2.2 Prove no per-session re-open remains (counter or timer must show one
      open per process).

## T3 — boot-time warm-up

- [x] T3.1 Load + verify the index once during start-up (before serving).
- [x] T3.2 Record the boot delta (must stay ≪ the 13-minute pack load).

## T4 — cheap mount-time identity check + receipt

- [x] T4.1 Replace per-open full hashing with: marker/receipt identity, per-file
      size, first/last-block fingerprints.
- [x] T4.2 Write a boot-time verification receipt (marker sha, file hashes when
      full verification runs, durations) to the log/evidence dir for audit.

## T5 — take Milvus off the query path

- [x] T5.1 Root-cause the `failed to get mvccTs` 60s-timeout behaviour in the
      snapshot open.
- [x] T5.2 Either fix the client configuration or make the Milvus check a
      boot-time/pack-level concern instead of a query-path cost; document which.

## T6 — acceptance evidence

- [x] T6.1 Before/after: first-session vector lane, second-session vector lane,
      and total first-answer latency on the probe queries.
- [x] T6.2 Replay gate 7/7 + probes (字节跳动 → ByteDance Ltd.; 优必选有哪些专利
      → local CN numbers) unchanged.
- [x] T6.3 Identical evidence/citation sets for the probe queries (semantics
      unchanged).

## Evidence

`.agents/runs/serving-index-process-scope/verification.md` — attribution table,
before/after lane timings, per-process open counters, mount receipt, replay
gate 7/7, probe citation-set comparison. Commits: `79f7abb1` (probe/timing
harness), `5cc0a686` (fix).

**Attribution correction (T1.3).** The repeated cost is **per query, not per
session**: entity-name plans matched the whole 51,026-point inventory, and the
lane re-parsed and re-bound every point on every turn. The "cold 19s vs warm
3s" split in the RED set was query shape (all-domain vs single-domain plans),
not process warmth — the same query in a fresh session still paid 19.3s. The
fix removes the per-query O(inventory) work and moves the derived-state build
to boot (T3).
