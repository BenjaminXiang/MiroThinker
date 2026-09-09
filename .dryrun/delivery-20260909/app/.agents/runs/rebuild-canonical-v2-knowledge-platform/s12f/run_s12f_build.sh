#!/usr/bin/env bash
set -Eeuo pipefail

WORKTREE=/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation
RUN_ROOT="$WORKTREE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
APP_ROOT="$WORKTREE/apps/miroflow-agent"
S12F_ROOT="$RUN_ROOT/s12f"
RUNNER="$RUN_ROOT/s12a/complete_candidate_runner.py"
LIVE_ENVELOPE="$RUN_ROOT/s12a/complete-candidate-build-envelope.json"
ORIGINAL_ENVELOPE="$S12F_ROOT/pre-s12f-s12a-envelope.json"
CANDIDATE_ENVELOPE="$S12F_ROOT/complete-candidate-build-envelope.json"
FAILED_ENVELOPE="$S12F_ROOT/failed-candidate-build-envelope.json"
BUILD_LOG="$S12F_ROOT/build.log"
ORIGINAL_ENVELOPE_SHA256=ab21c0a60a5d85a2abd51724b945a79e5f99c121601eeb995870cb974b79acb9

if [[ ! -f "$LIVE_ENVELOPE" || -L "$LIVE_ENVELOPE" ]]; then
  echo "s12a envelope is absent or unsafe" >&2
  exit 2
fi
if [[ "$(stat -c %h "$LIVE_ENVELOPE")" != 1 ]]; then
  echo "s12a envelope is hard-linked" >&2
  exit 2
fi
if [[ "$(sha256sum "$LIVE_ENVELOPE" | cut -d' ' -f1)" != "$ORIGINAL_ENVELOPE_SHA256" ]]; then
  echo "s12a envelope hash differs before build" >&2
  exit 2
fi
if [[ -e "$ORIGINAL_ENVELOPE" || -e "$CANDIDATE_ENVELOPE" || -e "$FAILED_ENVELOPE" ]]; then
  echo "s12f envelope output/backup already exists" >&2
  exit 2
fi
if [[ -e /var/tmp/mirothinker-canonical-v2-s12f/staging-v1 ]]; then
  echo "s12f staging root is not fresh" >&2
  exit 2
fi

mv "$LIVE_ENVELOPE" "$ORIGINAL_ENVELOPE"

restore_s12a_envelope() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -f "$LIVE_ENVELOPE" ]]; then
    if [[ $status -eq 0 ]]; then
      mv "$LIVE_ENVELOPE" "$CANDIDATE_ENVELOPE"
    else
      mv "$LIVE_ENVELOPE" "$FAILED_ENVELOPE"
    fi
  fi
  if [[ -f "$ORIGINAL_ENVELOPE" ]]; then
    mv "$ORIGINAL_ENVELOPE" "$LIVE_ENVELOPE"
    chmod 0600 "$LIVE_ENVELOPE"
  fi
  if [[ ! -f "$LIVE_ENVELOPE" ]] || \
     [[ "$(sha256sum "$LIVE_ENVELOPE" | cut -d' ' -f1)" != "$ORIGINAL_ENVELOPE_SHA256" ]]; then
    echo "failed to restore the byte-exact s12a envelope" >&2
    status=97
  fi
  echo "BUILD_EXIT=$status"
  exit "$status"
}
trap restore_s12a_envelope EXIT INT TERM

cd "$APP_ROOT"
PYTHONUNBUFFERED=1 uv run python "$RUNNER" \
  --database-url postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_s12f_20260801_v1 \
  --expected-database miroflow_candidate_s12f_20260801_v1 \
  --database-target-kind disposable \
  --accepted-backup-gate-root "$RUN_ROOT" \
  --source-manifest "$S12F_ROOT/source-build-manifest-s12f.json" \
  --source-manifest-sha256 81ed1f9f7da7b61f2b10192e311cdee73bff2d19ac9290cdb2468f1288e48b7a \
  --candidate-staging-root /var/tmp/mirothinker-canonical-v2-s12f/staging-v1 \
  --index-root /var/tmp/mirothinker-canonical-v2-s12f/index-v1 \
  --index-marker-sha256 e4314c15518980aaa75a0069dce14c3857df43b74705ce600c6741af74d49f51 \
  --candidate-release-id candidate-s12f-20260801-v1 \
  --run-id s12f-build-20260801-v1 \
  --source-batch-id s12a-released-objects-full-v1 \
  --source-batch-id s12c-r7-company-knowledge-v1 \
  --source-batch-id s12c-r7-company-workbook-supplement-v1 \
  --source-batch-id s12c-r7-paper-identifiers-v1 \
  --source-batch-id s12c-r7-patent-identifiers-v1 \
  --source-batch-id s12c-r7-professor-company-roles-v1 \
  --source-batch-id s12e-professor-backfill-v1 \
  --source-batch-id s12f-company-backfill-v1 \
  --source-batch-id s12f-applicant-binding-v1 \
  --parser-version historical_jsonl=v1 \
  --parser-version historical_xlsx=v1 \
  --parser-version released_objects_sqlite=canonical-v2-s12a-full-table-v1 \
  --policy-version path_eligibility=path-eligibility-v1 \
  --policy-version released_objects_mapper=canonical-v2-released-objects-mapper-v2 \
  --model-version embedding=Qwen/Qwen3-Embedding-8B \
  --recorded-decision-bundle "$RUN_ROOT/s12a/recorded-decision-bundle-v1.json" \
  --recorded-embedding-bundle "$RUN_ROOT/s12c/qwen-embedding-bundle-v1.json" \
  --envelope-output "$LIVE_ENVELOPE" \
  --accepted-original-milvus-path /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --accepted-original-milvus-sha256 43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc \
  --accepted-original-milvus-record-sha256 df3715a0be8560d523ce2abb589bdaf690e0fe07babcad26c03a4da0ad8cbe6b \
  2>&1 | tee "$BUILD_LOG"
