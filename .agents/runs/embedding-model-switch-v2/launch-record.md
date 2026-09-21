# Launch record — fembed rebuild (embedding switch to `qwen3.7-text-embedding-flash`)

Runbook: `.worktrees/embedding-switch-docs/.agents/runs/embedding-model-switch-v2/rebuild-runbook.md`
Steps 0–5 executed **from the switch line** (`.worktrees/embedding-switch-line`,
branch `switch/embedding-model-to-qwen37-flash`), per the operator decision that
the build line's ported trees stay a documented fallback.
Date: 2026-09-22. Route: **dashscope-native** (option B).

## Identities

| Item | Value |
|---|---|
| release id | `candidate-v2-20260922-r1` |
| run id | `fembed-build-20260922-v1` |
| target database | `miroflow_candidate_v2_20260922_r1` (disposable, marker-owned) |
| index root (build form) | `/var/tmp/mirothinker-data-v2/index-v4` |
| index marker sha256 | `058c0bcfa905b46d3a3dcd56a10712de6eb69791b980d2a6ccfe8f441b0a3e5c` |
| staging root | `/var/tmp/mirothinker-data-v2/staging-v4` |
| embedding bundle | `.agents/runs/embedding-model-switch-v2/qwen3.7-text-embedding-flash-embedding-bundle-v1.json` (native, `content_sha256 67927ea060ec3036927376c7059aaa7d3140c33160b9be440556a19cd8d64ef3`, `batch_size 20`, document role) |
| envelope output | `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope.json` (switch line; was **free**, runbook step 2 is a no-op) |
| backups read | switch-line gate root `s2` + `s2b` (356 KB + 176 KB, manifests + restore verification) |
| rollback anchor | `.worktrees/data-rebuild/…/s12a/complete-candidate-build-envelope.json` (8,303,007,285 B) — read only, never moved |

## Exact command

```bash
# launcher (switch line, committed):
#   .agents/runs/full-column-serving-pack-rebuild/build-fembed-20260922.sh
cd /home/longxiang/MiroThinker/.worktrees/embedding-switch-line
setsid nohup bash .agents/runs/full-column-serving-pack-rebuild/build-fembed-20260922.sh \
  > .agents/runs/full-column-serving-pack-rebuild/build-fembed-20260922.log 2>&1 < /dev/null &
```

The launcher execs, with the credential read from the 0600 key file and never
inlined or printed:

```bash
CANONICAL_V2_EMBEDDING_API_KEY="$(cat /var/tmp/mirothinker-qianwen-api-key)" \
PYTHONUNBUFFERED=1 exec /home/longxiang/MiroThinker/.venv/bin/python \
  "$GATE_ROOT/s12a/complete_candidate_runner.py" \
  --database-url postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_v2_20260922_r1 \
  --expected-database miroflow_candidate_v2_20260922_r1 \
  --database-target-kind disposable \
  --accepted-backup-gate-root $SWITCH_LINE/.agents/runs/rebuild-canonical-v2-knowledge-platform \
  --source-manifest …/full-column-serving-pack-rebuild/source-build-manifest-p4.json \
  --source-manifest-sha256 a6e82fcd9dd5b2da22fd0c73cfe81b674ad04827092eb01fd4442956f70e184d \
  --candidate-staging-root /var/tmp/mirothinker-data-v2/staging-v4 \
  --index-root /var/tmp/mirothinker-data-v2/index-v4 \
  --index-marker-sha256 058c0bcfa905b46d3a3dcd56a10712de6eb69791b980d2a6ccfe8f441b0a3e5c \
  --candidate-release-id candidate-v2-20260922-r1 --run-id fembed-build-20260922-v1 \
  … 15 --source-batch-id … (runbook step 5 list, unchanged) \
  --model-version embedding=qwen3.7-text-embedding-flash \
  --recorded-decision-bundle …/s12a/recorded-decision-bundle-v1.json \
  --recorded-embedding-bundle …/embedding-model-switch-v2/qwen3.7-…-v1.json \
  --envelope-output …/s12a/complete-candidate-build-envelope.json \
  --accepted-original-milvus-path /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --accepted-original-milvus-sha256 43ef203e… \
  --accepted-original-milvus-record-sha256 df3715a0…
```

## Detached process

| Item | Value |
|---|---|
| PID | **2077915** (`/home/longxiang/MiroThinker/.venv/bin/python …/s12a/complete_candidate_runner.py`) |
| session | own (`sid=2077915`, `setsid`), reparented on shell exit |
| log | `.agents/runs/full-column-serving-pack-rebuild/build-fembed-20260922.log` |
| sampler | `.agents/runs/full-column-serving-pack-rebuild/build-fembed-20260922.watchdog.log` (2-minute samples) |

## First attempt failed in 12 s — the `src`-tree trap (recorded)

The first launch died with:

```
TypeError: load_content_addressed_embedding_adapter() got an unexpected keyword argument 'role'
```

Cause: the deployment venv installs `src` **editable from the live tree**
(`site-packages/_editable_impl_miroflow_agent.pth` →
`/home/longxiang/MiroThinker/apps/miroflow-agent`), and for a *script* invocation
Python puts the script's own directory on `sys.path[0]` — not the cwd. The runner
therefore imported the live tree's `canonical_v2` (no `role` parameter, no
candidate identity). Fix: the launcher exports
`PYTHONPATH=$SWITCH_LINE/apps/miroflow-agent` before the exec (PYTHONPATH precedes
`.pth` entries). Verified: with that line the loader resolves to the switch
line's file and its signature is `(path, *, role)`.

**Consequence for step 12 (cutover), must not be missed:** the live 18188 process
runs with cwd `.worktrees/canonical-v2-s11-consolidation` and no `PYTHONPATH`, so
its `src` comes from *its own* tree. The switched serve command must launch with
cwd (or `PYTHONPATH`) pointing at the switch line, otherwise the process would
serve the new pack with the **old** tree's `canonical_v2`.

## Pre-window precheck

`bash precheck.sh --full` (run before steps 3–4): **`OK=42 WARN=0 FAIL=0`,
`RESULT: READY`**, H2 authenticated probe `HTTP 200, dims=1024`.
Re-running it *after* steps 3–4 reports `FAIL=2` on exactly the two freshness
assertions the window deliberately consumes — `D1 index-v4 — already exists`,
`D1 staging-v4 — already exists`. That is the marker, the database and the
staging root the build is already using, not a regression.

## Step-6 trigger

When the log prints `envelope_sha256=…` (alongside `receipt_sha256=` and
`handoff_sha256=`), the build finished: proceed to step 6 (verify the vector
matrix) and then 7 (index conversion) / 8 (seal).

## Watch window (first 45 minutes, 2026-09-22 00:11 → 00:56)

Sampler: `.agents/runs/full-column-serving-pack-rebuild/build-fembed-20260922.watchdog.log`
(one line every 2 minutes, pid/state/cpu/rss/log-bytes/last-line).

| Time | Elapsed | CPU time | %CPU | RSS | Log bytes | Last line |
|---|---|---|---|---|---|---|
| 00:12 | 1:34 | 1:34 | 93% | 2.3 GB | 796 | `P4_MERGE_LEDGER {…}` |
| 00:20 | 9:35 | 9:35 | 98.8% | 3.8 GB | 1050 | `APPLICANT_BINDING_LEDGER …` |
| 00:30 | 19:35 | 19:35 | 99.3% | 8.1 GB | 1050 | same |
| 00:40 | 29:35 | 29:35 | 99.5% | 11.8 GB | 1050 | same |
| 00:50 | 39:35 | 39:35 | 99.6% | 11.8 GB | 1050 | same |
| 00:56 | 44:50 | 44:42 | 99.7% | 11.8 GB | 1050 | same |

* **Advancing, not stalled**: CPU time tracks wall clock at ~99% (single core),
  RSS grows with the restore then plateaus; the run is in the merge/restore
  phase, which prints little.
* **No error of any kind** in the log (`error|traceback|differ|exception|400|refus`
  → 0 hits). The two known window-killers cannot have fired yet: no gateway call
  has been made (`ss` shows zero sockets for the pid).
* **The batch-20 killer was disproved ahead of the embedding phase** by driving
  the build's own chain (`load_content_addressed_embedding_adapter(role="document")`
  → native adapter → gateway) with the 20 *longest* real documents from the live
  pack's lookup (read-only): 20 rows × 1024 dims, all non-zero, 1.605 s, HTTP 200
  — `.agents/runs/embedding-model-switch-v2/build-embedding-path-probe.json`.
* **The audit killer is structurally covered**: the running process's
  `PYTHONPATH` pins the switch line's app root (checked in `/proc/2077915/environ`,
  credential line never echoed), whose `index_projection_isolated.py` carries
  `_MIN_VECTOR_COSINE_SIMILARITY = 0.99` at line 76.
* Host head-room at 00:56: 396 GB RAM available (RSS 11.8 GB), `/var/tmp` 881 GB
  free, staging 107 MB, index root marker only.

