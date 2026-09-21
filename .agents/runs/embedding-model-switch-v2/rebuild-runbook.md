# Rebuild runbook — serving-side embedding switch to `qwen3.7-text-embedding-flash`

Change: `switch-embedding-model-to-qwen37-flash`
(`openspec/changes/switch-embedding-model-to-qwen37-flash/`, design §5).
Audience: the operator who runs the window. Every command below is derived from
the scripts that actually produced run16 and the v1.1 pack — **not** from memory:

| Derived from | Path |
|---|---|
| runner invocation, index marker, disposable DB | `.worktrees/data-rebuild/.agents/runs/full-column-serving-pack-rebuild/build-run16.sh` |
| pack sealer invocation (v2 contract) | `.worktrees/data-rebuild/.agents/runs/full-column-serving-pack-rebuild/build_run16_serving_pack.sh` |
| re-seal against merged code (v1.1) | `.worktrees/release-v11/.agents/runs/release-v11/reseal-command.sh` |
| v1 → v2 index conversion | `.worktrees/slim-serving-pack/.agents/runs/drop-milvus-from-serving-pack/convert_index_to_v2.py` |
| serving bundle generator | `.worktrees/data-rebuild/.agents/runs/full-column-serving-pack-rebuild/generate_run16_serving_bundle.py` |
| fast-path check | `.worktrees/release-v11/.agents/runs/release-v11/fastpath-check.py` |
| recall gate commands | `.worktrees/recall-regression/.agents/runs/embedding-model-switch/protocol.md` |
| live serve command (cutover template) | `.worktrees/canonical-v2-s11-consolidation/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18188-command.sh` |

Hard rules for the window: **never restart, kill or rebind the live 18188 service**
until step 12; never delete or rewrite the pre-switch pack/index/bundle (they are
the rollback anchor); never print a secret (the key is read from a file, `$(cat …)`
only); one writer per tree.

### Interpreter discipline (read before typing any command)

The pack records `reader_contract_sha256 = sha256(python + pydantic + every
canonical_v2/*.py)`, and the boot compares it: an equal digest takes the ~120 s
fast path, a different one replays the reconstruction on **every** boot (~285 s).
Measured on this host today:

| Interpreter | pydantic | digest (live tree) |
|---|---|---|
| `/home/longxiang/MiroThinker/.venv/bin/python` (deployment venv) | 2.12.5 | `ebc22047…` = the digest the mounted pack records |
| `.worktrees/canonical-v2-s11-consolidation/.venv/bin/python` | 2.12.5 | `ebc22047…` (same) |
| `.worktrees/…/apps/miroflow-agent/.venv/bin/python` (created by `uv run` inside `apps/miroflow-agent`) | **2.11.7** | `90717887…` — would silently cost the replay |

`uv run` picks its environment from the current directory, so the same command can
land on either pair. The window therefore **pins the deployment interpreter** and
does not use bare `uv run` for the build/seal steps:

```bash
DEPLOY_VENV=/home/longxiang/MiroThinker/.venv      # CPython 3.12.12 + pydantic 2.12.5
DEPLOY_PY="$DEPLOY_VENV/bin/python"
"$DEPLOY_PY" -c "import sys,pydantic;print(sys.version.split()[0], pydantic.VERSION)"   # expect: 3.12.12 2.12.5
```

The precheck enforces this pair and warns when a worktree-local `.venv` with a
different pydantic exists.

---

## 0. Variables and prerequisites

```bash
# the merged switch line (created by T2.1; see design §6 for the merge order)
SWITCH_LINE=/home/longxiang/MiroThinker/.worktrees/embedding-switch-line
GATE_ROOT="$SWITCH_LINE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
RUN_ROOT="$SWITCH_LINE/.agents/runs/full-column-serving-pack-rebuild"
RUNNER="$GATE_ROOT/s12a/complete_candidate_runner.py"
SEALER="$GATE_ROOT/s12c/build_serving_pack.py"

RUNS="$SWITCH_LINE/.agents/runs/embedding-model-switch-v2"
BUNDLE_COMPAT="$RUNS/qwen3.7-text-embedding-flash-embedding-bundle-v1-openai-compat.json"   # 45e45855…  (chosen route)
BUNDLE_NATIVE="$RUNS/qwen3.7-text-embedding-flash-embedding-bundle-v1.json"                # cdddcdfd…  (fallback)

KEY_FILE=/var/tmp/mirothinker-qianwen-api-key        # 0600, outside the repo

# the new release triple (fill the date when the window opens)
DATE=20260922
RELEASE_ID="candidate-v2-$DATE-r1"
TARGET_DB="miroflow_candidate_v2_$DATE_r1"
RUN_ID="fembed-build-$DATE-v1"
STAGING=/var/tmp/mirothinker-data-v2/staging-v4
INDEX=/var/tmp/mirothinker-data-v2/index-v4            # build form (with milvus.db)
INDEX_V2=/var/tmp/mirothinker-data-v2/index-v4-v2       # serving form (no milvus.db)
PACK_DIR=/var/tmp/mirothinker-data-v2/serving-pack-fembed-v1
ENVELOPE="$GATE_ROOT/s12a/complete-candidate-build-envelope.json"
ENVELOPE_ARCHIVE="$GATE_ROOT/s12a/complete-candidate-build-envelope-pre-fembed.json"

# the rollback anchor (do not touch)
OLD_PACK=/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound
OLD_INDEX=/var/tmp/mirothinker-data-v2/index-v3-v2
OLD_MARKER_SHA=b6f78a3b1e28c280860a4210bfad286ef65090e758de5b876d7f639eefaa8373
```

Prerequisites (all checked by `precheck.sh`, step 1):

1. `precheck.sh` is all-`OK` (rollback anchor hashes, fresh target paths, Postgres,
   interpreter 3.12.12 + pydantic 2.12.5, disk, endpoint, recall artifacts).
2. The switch line exists and its merge-interaction tests are green (tasks T2.1/T2.4/T2.5).
3. `CANONICAL_V2_EMBEDDING_API_KEY` obtainable from `$KEY_FILE` (or a managed-secret
   entry), and the key rotated if it was ever exposed (T3.2).
4. The disposable Postgres container `canonical-v2-s12c-pg-20260726-r8` is up.
5. `docs/plans/` untouched by this work.

---

## 1. Precheck

```bash
bash "$RUNS/precheck.sh"                 # ~50 s: hashes the 8.3 GB run16 envelope (measured 76 s with --full)
bash "$RUNS/precheck.sh" --fast          # ~1 s: sizes only
bash "$RUNS/precheck.sh" --batch-probe   # + one 32-text call: answers the batch-cap question
```

Expected: every line `[OK]`, and in the endpoint section one authenticated probe —
`HTTP 200, dims=1024` (this is the single live call; the script never prints the key).
Any `[FAIL]` stops the window (exit 2). Measured today on this host with the switch
line not yet created: `OK=36 WARN=1 FAIL=0` with `SWITCH_LINE` pointed at an
existing tree, the only warning being the app-local venv trap (§ interpreter
discipline); with `--full` the same run took 76 s (the 8.3 GB envelope + 0.9 GB
lookup + 3.5 GB relationships hashes). The endpoint branch was exercised live
without a key (`H1 compatible route — 401`, `H1a /v1/embeddings — 404`, `H2 … stays
open`); the model question itself was answered once, outside the script, by the
equivalent one-shot probe (HTTP 200, `dims=1024`, 0.311 s) — a keyed precheck run
reproduces it through `H2`.

---

## 2. Archive whatever occupies the runner's fixed envelope path

The runner writes `$ENVELOPE` into the gate root of the tree it runs from, and
refuses to run when both the fixed path and its archive already exist; the fixed
path is therefore freed first (never deleted).

The file sitting there depends on the branch: measured today, the **live tree's**
fixed path holds an *older* candidate envelope (`candidate-s12a-20260722-r6`,
56,547,328 B, file sha256 `ab21c0a6…`) that the switch line inherits. The **run16**
envelope — the identity record of the release currently served — lives in the
`data-rebuild` worktree's fixed path (8,303,007,285 B, file sha256
`43735faa…`, content sha `a8440bdf…`) and is **not** the file this step moves: it
is the rollback anchor's record, checked by `precheck.sh` cluster C, and it must
stay untouched.

```bash
# (a) the pre-switch release's record — verify, never move
python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" \
  /home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope.json
# expect 43735faa9300fc834bffcea44304462f30128d5dfa0eb048e76075a115ccea20

# (b) free the switch line's fixed path (records the identity of whatever it held)
[[ -e "$ENVELOPE" ]] || { echo "fixed path already free"; }
[[ -e "$ENVELOPE_ARCHIVE" ]] && { echo "archive name already taken — resolve by hand"; exit 2; }
sha256sum "$ENVELOPE" >/tmp/envelope-pre-fembed.sha256
mv "$ENVELOPE" "$ENVELOPE_ARCHIVE"
cat /tmp/envelope-pre-fembed.sha256    # paste the identity into the window log
```

The guard in `build-run16.sh` that compared specific archive names is script-local;
this run's wrapper must archive whatever occupied the path and re-check that the
fixed path is free before launching (a new build would otherwise overwrite the
previous envelope in place).

---

## 3. Fresh index marker

```bash
cd "$SWITCH_LINE/apps/miroflow-agent"

MARKER_SHA="$(
  "$DEPLOY_PY" - <<PY
import sys
from pathlib import Path
sys.path.insert(0, ".")
from src.data_agents.canonical_v2.index_projection_isolated import prepare_isolated_index_target
target = prepare_isolated_index_target(
    root=Path("$INDEX"),
    target_id="index:$RELEASE_ID",
    release_id="$RELEASE_ID",
    backup_gate_root=Path("$GATE_ROOT"),
    forbidden_milvus_paths=(Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db"),),
)
print(target.marker_sha256)
PY
)"
echo "index marker sha256=$MARKER_SHA"     # record it; the sealer and the serve command both need it
```

## 4. Disposable target database

```bash
cd "$SWITCH_LINE/apps/miroflow-agent"
"$DEPLOY_PY" - <<PY
import psycopg
TARGET = "$TARGET_DB"
MARKER = f"miroflow:destructive-target:v1:disposable:{TARGET}"
admin = psycopg.connect("postgresql://miroflow@127.0.0.1:55458/postgres", autocommit=True)
existing = admin.execute(
    "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = %s", (TARGET,)
).fetchone()
if existing is not None:
    marker = existing[0]
    if marker != MARKER:
        raise SystemExit(f"refusing to reset {TARGET}: marker={marker!r}")
    admin.execute(f"DROP DATABASE {TARGET} WITH (FORCE)")
admin.execute(f"CREATE DATABASE {TARGET}")
admin.execute(f"COMMENT ON DATABASE {TARGET} IS '{MARKER}'")
print("target database created and marked")
PY

CANONICAL_V2_BACKUP_GATE_ROOT="$GATE_ROOT" \
ALEMBIC_DATABASE_URL="postgresql+psycopg://miroflow@127.0.0.1:55458/$TARGET_DB" \
ALEMBIC_EXPECTED_DATABASE="$TARGET_DB" \
ALEMBIC_TARGET_KIND=disposable \
"$DEPLOY_VENV/bin/alembic" -c canonical_v2_alembic.ini upgrade head
```

## 5. The build — re-embed 51,026 points with the candidate model

The embedding happens **inside** the official runner's index phase
(`_write_milvus_projection` → `embed_batch` over every point, then
`write_persisted_vector_matrix`). Nothing else changes: same manifest, same
restore root, same decision bundle — only `--recorded-embedding-bundle` and
`--model-version embedding=…`.

```bash
cd "$SWITCH_LINE/apps/miroflow-agent"
CANONICAL_V2_EMBEDDING_API_KEY="$(cat "$KEY_FILE")" \
PYTHONUNBUFFERED=1 nohup "$DEPLOY_PY" "$RUNNER" \
  --database-url "postgresql://miroflow@127.0.0.1:55458/$TARGET_DB" \
  --expected-database "$TARGET_DB" \
  --database-target-kind disposable \
  --accepted-backup-gate-root "$GATE_ROOT" \
  --source-manifest "$RUN_ROOT/source-build-manifest-p4.json" \
  --source-manifest-sha256 a6e82fcd9dd5b2da22fd0c73cfe81b674ad04827092eb01fd4442956f70e184d \
  --candidate-staging-root "$STAGING" \
  --index-root "$INDEX" \
  --index-marker-sha256 "$MARKER_SHA" \
  --candidate-release-id "$RELEASE_ID" \
  --run-id "$RUN_ID" \
  --source-batch-id s12a-released-objects-full-v1 \
  --source-batch-id s12c-r7-company-knowledge-v1 \
  --source-batch-id s12c-r7-company-workbook-supplement-v1 \
  --source-batch-id s12c-r7-paper-identifiers-v1 \
  --source-batch-id s12c-r7-patent-identifiers-v1 \
  --source-batch-id s12c-r7-professor-company-roles-v1 \
  --source-batch-id s12e-professor-backfill-v1 \
  --source-batch-id s12f-company-backfill-v1 \
  --source-batch-id s12f-applicant-binding-v1 \
  --source-batch-id p4-company-full-v1 \
  --source-batch-id p4-patent-full-v1 \
  --source-batch-id p4-paper-salvage-v1 \
  --source-batch-id p4-professor-full-v1 \
  --source-batch-id p4-professor-paper-links-v1 \
  --source-batch-id p4-applicant-binding-full-v1 \
  --parser-version historical_jsonl=v1 \
  --parser-version historical_xlsx=v1 \
  --parser-version released_objects_sqlite=canonical-v2-s12a-full-table-v1 \
  --policy-version path_eligibility=path-eligibility-v1 \
  --policy-version released_objects_mapper=canonical-v2-released-objects-mapper-v2 \
  --model-version embedding=qwen3.7-text-embedding-flash \
  --recorded-decision-bundle "$GATE_ROOT/s12a/recorded-decision-bundle-v1.json" \
  --recorded-embedding-bundle "$BUNDLE_COMPAT" \
  --envelope-output "$ENVELOPE" \
  --accepted-original-milvus-path /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --accepted-original-milvus-sha256 43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc \
  --accepted-original-milvus-record-sha256 df3715a0be8560d523ce2abb589bdaf690e0fe07babcad26c03a4da0ad8cbe6b \
  > "$RUN_ROOT/build-fembed-$DATE.log" 2>&1 &
```

Watch it the way run16 was watched (`watchdog-run16.sh` is the template: 5-minute
samples of pid/state/cpu/written-bytes, a stall detector, and a one-shot failure
dossier). Success lines in the log:

```
candidate_release_id=candidate-v2-<DATE>-r1
receipt_sha256=…
handoff_sha256=…
envelope_sha256=…            # the envelope's *content* sha (not the file bytes)
```

> **No checkpoint inside the embedding pass.** `_BatchingEmbeddingAdapter` keeps an
> in-memory de-duplicated cache (16,384 entries) and performs no retries; a
> transport error aborts the build, and the resume adapters
> (`s12b/resume_r3_candidate.py` and its siblings) are hand-pinned to a specific
> release/run — a mid-run failure is a fresh rebuild unless someone writes a new
> resume wrapper for this run. Budget accordingly and keep the gateway key/quota
> healthy before starting.

## 6. Verify the new vector matrix

```bash
cd "$SWITCH_LINE/apps/miroflow-agent"
"$DEPLOY_PY" - <<PY
import numpy as np, json
d = np.load("$INDEX/vector_matrix.npz", allow_pickle=True)
meta = json.loads(str(d["meta"].item()))
print(meta)                      # expect dimension=1024, point_count=51026, model qwen3.7-text-embedding-flash
print(np.asarray(d["matrix"]).shape)
PY
```

Expect: `dimension: 1024`, `point_count: 51026` (the same set the pre-switch matrix
had), `embedding_model_id: qwen3.7-text-embedding-flash`, file ≈420 MB (vs the
pre-switch 1,676,818,545 B).

## 7. Convert the index to the v2 (no-Milvus) serving form

The v2 sealer refuses a v1 index root (measured: attempt 2 of the run16 seal failed
with "v2 seal requires a converted index root"), so this step is mandatory.

```bash
cd "$SWITCH_LINE/apps/miroflow-agent"
"$DEPLOY_PY" "$SWITCH_LINE/.agents/runs/drop-milvus-from-serving-pack/convert_index_to_v2.py" \
  --source-root "$INDEX" \
  --dest-root "$INDEX_V2" | tee /var/tmp/mirothinker-data-v2/index-v4-v2-convert.log
```

Record the printed `conversion_report`: dest lookup bytes/sha256, dest marker
sha256, removed Milvus bytes. The converter is read-only against the source root;
a failed conversion leaves a partial destination that must be removed before
retrying. For reference, run16's conversion report:
`dest_lookup_bytes 896270336`, `removed_milvus_bytes 1078018048`,
`dest_marker_sha256 b6f78a3b…` (the value that ended up in the live serve command).

> The converter's thin CLI is not present on older build branches (the run16 tree
> lacked `convert_isolated_index_to_v2`); the switch line has it. Do not run the
> conversion from the `data-rebuild` worktree.

## 8. Seal the serving pack (v2 contract)

Must run **from the switch line with the deployment interpreter** — the pack
records `reader_contract_sha256` = `sha256(python + pydantic + every
canonical_v2/*.py)`, and a boot whose reader digest differs pays the ~285 s
reconstruction replay instead of the ~120 s fast path.

```bash
cd "$SWITCH_LINE/apps/miroflow-agent"
EXPECTED_MARKER_SHA256="$("$DEPLOY_PY" -c "import hashlib;print(hashlib.sha256(open('$INDEX_V2/.canonical-v2-isolated-index-target.json','rb').read()).hexdigest())")"

"$DEPLOY_PY" "$SEALER" \
  --envelope "$ENVELOPE" \
  --index-root "$INDEX_V2" \
  --pack-dir "$PACK_DIR" \
  --expected-release-id "$RELEASE_ID" \
  --generator-run-id "fembed-pack-$DATE-v1" \
  --pack-schema-version canonical-v2-serving-pack-v2 \
  2>&1 | tee "$RUN_ROOT/pack-seal-fembed-$DATE.log"
```

Preconditions the sealer/its wrapper enforce: pack dir must not exist; envelope
regular file; index root regular dir with a marker; sealer must accept
`--pack-schema-version`. Record the `phase=…` lines (run16: `envelope_validate`
1926 s, `dogfood_open` 312 s; phase sum 40.4 min, and the v1.1 re-seal measured
42.08 min wall clock) and the manifest sha256. `EXPECTED_MARKER_SHA256` is only
cross-checked by the wrapper logic — the sealer itself reads the marker from the
index root.

## 9. Verify the pack identity and the boot fast path

```bash
cp /home/longxiang/MiroThinker/.worktrees/release-v11/.agents/runs/release-v11/fastpath-check.py "$RUN_ROOT/"
"$DEPLOY_PY" "$RUN_ROOT/fastpath-check.py" --pack "$PACK_DIR" --verify-reconstruction no
```

(The copy matters: the script derives the code tree it tests from its own location —
`parents[3]/apps/miroflow-agent` — so a copy inside the switch line tests the switch
line's reader, and nothing else.)

Then boot the pack read-only on a scratch port (step 11's recipe, without the gate
flags first) and check the mount receipt written next to the pack
(`"$PACK_DIR".mount-receipt.json`): `index_marker_sha256` = step 7's marker,
`pack_manifest_sha256` = step 8's manifest hash, `verification: receipt`,
`mount_seconds` in the ~120 s class (a ~285 s mount means the reader digest does
not match the sealing tree). **Never** point the live 18188 process at the new pack
before step 12.

## 10. New serving bundle

```bash
cp "$RUN_ROOT/generate_run16_serving_bundle.py" "$RUN_ROOT/generate_fembed_serving_bundle.py"
# edit ONLY the release-bound identities + embedding_model_id:
#   SOURCE  = ../rebuild-canonical-v2-knowledge-platform/s12g/serving-bundle-run16.json
#   OUTPUT  = ../rebuild-canonical-v2-knowledge-platform/s12g/serving-bundle-fembed.json
#   RELEASE_ID / DATABASE_NAME / INDEX_ROOT / ENVELOPE / PACK_DIR / PACK_GENERATOR_RUN_ID
#   embedding_model_id = "qwen3.7-text-embedding-flash"
EXPECTED_MARKER_SHA256="$("$DEPLOY_PY" -c "import hashlib;print(hashlib.sha256(open('$INDEX_V2/.canonical-v2-isolated-index-target.json','rb').read()).hexdigest())")" \
  "$DEPLOY_PY" "$RUN_ROOT/generate_fembed_serving_bundle.py"
sha256sum "$GATE_ROOT/s12g/serving-bundle-fembed.json"   # record: the serve command needs --recorded-serving-bundle-sha256
```

## 11. Recall non-regression gate (blocking)

Boot the switched scratch instance (spare port, own state dirs, the gate flags) —
template: `.worktrees/recall-regression/.agents/runs/embedding-model-switch/serve-18295-command.sh`,
which is a copy of the live command with only port + state paths rebased. Two
adaptations for this run:

* the launcher and the paths must be the **switch line's** (new pack, new index
  root, new embedding bundle), i.e. the same command the cutover will install —
  a scratch boot of the *pre-switch* tree would measure the wrong code;
* add the gate flags below (the baseline recipe did not set them, so the switched
  run must, or the diff reports REVIEW coverage for every case).

```bash
CANONICAL_V2_TURN_DEBUG_DIR=/var/tmp/fembed-296/turn-debug
TURN_TRACE_DIR=/var/tmp/fembed-296/turn-trace
```

Then run the gate exactly as `protocol.md` §3 specifies (commands reproduced in
`acceptance.md`): warm-up pass → discard; judged pass → `after.json`; then

```bash
cd apps/admin-console && uv run python scripts/eval_recall_canonical_v2.py \
  --diff ../../.agents/runs/embedding-model-switch/baseline.json ../../.agents/runs/embedding-model-switch/after.json
cd apps/admin-console && uv run python scripts/eval_recall_canonical_v2.py \
  --diff ../../.agents/runs/embedding-model-switch/control.json  ../../.agents/runs/embedding-model-switch/after.json
```

(The harness's own `uv run` here belongs to the **recall worktree's
`apps/admin-console` project** — a separate interpreter/env from the pack's reader
digest — and the commands are the frozen protocol's, verbatim.)

Exit codes: 0 PASS / 1 FAIL / 2 REVIEW. **FAIL ⇒ do not cut over.** REVIEW rows are
decided by hand and recorded with the case, layer and reason. When the new pack
lives in its own directory, the scratch boot rewrites that pack's mount receipt
(same identity, new `generated_at`/`mount_seconds`) — expected, and it does not
touch the live pack's receipt.

## 12. Cutover and rollback

Cutover = a new serve-command file + restart. Take the live file as the template
(`…/s12g/serve-18188-command.sh`) and change exactly these fields:

| Field | Pre-switch | After cutover |
|---|---|---|
| launcher tree | `.worktrees/canonical-v2-s11-consolidation/…/s12e/serve_s12e_port.py` | **`$SWITCH_LINE/…/s12e/serve_s12e_port.py`** |
| `--serving-pack` | `…/serving-pack-run16-readerbound` | `…/serving-pack-fembed-v1` |
| `--index-root` | `…/index-v3-v2` | `…/index-v4-v2` |
| `--index-marker-sha256` | `b6f78a3b…` | step 7's marker |
| `--model-version embedding=` | `Qwen/Qwen3-Embedding-8B` | `qwen3.7-text-embedding-flash` |
| `--recorded-embedding-bundle` | `…/s12c/qwen-embedding-bundle-v1.json` | `$BUNDLE_COMPAT` |
| `--recorded-serving-bundle` (+ sha) | `…/s12g/serving-bundle-run16.json` (+ `0a09aecde9…`) | `…/s12g/serving-bundle-fembed.json` (+ step 10's sha) |
| `--candidate-release-id`, `--run-id` | run16 values | `$RELEASE_ID`, `$RUN_ID` |
| `--database-url`, `--expected-database` | `miroflow_candidate_v2_20260916_r1` | `$TARGET_DB` |
| env prefix | — | add `CANONICAL_V2_EMBEDDING_API_KEY="$(cat /var/tmp/mirothinker-qianwen-api-key)"` |

Unchanged on purpose: `--database-target-kind disposable`,
`--accepted-backup-gate-root`, `--source-manifest` + sha, the 15 `--source-batch-id`
values, the `--parser-version`/`--policy-version` pairs, the accepted-original-milvus
triple, `CANONICAL_V2_ACCESS_LOG_DB`, `CANONICAL_V2_CORRECTIONS_DB`,
`CANONICAL_V2_MANUAL_RECALL_DIR`, `CHAT_CONTEXTUAL_INTERPRETATION=on`.

```bash
cp …/s12g/serve-18188-command.sh …/s12g/serve-18188-command.pre-fembed.$(date +%Y%m%d-%H%M%S).sh   # rollback copy
# write the new file, then restart 18188 the way the line is normally restarted
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18188/api/health     # expect 200
```

Rollback (drill it in the window, in both directions):

```bash
cp …/s12g/serve-18188-command.pre-fembed.<ts>.sh …/s12g/serve-18188-command.sh
# restart 18188; confirm the pre-switch release id / index marker / embedding model are served
```

No rebuild, no backup restore: the old pack and both index roots were never
modified.

---

## Estimates

### Embedding pass (the only genuinely new cost)

| Input | Value | Source |
|---|---|---|
| points to embed | 51,026 | live `vector_matrix.npz` meta + `index_point` row count |
| batch size / workers | 32 / 32 | candidate bundle |
| calls | ⌈51,026 ÷ 32⌉ = **1,595** | derived |
| per-call latency | 0.204 s median / 0.232 s p95 (30 measured calls, compatible route); 0.311 s for the first cold call; 0.28 s in the plan | `repeat-noise-measurement.json`, this slice's probe |
| latency-bound wall clock | 1,595 × 0.204 ÷ 32 ≈ **10 s** | not binding |
| RPM 24,000 | 1,595 calls total ≈ 80 calls/min over 20 min | not binding |
| **TPM 1,000,000** | **binding** | plan §1 |
| embedded text volume | **52,193,135 characters** (mean 1,023/point, max 15,078, min 97) | measured from the live `index_point.point_json` |
| token volume | **≈20–35 M** (1.5–2.5 chars/token, mixed zh/en; cjk share 0.265) | derived — see caveat |
| **embedding pass wall clock** | **20–35 min at the ceiling, 30–60 min realistic; ≈2.5 h worst case** | derived |

Caveat on the token estimate: the tokenizer is not measurable offline. The two
anchors are (a) the live probe — 20 prompt tokens for a 6-character Chinese query,
which read literally implies up to 3.3 tokens/char and would put the pass at
2.5 h+; and (b) Qwen-family tokenizer behaviour on mixed zh/en corpora
(1.5–2.5 chars/token). Plan the window with **1 h for the pass and 3 h as the
contingency**, and read the gateway's own usage ledger afterwards.

Second caveat, measured on the lane: **the gateway is stochastic** — the same text
embedded twice scores repeat cosine ≥ 0.9988 (30 calls, compatible route), so the
rebuild's vectors are not reproducible byte-for-byte. Nothing in the pipeline
compares vectors for equality (the identity checks compare model id, dimension and
point-set), and the recall gate is the only bound on the semantic effect; do not
"fix" a differing vector by re-embedding during the window.

**Whole window**: run16's build took **≈6.5 h** (22:05:52 → 04:35:35, watchdog log;
the plan's planning figure is 8 h), the seal **42 min**, the conversion **≈5 min**,
two scratch boots **≈5 min each**, two gate passes **≈16–24 min**. Budget **7–9 h**
end to end, with the rebuild itself as the only long block.

### Quota

* Gateway embedding: ≈20–35 M tokens total (≈1,595 calls). One rebuild's worth;
  a second attempt doubles it.
* Recall gate: 2 passes × 37 turns ≈ **80 LLM-bearing turns**, plus the web
  provider calls the protocol records per pass (measured: 323 cold / 94 warm
  live provider calls, ~260 cache hits warm). The serving path's own LLM calls
  are not observable from the service — take the gateway figure.
* Web providers used by the *serving* smoke query: negligible.

### Disk

| Artifact | Pre-switch | After |
|---|---|---|
| `vector_matrix.npz` | 1,676,818,545 B (1.68 GB) | **≈418 MB** (51,026 × 1024 × float64) — exactly ¼ |
| index root, build form | 3.42 GB (`index-v3`: lookup 668 MB + milvus 1.08 GB + matrix 1.68 GB) | **≈1.5 GB** (`index-v4`: milvus vector payload ¼ → ≈0.45 GB) |
| index root, serving form | 2.57 GB (`index-v3-v2`) | **≈1.3 GB** (`index-v4-v2`: lookup 896 MB + matrix 418 MB) |
| serving pack | 4.38 GB (+`relationships.json` 3,477,354,956 B) | **≈4.4 GB — unchanged** (the pack is dominated by relationships, not vectors) |
| envelope | 8,303,007,285 B (archived, moved) | ≈same size, same directory (/home) |

Free-space floor for the window (precheck enforces 25 GB on `/var/tmp` and 15 GB on
the worktree filesystem): new index roots ≈2.9 GB, new pack ≈4.4 GB, staging
≈0.2 GB, new envelope ≈8.3 GB on `/home`; the pre-switch artifacts stay (≈7 GB).

### Rollback cost

Minutes: restore one command file, restart, confirm the pre-switch release id /
marker / embedding model in the receipt and `/api/health`. Nothing to rebuild and
nothing to restore from backup.
