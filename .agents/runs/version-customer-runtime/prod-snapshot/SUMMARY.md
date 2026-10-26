# Customer runtime snapshot — 2026-10-26

Source: `root@100.64.0.96:/root/deploy/fullstack-v2/code` (not a git checkout).

## What this is

A byte-faithful copy of the deployed `apps/` tree, committed as
`hotfix/customer-20261026` off `switch/embedding-model-to-qwen37-flash`
(`67933138`). `run.sh` is snapshotted here (it configures the runtime env and is
not under `apps/`).

- `manifest.sha256` — sha256 of every file that differs from the parent commit
  (33 modified + 4 added = 37 files).
- `excluded-patch-residue.txt` — 49 hot-patch backup files (`.bak-*`, `.pre-*`)
  that were created on the host next to the source files. They are **not**
  committed: they are deployment residue, not source. Their names are the only
  record of the patch sequence before this snapshot.
- `run.sh` — `sha256 fd17c4e6…`.

## Lineages (why the deployed tree is not any single branch)

Comparing the 31 Python files changed on the host between 2026-10-21 and
2026-10-26 against `switch/embedding-model-to-qwen37-flash`:

| result | count | notes |
|---|---|---|
| identical | 9 | already in the serving branch |
| different | 18 | hot patches from 10-22 … 10-26 |
| absent from the branch | 4 | `excel_structure.py`, `excel_ingest.py`, `run_scheduled_job.py`, `news_connectors/deepseek.py` — only in the 10-23 snapshot of `codex/canonical-v2-s12a-ready` |

## Known limitations

- The copy is additive: files present in git but absent on the host were not
  deleted. `scripts/check_runtime_drift.py` reports both directions.
- `*/logs`, `dist`, `node_modules`, `__pycache__` were excluded.
- This branch is a **snapshot**, not a merge. Converging the lineages is a
  separate change.
