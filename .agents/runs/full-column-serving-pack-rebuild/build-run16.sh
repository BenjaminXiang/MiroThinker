#!/usr/bin/env bash
# P4 full-column serving-pack rebuild — run16 (data line: D0-a/D0-b + C1 + F3 + D1-a).
#
# Parameter copy of build-run15.sh; only the release-bound identities change
# (new DB, new staging/index roots, new release id, new run id).  The envelope
# path is the runner's FIXED candidate evidence path and must be reused, so
# run15's envelope has to be archived first (see below).
#
# Gate: refuses to run until feat/d1a-tech-vocabulary is an ancestor of HEAD
# (D1-a is run16's last threshold; launching without it would rebuild the old
# vocabulary).
#
# Zero-write guarantees vs the LIVE line (run15 sealed on 18188):
#   - NEW database $TARGET_DB (run15's build DB and every other database on
#     the same cluster are never opened);
#   - NEW staging/index roots (staging-v3 / index-v3); the LIVE index-v2
#     (run15's milestone) is never touched;
#   - the run15 envelope is archived (not deleted) before this run writes the
#     fixed path; the archived file stays byte-intact;
#   - no --serve here; the run16 pack is smoke-served separately.
set -Eeuo pipefail

WORKTREE=/home/longxiang/MiroThinker/.worktrees/data-rebuild
RUN_ROOT="$WORKTREE/.agents/runs/full-column-serving-pack-rebuild"
GATE_ROOT="$WORKTREE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
APP_ROOT="$WORKTREE/apps/miroflow-agent"
RUNNER="$GATE_ROOT/s12a/complete_candidate_runner.py"
MANIFEST="$RUN_ROOT/source-build-manifest-p4.json"
# NB: this is the manifest's internal content_sha256 field (content-addressed),
# not the sha256 of the file bytes.
MANIFEST_SHA256=a6e82fcd9dd5b2da22fd0c73cfe81b674ad04827092eb01fd4442956f70e184d
ENVELOPE="$GATE_ROOT/s12a/complete-candidate-build-envelope.json"
ENVELOPE_RUN15_ARCHIVE="$GATE_ROOT/s12a/complete-candidate-build-envelope-run15.json"
BUILD_LOG="$RUN_ROOT/build-run16.log"
STAGING=/var/tmp/mirothinker-data-v2/staging-v3
INDEX=/var/tmp/mirothinker-data-v2/index-v3
TARGET_DB=miroflow_candidate_v2_20260916_r1
RUN_ID=p4-build-20260916-v1
RELEASE_ID=candidate-v2-20260916-r1

if ! git -C "$WORKTREE" merge-base --is-ancestor feat/d1a-tech-vocabulary HEAD; then
  echo "feat/d1a-tech-vocabulary is not merged into HEAD; run16 must include D1-a" >&2
  exit 2
fi
if [[ -e "$ENVELOPE_RUN15_ARCHIVE" && -e "$ENVELOPE" ]]; then
  echo "both the run15 archive and the live envelope path exist; resolve by hand" >&2
  exit 2
fi
if [[ -e "$ENVELOPE" && ! -e "$ENVELOPE_RUN15_ARCHIVE" ]]; then
  echo "envelope path is occupied by run15's envelope; archive it first:" >&2
  echo "  mv '$ENVELOPE' '$ENVELOPE_RUN15_ARCHIVE'" >&2
  exit 2
fi
if [[ -e "$STAGING" || -e "$INDEX" ]]; then
  echo "staging/index roots already exist; run16 requires a fresh target" >&2
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
    target_id="index:candidate-v2-20260916-r1",
    release_id="$RELEASE_ID",
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
  --model-version embedding=Qwen/Qwen3-Embedding-8B \
  --recorded-decision-bundle "$GATE_ROOT/s12a/recorded-decision-bundle-v1.json" \
  --recorded-embedding-bundle "$GATE_ROOT/s12c/qwen-embedding-bundle-v1.json" \
  --envelope-output "$ENVELOPE" \
  --accepted-original-milvus-path /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --accepted-original-milvus-sha256 43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc \
  --accepted-original-milvus-record-sha256 df3715a0be8560d523ce2abb589bdaf690e0fe07babcad26c03a4da0ad8cbe6b \
  2>&1 | tee "$BUILD_LOG"
