# Proposal: serving-index-process-scope

## Why

The serving process re-loads and re-verifies the local knowledge index on a
per-session basis, which shows up directly in first-answer latency. Measured on
the live entry (2026-09-15, run15 pack):

| Observation | Number | Evidence |
|---|---|---|
| vector-lane cost, **cold** | **18.7–30.6s** | 7 consecutive new sessions 00:53–00:59, every `turn=1` in `.agents/runs/close-workbook-gaps/turn-debug/` |
| vector-lane cost, **warm** | **3.0–3.2s** (later turns 0.1–0.9s) | two fresh sessions at 10:2x, same debug dir |
| full "fast-boot" snapshot open (`open_manifest_verified_index_snapshot`) | **~60s every time** (59.9 / 65.3 / 60.5s on a warm local copy) | measured on an isolated copy at `/var/tmp/scratch-index-warm` |
| — of which artifact hashing (`lookup.sqlite3` 638MB + `milvus.db` 1029MB) | **10.24s** | direct `sha256sum`, twice, same result |
| — Milvus checks | **~50s of timeouts** | the open emits `failed to get mvccTs from milvus server` every 60s (iterator.py:260) — a client that is not healthy, retried on a 60-second timeout, for a database the serving path never queries |
| query embedding (remote `100.64.0.27:18005`) | **0.03s** | 3 consecutive calls — **not** a factor |

User judgement (2026-09-15): *"把应该加载到内存中的东西在启动期加载是应该做的。
每次都加载浪费大量时间破坏用户体验是 bug"* — i.e. this is a defect, not a
design trade-off.

## What changes

1. **Load once per process, not once per session.** The snapshot / vector matrix
   / any index handle must live in a process-scoped cache keyed by
   `(index_root, marker_sha256, release_id)`, and must survive session forks.
2. **Warm it at boot.** The service pays the (now once-only) cost during start-up
   instead of on a user's first question.
3. **Keep a cheap mount-time identity check.** What actually needs proving at
   mount time is "the right pack is mounted, files are complete, nothing is
   truncated or stale" — marker + receipt identity + per-file size and
   first/last-block fingerprints. **Full 1.67GB re-hashing is not required on the
   query path**; run it once at boot and write a verification receipt.
4. **Stop paying for Milvus on the query path.** The serving read path never
   queries Milvus (it scores against the persisted `vector_matrix.npz`); the
   snapshot open's Milvus checks currently burn ~50s in timeouts. Either make
   the check cheap/optional or drop it from the serving path, keeping the
   pack-level binding checks.

## Out of scope / invariants

- **No change to retrieval semantics**: same lanes, same candidates, same
  evidence and citations for the same query. Acceptance requires identical
  evidence/citation sets on the probe queries plus a green replay gate.
- No change to the pack format, the serving command file, or the release
  pipeline. This is a serving-runtime change only.
- Auditability is preserved: the boot-time verification receipt (marker sha,
  per-file hashes, durations) is written to the log/evidence directory.

## Rollback

Code-only change on its own branch; rollback = redeploy the previous serving
commit and restart the unit (≈13 min pack load, unchanged).
