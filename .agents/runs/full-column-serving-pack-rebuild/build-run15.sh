#!/usr/bin/env bash
# P4 full-column serving-pack rebuild — run15 (C1 alias-closure batch1b).
#
# Zero-write guarantees vs the LIVE line (run14 sealed on 18188):
#   - NEW database $TARGET_DB (the run14 build DB and every s12* database on
#     the same cluster are never opened);
#   - NEW staging/index roots (staging-v2 / index-v2); the LIVE index-v1
#     (the running service's Milvus cwd) is never touched;
#   - NEW envelope file at the runner's fixed candidate evidence path; the
#     archived run14 envelope stays byte-intact;
#   - no --serve here; the run15 pack is smoke-served separately.
#
# Prereq: data-rebuild worktree carries the alias-closure code (batch1a) on
# top of the run14 build state (knowledge_build_isolated.py last changed
# 2026-09-07; run14 envelope built 2026-09-08 20:00).
set -Eeuo pipefail

WORKTREE=/home/longxiang/MiroThinker/.worktrees/data-rebuild
RUN_ROOT="$WORKTREE/.agents/runs/full-column-serving-pack-rebuild"
GATE_ROOT="$WORKTREE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
APP_ROOT="$WORKTREE/apps/miroflow-agent"
RUNNER="$GATE_ROOT/s12a/complete_candidate_runner.py"
MANIFEST="$RUN_ROOT/source-build-manifest-p4.json"
MANIFEST_SHA256=a6e82fcd9dd5b2da22fd0c73cfe81b674ad04827092eb01fd4442956f70e184d
ENVELOPE="$GATE_ROOT/s12a/complete-candidate-build-envelope.json"
BUILD_LOG="$RUN_ROOT/build-run15.log"
STAGING=/var/tmp/mirothinker-data-v2/staging-v2
INDEX=/var/tmp/mirothinker-data-v2/index-v2
TARGET_DB=miroflow_candidate_v2_20260913_r1
RUN_ID=p4-build-20260913-v1

if [[ -e "$ENVELOPE" ]]; then
  echo "envelope output already exists: $ENVELOPE" >&2
  exit 2
fi
if [[ -e "$STAGING" || -e "$INDEX" ]]; then
  echo "staging/index roots already exist; run15 requires a fresh target" >&2
  exit 2
fi
if ! docker ps --format '{{.Names}}' | grep -q '^canonical-v2-s12c-pg-20260726-r8$'; then
  echo "build database container canonical-v2-s12c-pg-20260726-r8 is not running" >&2
  exit 2
fi

cd "$APP_ROOT"

# 1) fresh isolated index target: marker only (S2B gate inside).
MARKER_SHA="$(
  uv run python - <<PY
import sys
from pathlib import Path

sys.path.insert(0, ".")
from src.data_agents.canonical_v2.index_projection_isolated import (
    prepare_isolated_index_target,
)

target = prepare_isolated_index_target(
    root=Path("$INDEX"),
    target_id="index:candidate-v2-20260913-r1",
    release_id="candidate-v2-20260913-r1",
    backup_gate_root=Path("$GATE_ROOT"),
    forbidden_milvus_paths=(
        Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db"),
    ),
)
print(target.marker_sha256)
PY
)"
echo "index marker sha256=$MARKER_SHA"

# 2) fresh disposable target database (marker-owned drop only; never touches
#    any other database on the cluster).
if ! uv run python - <<PY
import psycopg

TARGET = "$TARGET_DB"
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
ALEMBIC_DATABASE_URL="postgresql+psycopg://miroflow@127.0.0.1:55458/$TARGET_DB" \
ALEMBIC_EXPECTED_DATABASE="$TARGET_DB" \
ALEMBIC_TARGET_KIND=disposable \
uv run alembic -c canonical_v2_alembic.ini upgrade head >/dev/null

# 3) the candidate build itself.
cd "$APP_ROOT"
PYTHONUNBUFFERED=1 uv run python "$RUNNER" \
  --database-url postgresql://miroflow@127.0.0.1:55458/$TARGET_DB \
  --expected-database "$TARGET_DB" \
  --database-target-kind disposable \
  --accepted-backup-gate-root "$GATE_ROOT" \
  --source-manifest "$MANIFEST" \
  --source-manifest-sha256 "$MANIFEST_SHA256" \
  --candidate-staging-root "$STAGING" \
  --index-root "$INDEX" \
  --index-marker-sha256 "$MARKER_SHA" \
  --candidate-release-id candidate-v2-20260913-r1 \
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
  --model-version embedding=Qwen/Qwen3-Embedding-8B \
  --recorded-decision-bundle "$GATE_ROOT/s12a/recorded-decision-bundle-v1.json" \
  --recorded-embedding-bundle "$GATE_ROOT/s12c/qwen-embedding-bundle-v1.json" \
  --envelope-output "$ENVELOPE" \
  --accepted-original-milvus-path /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --accepted-original-milvus-sha256 43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc \
  --accepted-original-milvus-record-sha256 df3715a0be8560d523ce2abb589bdaf690e0fe07babcad26c03a4da0ad8cbe6b \
  2>&1 | tee "$BUILD_LOG"
