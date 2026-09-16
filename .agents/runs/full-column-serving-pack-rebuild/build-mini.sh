#!/usr/bin/env bash
# Mini rehearsal build: s12f known-good base + ONE p4 batch (professor_full).
# Purpose: exercise the WHOLE pipeline (including p4 merge code and every
# post-domain phase) at reduced scale so downstream landmines surface in
# hours instead of 30h full runs. Fully isolated from the full-column run:
# own database, own staging/index roots, own gate-root copy, own envelope.
set -Eeuo pipefail

WORKTREE=/home/longxiang/MiroThinker/.worktrees/data-rebuild
RUN_ROOT="$WORKTREE/.agents/runs/full-column-serving-pack-rebuild"
REAL_GATE_ROOT="$WORKTREE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
GATE_ROOT="$RUN_ROOT/mini_gate_root"
APP_ROOT="$WORKTREE/apps/miroflow-agent"
RUNNER="$REAL_GATE_ROOT/s12a/complete_candidate_runner.py"
MANIFEST="$RUN_ROOT/source-build-manifest-p4-mini.json"
DATABASE=miroflow_candidate_v2_mini_r1
RELEASE=candidate-v2-mini-20260821-r1
RUN_ID=p4-mini-20260821-v1
ENVELOPE="$GATE_ROOT/s12a/complete-candidate-build-envelope.json"
BUILD_LOG="$RUN_ROOT/build-mini.log"
DATA_ROOT=/var/tmp/mirothinker-data-mini

if [[ -e "$ENVELOPE" ]]; then
  echo "mini envelope already exists: $ENVELOPE" >&2
  exit 2
fi

# Independent gate root copy (s2/s2b control files are content-identical so
# every pinned hash check passes; s12a slot hosts the mini envelope).
mkdir -p "$GATE_ROOT/s12a"
rm -rf "$GATE_ROOT/s2" "$GATE_ROOT/s2b"
cp -r "$REAL_GATE_ROOT/s2" "$REAL_GATE_ROOT/s2b" "$GATE_ROOT/"

# Marker-bound reset of the mini staging/index roots (same semantics as the
# full build script, bound to the MINI identity).
python3 - "$DATA_ROOT" "$RUN_ID" "$RELEASE" "$MANIFEST" <<'PY'
import json
import shutil
import sys
from pathlib import Path

data_root, run_id, release, manifest_path = sys.argv[1:5]
manifest_sha = json.loads(Path(manifest_path).read_text())["content_sha256"]
expected = {
    "schema_version": "canonical-v2-candidate-staging-marker-v1",
    "run_id": run_id,
    "candidate_release_id": release,
    "source_manifest_sha256": manifest_sha,
}
for name in ("staging-v1", "index-v1"):
    root = Path(data_root) / name
    if not root.exists():
        continue
    marker_path = root / ".canonical-v2-staging.json"
    try:
        marker = json.loads(marker_path.read_text()) if marker_path.exists() else None
    except (OSError, json.JSONDecodeError):
        sys.exit(f"{name}: marker unreadable; refusing reset")
    if not isinstance(marker, dict) or any(
        marker.get(key) != value for key, value in expected.items()
    ):
        sys.exit(f"{name}: marker does not bind the mini identity: {marker!r}")
    shutil.rmtree(root)
    print(f"{name}: stale mini roots removed")
PY

# Reset the disposable mini database (marker-bound, same rules as full).
cd "$APP_ROOT"
if ! uv run python - "$DATABASE" <<'PY'
import sys

import psycopg

target = sys.argv[1]
marker = f"miroflow:destructive-target:v1:disposable:{target}"
admin = psycopg.connect(
    "postgresql://miroflow@127.0.0.1:55458/postgres", autocommit=True
)
existing = admin.execute(
    "SELECT shobj_description(oid, 'pg_database') AS marker "
    "FROM pg_database WHERE datname = %s",
    (target,),
).fetchone()
if existing is not None:
    if existing[0] == marker:
        admin.execute(f"DROP DATABASE {target} WITH (FORCE)")
        print("stale mini database dropped")
    else:
        probe = psycopg.connect(
            f"postgresql://miroflow@127.0.0.1:55458/{target}", autocommit=True
        )
        tables = probe.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' AND table_schema NOT IN "
            "('pg_catalog', 'information_schema')"
        ).fetchone()[0]
        probe.close()
        if tables:
            sys.exit(f"refusing reset: marker={existing[0]!r}, {tables} tables")
        admin.execute(f"DROP DATABASE {target} WITH (FORCE)")
        print("unmarked empty mini database dropped")
admin.execute(f"CREATE DATABASE {target}")
admin.execute(f"COMMENT ON DATABASE {target} IS '{marker}'")
print("mini database created and marked")
PY
then
  echo "mini database preparation failed" >&2
  exit 2
fi

MANIFEST_SHA=$(uv run python -c "
import json, sys
print(json.load(open('$MANIFEST'))['content_sha256'])
")
CANONICAL_V2_BACKUP_GATE_ROOT="$GATE_ROOT" \
ALEMBIC_DATABASE_URL="postgresql+psycopg://miroflow@127.0.0.1:55458/$DATABASE" \
ALEMBIC_EXPECTED_DATABASE=$DATABASE \
ALEMBIC_TARGET_KIND=disposable \
uv run alembic -c canonical_v2_alembic.ini upgrade head >/dev/null

# Materialize the isolated index marker and pin its hash for the runner.
mkdir -p "$DATA_ROOT"
INDEX_MARKER_SHA=$(uv run python - "$DATA_ROOT/index-v1" "$RELEASE" "$GATE_ROOT" <<'PY'
import hashlib
import sys

sys.path.insert(0, ".")
from src.data_agents.canonical_v2.knowledge_build_isolated import (
    prepare_isolated_index_target,
)

root, release, gate_root = sys.argv[1:4]
prepare_isolated_index_target(
    root=__import__("pathlib").Path(root),
    target_id=f"index:{release}",
    release_id=release,
    backup_gate_root=__import__("pathlib").Path(gate_root),
    forbidden_milvus_paths=(
        __import__("pathlib").Path(
            "/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db"
        ),
    ),
)
marker = __import__("pathlib").Path(root) / ".canonical-v2-isolated-index-target.json"
print(hashlib.sha256(marker.read_bytes()).hexdigest())
PY
)

# Derive the exact evidence batch list from the mini manifest itself.
BATCH_ARGS=()
while read -r batch; do
  BATCH_ARGS+=(--source-batch-id "$batch")
done < <(uv run python -c "
import json
manifest = json.load(open('$MANIFEST'))
batches = sorted({
    member['source_batch_id']
    for entry in manifest['inventory_entries']
    if entry.get('disposition') == 'evidence_input'
    for member in entry['members']
})
print('\n'.join(batches))
")

cd "$APP_ROOT"
PYTHONUNBUFFERED=1 uv run python "$RUNNER" \
  --database-url "postgresql://miroflow@127.0.0.1:55458/$DATABASE" \
  --expected-database "$DATABASE" \
  --database-target-kind disposable \
  --accepted-backup-gate-root "$GATE_ROOT" \
  --source-manifest "$MANIFEST" \
  --source-manifest-sha256 "$MANIFEST_SHA" \
  --candidate-staging-root "$DATA_ROOT/staging-v1" \
  --index-root "$DATA_ROOT/index-v1" \
  --index-marker-sha256 "$INDEX_MARKER_SHA" \
  --candidate-release-id "$RELEASE" \
  --run-id "$RUN_ID" \
  "${BATCH_ARGS[@]}" \
  --parser-version historical_jsonl=v1 \
  --parser-version historical_xlsx=v1 \
  --parser-version released_objects_sqlite=canonical-v2-s12a-full-table-v1 \
  --policy-version path_eligibility=path-eligibility-v1 \
  --policy-version released_objects_mapper=canonical-v2-released-objects-mapper-v2 \
  --model-version embedding=Qwen/Qwen3-Embedding-8B \
  --recorded-decision-bundle "$REAL_GATE_ROOT/s12a/recorded-decision-bundle-v1.json" \
  --recorded-embedding-bundle "$REAL_GATE_ROOT/s12c/qwen-embedding-bundle-v1.json" \
  --envelope-output "$ENVELOPE" \
  --accepted-original-milvus-path /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --accepted-original-milvus-sha256 43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc \
  --accepted-original-milvus-record-sha256 df3715a0be8560d523ce2abb589bdaf690e0fe07babcad26c03a4da0ad8cbe6b \
  2>&1 | tee "$BUILD_LOG"
