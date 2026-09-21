# Verification: switch-embedding-model-to-qwen37-flash — preparation slice

Branch `docs/switch-embedding-model-change` (worktree
`.worktrees/embedding-switch-docs`), based on `v2/embedding-model-switch`
(`17404d7a`). This slice **prepares** the switch: the OpenSpec change, the rebuild
runbook and the precondition checker. No production code is touched; no index,
pack, database or live service is modified.

## 1. What this slice produced

| Artifact | Purpose |
|---|---|
| `openspec/changes/switch-embedding-model-to-qwen37-flash/{proposal,design,tasks,acceptance,spec-delta}.md` + `specs/canonical-v2-embedding-identity/spec.md` | the change contract; acceptance = the plan's §4 calibrated recall gate |
| `openspec/change-ledger.md` row | registration |
| `.agents/runs/embedding-model-switch-v2/rebuild-runbook.md` | the ordered window commands, derived from the scripts that produced run16 + v1.1 |
| `.agents/runs/embedding-model-switch-v2/precheck.sh` | the pre-window checker |
| `.agents/runs/switch-embedding-model-to-qwen37-flash/verification-contract.md` | the layer map (this file's sibling) |

## 2. Facts established or re-verified here (with the command that shows them)

| Fact | Evidence |
|---|---|
| The compatible route **serves the flash model**: HTTP 200, 1024 dims, 0.311 s, `model=qwen3.7-text-embedding-flash`, usage 20 prompt tokens (one call, key from the 0600 file, never printed) | the one-shot probe of `POST /compatible-mode/v1/embeddings` |
| The route candidates behave as slice 1 recorded without a key: compatible **401**, `/v1/embeddings` **404** | `precheck.sh` H1/H1a |
| The index is 51,026 points at 4096 dims and the file is 1,676,818,545 B; the 1024-dim rebuild is ≈418 MB (exactly ¼) | `np.load(vector_matrix.npz).meta`; `index_point` row count |
| The embedded text volume is 52,193,135 characters (mean 1,023/point, max 15,078, cjk share 0.265) — the basis of the TPM estimate | SQL over the live `lookup.sqlite3` (`json_extract(point_json,'$.embedded_content')`), 51,026 + 3,001 sampled rows |
| The pack seal's cost is measured, not guessed: `envelope_validate` 1926 s + `dogfood_open` 312 s (phase sum 40.4 min; v1.1 re-seal 42.08 min wall clock) | `.worktrees/data-rebuild/.agents/runs/full-column-serving-pack-rebuild/build-run16-pack-seal.log`; `.worktrees/release-v11/.../verification.md` |
| run16's build wall clock was **≈6.5 h** (22:05:52 → 04:35:35) | `.worktrees/data-rebuild/.agents/runs/full-column-serving-pack-rebuild/watchdog-run16.log` |
| The pack's recorded reader digest (`ebc22047…`) is reproduced by **pydantic 2.12.5** and *not* by the app-local venv's 2.11.7 (`90717887…`) ⇒ the window must pin the deployment interpreter | `reader_contract_digest()` computed in the live tree with three interpreters; the mounted pack's `manifest.json` |
| The pre-switch envelope identity (file sha `43735faa…`, size 8,303,007,285) and the pack/index identities (marker `b6f78a3b…`, lookup `2f3e69f4…`, relationships `b65794b0…`) are unchanged | `precheck.sh --full`: `OK=39 WARN=1 FAIL=0` |
| The recall gate's frozen artifacts match their recorded hashes (harness + 6 files) and the case files parse (25 + 12) | same run, G cluster |
| The runner's fixed envelope path in the switch line is currently free, but the *live* line's copy holds an older envelope (`candidate-s12a-20260722-r6`, 56,547,328 B) ⇒ the runbook's archive step is required | precheck C2 + reading the live tree's file |

## 3. Checks run in this slice

| Command | Result |
|---|---|
| `bash -n .agents/runs/embedding-model-switch-v2/precheck.sh` | syntax OK |
| `precheck.sh --offline --fast` (SWITCH_LINE → this worktree) | **OK=36 WARN=1 FAIL=0** — the warning is the app-local venv trap |
| `precheck.sh --offline --full` | **OK=39 WARN=1 FAIL=0**, 76 s wall clock |
| `precheck.sh --fast` (key path deliberately wrong) | **FAIL=1** (A5 credential) + `H1 401` / `H1a 404` / `H2 SKIP` — failure path and the no-key branch behave; exit 2 |
| `openspec validate switch-embedding-model-to-qwen37-flash --strict` | see §5 |
| live 18188 service | untouched: `/api/health` 200 at the start and end of this slice; only `GET` requests were made to it |

## 4. Not verified here (and where it lands)

* Everything in the change's `acceptance.md` with status `pending` — the rebuild,
  the seal, the gate and the cutover. They are the window's work.
* The `precheck.sh` H2 branch (keyed probe) was not executed **in the script** —
  the model question was answered by one standalone call before the script
  existed, and this slice deliberately stayed inside that one-call budget. The
  keyed branch is therefore code-reviewed, not executed; its request is
  byte-equivalent to the executed probe. Risk: low (same URL/body/parse), and the
  first keyed precheck run before the window will execute it.
* The batch-32 cap question (`--batch-probe`) is open and deliberately not
  answered here: it costs one more live call and belongs to the pre-window run.
* The merge (tasks T2.1–T2.5) does not exist yet: the parent's F1/F2 interaction
  requirements are written as tasks with named test files, not as verified facts.
* The gateway characteristics recorded in design §2.1 are the **lane's** repeat
  measurement (`.agents/runs/embedding-model-switch-v2/repeat-noise-measurement.json`,
  a sibling slice that landed after this branch's base `17404d7a`, lane tip
  `5a8b4a13`) plus this slice's single probe — referenced, not re-run here. The
  candidate bundle hashes in `precheck.sh` were re-checked against the lane tip and
  still match (`cdddcdfd…`, `45e45855…`).

## 5. OpenSpec validation

Recorded in the commit message and reproducible with:

```bash
cd .worktrees/embedding-switch-docs && openspec validate switch-embedding-model-to-qwen37-flash --strict
```
