PORT="${1:-18188}"
#!/usr/bin/env bash
# P4 scratch-port smoke serve of the v2 serving pack (port 18200).
#
# Mirrors serve-fixline-18188.sh but binds EVERY P4 artifact to new names:
# pack /var/tmp/mirothinker-data-v2/serving-pack, gate root and bundles from
# THIS worktree, access/corrections/manual-recall sidecars under
# /var/tmp/mirothinker-data-v2/. The live 18188 instance is untouched.
set -euo pipefail

WORKTREE=/home/longxiang/MiroThinker/.worktrees/data-rebuild
GATE_ROOT="$WORKTREE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
RUN_ROOT="$WORKTREE/.agents/runs/full-column-serving-pack-rebuild"
APP_ROOT="$WORKTREE/apps/miroflow-agent"

export CANONICAL_V2_ACCESS_LOG_DB=/var/tmp/mirothinker-data-v2/access-logs.sqlite3
export CANONICAL_V2_CORRECTIONS_DB=/var/tmp/mirothinker-data-v2/corrections.sqlite3
export CANONICAL_V2_MANUAL_RECALL_DIR=/var/tmp/mirothinker-data-v2/manual-recall-v1
export CHAT_LLM_PROFILE=${CHAT_LLM_PROFILE:-gemma4}
export CHAT_LLM_TIMEOUT_SECONDS=${CHAT_LLM_TIMEOUT_SECONDS:-90}

export PYTHONPATH="$WORKTREE/apps/miroflow-agent:$WORKTREE/apps/admin-console:$WORKTREE/libs/miroflow-tools:${PYTHONPATH:-}"
cd /home/longxiang/MiroThinker
PORT="${1:-18188}"
exec .venv/bin/python "$GATE_ROOT/s12e/serve_s12e_port.py" "$PORT" \
  --database-url postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_v2_20260819_r1 \
  --expected-database miroflow_candidate_v2_20260819_r1 \
  --database-target-kind disposable \
  --accepted-backup-gate-root "$GATE_ROOT" \
  --source-manifest "$RUN_ROOT/source-build-manifest-p4.json" \
  --source-manifest-sha256 a6e82fcd9dd5b2da22fd0c73cfe81b674ad04827092eb01fd4442956f70e184d \
  --candidate-staging-root /var/tmp/mirothinker-data-v2/staging-smoke \
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
  --recorded-serving-bundle "$RUN_ROOT/serving-bundle-p4.json" \
  --recorded-serving-bundle-sha256 ddee3610c7e9258f04b34a4de24c6d73c08522142b653633477a25613f1715fc \
  --recorded-embedding-bundle "$GATE_ROOT/s12c/qwen-embedding-bundle-v1.json" \
  --envelope-output "$GATE_ROOT/s12a/complete-candidate-build-envelope.json" \
  --accepted-original-milvus-path /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --accepted-original-milvus-sha256 43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc \
  --accepted-original-milvus-record-sha256 df3715a0be8560d523ce2abb589bdaf690e0fe07babcad26c03a4da0ad8cbe6b \
  --serve --serve-existing --serving-pack /var/tmp/mirothinker-data-v2/serving-pack
