#!/usr/bin/env bash
# P4 full-column serving-pack rebuild (full-column-serving-pack-rebuild).
#
# Zero-write guarantees vs the live line:
#   - database: NEW disposable miroflow_candidate_v2_20260819_r1 (the s12f
#     database on the same cluster is never opened by the build target);
#   - staging/index roots under a NEW /var/tmp/mirothinker-data-v2 tree;
#   - envelope lands in THIS worktree's gate root (s12a slot), not the live
#     canonical-v2-s11-consolidation worktree;
#   - no --serve here; the v2 pack is smoke-served separately on port 18200.
set -Eeuo pipefail

WORKTREE=/home/longxiang/MiroThinker/.worktrees/data-rebuild
RUN_ROOT="$WORKTREE/.agents/runs/full-column-serving-pack-rebuild"
GATE_ROOT="$WORKTREE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
APP_ROOT="$WORKTREE/apps/miroflow-agent"
RUNNER="$GATE_ROOT/s12a/complete_candidate_runner.py"
MANIFEST="$RUN_ROOT/source-build-manifest-p4.json"
MANIFEST_SHA256=a6e82fcd9dd5b2da22fd0c73cfe81b674ad04827092eb01fd4442956f70e184d
ENVELOPE="$GATE_ROOT/s12a/complete-candidate-build-envelope.json"
BUILD_LOG="$RUN_ROOT/build.log"

if [[ -e "$ENVELOPE" ]]; then
  echo "envelope output already exists: $ENVELOPE" >&2
  exit 2
fi
# Reset stale staging/index roots left by a partially-failed run of THIS build
# identity: the staging marker must bind this run-id + release + manifest sha,
# otherwise halt. Existence alone is not freshness (same lesson as the DB).
if [[ -e /var/tmp/mirothinker-data-v2/staging-v1 || -e /var/tmp/mirothinker-data-v2/index-v1 ]]; then
  if ! python3 - <<'PY'
import json
import shutil
import sys
from pathlib import Path

expected = {
    "schema_version": "canonical-v2-candidate-staging-marker-v1",
    "run_id": "p4-build-20260819-v1",
    "candidate_release_id": "candidate-v2-20260819-r1",
    "source_manifest_sha256": (
        "a6e82fcd9dd5b2da22fd0c73cfe81b674ad04827092eb01fd4442956f70e184d"
    ),
}
marker_path = Path(
    "/var/tmp/mirothinker-data-v2/staging-v1/.canonical-v2-staging.json"
)
try:
    marker = json.loads(marker_path.read_text()) if marker_path.exists() else None
except (OSError, json.JSONDecodeError):
    sys.exit("staging marker is unreadable; refusing to reset staging/index roots")
if not isinstance(marker, dict) or any(
    marker.get(key) != value for key, value in expected.items()
):
    sys.exit(
        "staging/index roots exist but the marker does not bind this build "
        f"identity: {marker!r}"
    )
for root in (
    Path("/var/tmp/mirothinker-data-v2/staging-v1"),
    Path("/var/tmp/mirothinker-data-v2/index-v1"),
):
    if root.exists():
        shutil.rmtree(root)
print("stale staging/index roots from a failed run of this build removed")
PY
  then
    echo "staging/index roots are not fresh and not safely resettable" >&2
    exit 2
  fi
fi
if ! docker ps --format '{{.Names}}' | grep -q '^canonical-v2-s12c-pg-20260726-r8$'; then
  echo "build database container canonical-v2-s12c-pg-20260726-r8 is not running" >&2
  exit 2
fi

# Reset the disposable target database to a fresh, marked state (C2_0013 head).
# Existence is NOT freshness: a partially-failed run leaves rows behind (the
# runner's _assert_fresh_database then aborts), and a manually recreated
# database carries no destructive-target marker (identity checks then abort).
# Drop-and-recreate is only allowed for a database that either carries this
# script's exact disposable marker or is completely empty; anything else halts.
# The s12f database on the same cluster is never touched.
cd "$APP_ROOT"
if ! uv run python - <<'PY'
import psycopg

TARGET = "miroflow_candidate_v2_20260819_r1"
MARKER = f"miroflow:destructive-target:v1:disposable:{TARGET}"

admin = psycopg.connect(
    "postgresql://miroflow@127.0.0.1:55458/postgres", autocommit=True
)
existing = admin.execute(
    "SELECT shobj_description(oid, 'pg_database') AS marker "
    "FROM pg_database WHERE datname = %s",
    (TARGET,),
).fetchone()
if existing is not None:
    marker = existing[0]
    if marker == MARKER:
        admin.execute(f"DROP DATABASE {TARGET} WITH (FORCE)")
        print("stale disposable target dropped (owned by a previous run)")
    else:
        probe = psycopg.connect(
            f"postgresql://miroflow@127.0.0.1:55458/{TARGET}", autocommit=True
        )
        tables = probe.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' AND table_schema NOT IN "
            "('pg_catalog', 'information_schema')"
        ).fetchone()[0]
        probe.close()
        if tables:
            raise SystemExit(
                f"refusing to reset {TARGET}: marker={marker!r} "
                f"and {tables} tables present"
            )
        admin.execute(f"DROP DATABASE {TARGET} WITH (FORCE)")
        print("unmarked but empty target dropped")
admin.execute(f"CREATE DATABASE {TARGET}")
admin.execute(f"COMMENT ON DATABASE {TARGET} IS '{MARKER}'")
print("target database created and marked")
PY
then
  echo "target database preparation failed" >&2
  exit 2
fi
CANONICAL_V2_BACKUP_GATE_ROOT="$GATE_ROOT" \
ALEMBIC_DATABASE_URL="postgresql+psycopg://miroflow@127.0.0.1:55458/miroflow_candidate_v2_20260819_r1" \
ALEMBIC_EXPECTED_DATABASE=miroflow_candidate_v2_20260819_r1 \
ALEMBIC_TARGET_KIND=disposable \
uv run alembic -c canonical_v2_alembic.ini upgrade head >/dev/null

mkdir -p /var/tmp/mirothinker-data-v2
cd "$APP_ROOT"
PYTHONUNBUFFERED=1 uv run python "$RUNNER" \
  --database-url postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_v2_20260819_r1 \
  --expected-database miroflow_candidate_v2_20260819_r1 \
  --database-target-kind disposable \
  --accepted-backup-gate-root "$GATE_ROOT" \
  --source-manifest "$MANIFEST" \
  --source-manifest-sha256 "$MANIFEST_SHA256" \
  --candidate-staging-root /var/tmp/mirothinker-data-v2/staging-v1 \
  --index-root /var/tmp/mirothinker-data-v2/index-v1 \
  --index-marker-sha256 8848197caaa665fa093f054aa6c7c241b90376f311ec62e089ddb479a6e97c8b \
  --candidate-release-id candidate-v2-20260819-r1 \
  --run-id p4-build-20260819-v1 \
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
  --model-version embedding=Qwen/Qwen3-Embedding-8B \
  --recorded-decision-bundle "$GATE_ROOT/s12a/recorded-decision-bundle-v1.json" \
  --recorded-embedding-bundle "$GATE_ROOT/s12c/qwen-embedding-bundle-v1.json" \
  --envelope-output "$ENVELOPE" \
  --accepted-original-milvus-path /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --accepted-original-milvus-sha256 43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc \
  --accepted-original-milvus-record-sha256 df3715a0be8560d523ce2abb589bdaf690e0fe07babcad26c03a4da0ad8cbe6b \
  2>&1 | tee "$BUILD_LOG"
