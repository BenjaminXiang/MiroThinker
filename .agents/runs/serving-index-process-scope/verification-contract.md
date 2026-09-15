# Verification contract: serving-index-process-scope

Status: contract frozen 2026-09-15 before any production-code edit.

## Claim under test

**The serving process must load and verify the local knowledge index once per
process, at boot — not once per session, and never on the user's first question.**

## RED artifacts (must exist before the fix)

Evidence already captured (this file's directory and the human analysis doc):

| RED evidence | Where |
|---|---|
| 7 consecutive new sessions each paying 18.7–30.6s in the vector lane on `turn=1` | `.agents/runs/close-workbook-gaps/turn-debug/*-01.json` (2026-09-15 00:53–00:59) |
| warm new sessions at 3.0–3.2s, same-session later turns 0.1–0.9s | `turn-debug-qpXKYyLhq1a0-*.json`, `turn-debug-iAkeGULNt1sQ-*.json` |
| "fast-boot" snapshot open ≈ **60s every time** (59.9 / 65.3 / 60.5s) on a warm copy | `/var/tmp/scratch-index-warm` measurement, 2026-09-15 10:31 |
| artifact hashing 1.67GB = **10.24s** | `sha256sum` of index-v2 lookup+milvus, twice |
| Milvus check burning ~50s of 60s timeouts (`failed to get mvccTs`) | snapshot-open log output, same run |
| query embedding = **0.03s** (not a factor) | 3 consecutive calls to `100.64.0.27:18005/v1/embeddings` |

## GREEN criteria

1. Instrumented run from the **same `serve-*.sh` command file** on a scratch port
   shows: first session ≤1s vector lane, second session ≤1s, and **exactly one**
   index open per process lifetime (counter).
2. Boot log/receipt records the one-time load with durations (audit preserved).
3. Negative mount test: a truncated/corrupted artifact copy is rejected at mount
   time with a clear error (cheap identity check actually works).
4. `mvccTs`-style 60s timeouts absent from the serving path.
5. Replay gate **7/7** and the probes (「字节跳动」→ ByteDance Ltd.;
   「优必选有哪些专利」→ local CN numbers) unchanged, with **identical
   evidence/citation sets** for the probe queries.

## Measurement protocol (no hand-rolled parameters)

- Scratch instance: same command file mechanism as production
  (`env $(cat serve-<port>-command-*.sh)`), never ad-hoc flags — a hand-rolled
  scratch launch already produced one false-regression alarm on 2026-09-14.
- Comparisons use `turn-debug` lane timings (`lane_timings.vector`) for the same
  query, first turn of a fresh session vs second turn, and across two fresh
  sessions.
- Boot delta is measured from the unit's `ActiveEnterTimestamp` to the first 200
  on `/api/health`.

## Danger notes

- The live service must keep serving while this work happens: implement on its
  own branch/worktree, verify on a scratch port, then deploy by merging +
  restarting the unit (never edit the live worktree in place).
- Do not weaken `fail-closed`: if an artifact cannot be identified, refuse to
  serve (mount-time), but do not re-prove identity on every query.
