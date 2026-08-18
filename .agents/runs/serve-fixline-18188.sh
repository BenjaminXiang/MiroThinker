#!/usr/bin/env bash
# fix 分支 serve 启动入口（Phase 1/2 验证期间使用；与 s12g 命令文件同构，
# 但 sha 修正为 bundle 实际声明的 c1 值，并带 TURN_TRACE_DIR）。
set -euo pipefail
cd /home/longxiang/MiroThinker
W=/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation/.agents/runs/rebuild-canonical-v2-knowledge-platform
R=/home/longxiang/MiroThinker/.agents/runs/rebuild-canonical-v2-knowledge-platform
export TURN_TRACE_DIR=${TURN_TRACE_DIR:-/var/tmp/turn-trace-fixline}
export CANONICAL_V2_ACCESS_LOG_DB=/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3
export CANONICAL_V2_CORRECTIONS_DB=/var/tmp/mirothinker-canonical-v2-s12f/corrections.sqlite3
export CANONICAL_V2_MANUAL_RECALL_DIR=/var/tmp/mirothinker-canonical-v2-s12f/manual-recall-v1
export CHAT_LLM_PROFILE=${CHAT_LLM_PROFILE:-gemma4}
exec uv run python "$R/s12e/serve_s12e_port.py" 18188 \
  --database-url postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_s12f_20260801_v1 \
  --expected-database miroflow_candidate_s12f_20260801_v1 \
  --database-target-kind disposable \
  --accepted-backup-gate-root "$W" \
  --source-manifest "$W/s12f/source-build-manifest-s12f.json" \
  --source-manifest-sha256 7908db3925c8450bc93aa9543b9c94b7cf37a4bae8f796cf0cdd007ac77c0f97 \
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
  --parser-version historical_jsonl=v1 \
  --parser-version historical_xlsx=v1 \
  --parser-version released_objects_sqlite=canonical-v2-s12a-full-table-v1 \
  --policy-version path_eligibility=path-eligibility-v1 \
  --policy-version released_objects_mapper=canonical-v2-released-objects-mapper-v2 \
  --model-version embedding=Qwen/Qwen3-Embedding-8B \
  --recorded-decision-bundle "$W/s12a/recorded-decision-bundle-v1.json" \
  --recorded-embedding-bundle "$W/s12c/qwen-embedding-bundle-v1.json" \
  --recorded-serving-bundle "$W/s12f/serving-bundle-s12f.json" \
  --recorded-serving-bundle-sha256 93fb456012f5e9799414cd90fa2ea27bb7d58acd5d41c13ac3b9dea601aed9c0 \
  --envelope-output "$W/s12a/complete-candidate-build-envelope.json" \
  --accepted-original-milvus-path /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --accepted-original-milvus-sha256 43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc \
  --accepted-original-milvus-record-sha256 df3715a0be8560d523ce2abb589bdaf690e0fe07babcad26c03a4da0ad8cbe6b \
  --serve --serve-existing --serving-pack /var/tmp/mirothinker-canonical-v2-s12f/serving-pack
