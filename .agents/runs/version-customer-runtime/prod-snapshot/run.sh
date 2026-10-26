#!/usr/bin/env bash
# MiroThinker canonical-v2 (fembed line) launcher — customer site.
# Bundle root: /root/deploy/fullstack-v2   Usage: nohup bash run.sh [PORT] > serve.log 2>&1 &
#
# Frozen identities (must not drift; pinned by the serving bundle / pack manifest):
#   release   candidate-v2-20260922-r1
#   pack      /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth
#   index     /var/tmp/mirothinker-data-v2/index-v4-v2  (marker df594dc5…)
#   embedding qwen3.7-text-embedding-flash @ maas.qianwenaiapi.com (CANONICAL_V2_EMBEDDING_API_KEY)
#
# Credentials: all model keys live in code/config/managed/secrets.json (managed file,
# editable from the admin web page); an explicit environment variable would shadow
# that page, so this launcher deliberately does NOT export them.
set -Eeuo pipefail

B="$(cd "$(dirname "$0")" && pwd)"
PORT="${1:-18188}"
PY="$B/.venv/bin/python"
export PATH="$B/.venv/bin:$PATH"
DB=miroflow_candidate_v2_20260922_r1
PACK=/var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth
INDEX=/var/tmp/mirothinker-data-v2/index-v4-v2
# Pinned evidence root: the recorded serving bundle names the envelope under this
# exact path, and the runner re-derives it from --accepted-backup-gate-root.
GATE=/home/longxiang/MiroThinker/.worktrees/embedding-switch-line/.agents/runs/rebuild-canonical-v2-knowledge-platform

cd "$B"
mkdir -p "$B/var" "$B/var/staging-smoke" "$B/var/manual-recall-v1"

# --- session sidecars (sqlite, bundle-local) ---
export CANONICAL_V2_ACCESS_LOG_DB="$B/var/access-logs.sqlite3"
export CANONICAL_V2_CORRECTIONS_DB="$B/var/corrections.sqlite3"
export CANONICAL_V2_MANUAL_RECALL_DIR="$B/var/manual-recall-v1"
export CANONICAL_V2_ANSWER_CACHE_DB="$B/var/answer-cache.sqlite3"
export CANONICAL_V2_ANSWER_CACHE=1
export CANONICAL_V2_TURN_DEBUG_DIR="$B/var/turn-debug"
export MIROTHINKER_JOB_PYTHON="$B/.venv/bin/python"
export MIROTHINKER_JOB_DATABASE_URL="postgresql://miroflow@127.0.0.1:5432/miroflow_collection_v1"
# Console/upload/ops surface: the customer asked for the data front door and the
# index actions to be usable. DATABASE_URL is the console DSN (collection DB);
# it is deliberately scoped to this process, never exported globally.
export DATABASE_URL="$MIROTHINKER_JOB_DATABASE_URL"
# Retrieval self-check runs against the live service instead of starting a
# second uvicorn (the serving process owns the pack and the Milvus-Lite lock).
export HOST_E2E_BASE_URL="http://127.0.0.1:18188"
export MIROTHINKER_JOB_TIMEZONE="Asia/Shanghai"
# Seed page keeps its own DSN so the seed surface never depends on the console DSN.
export CANONICAL_V2_SEED_DATABASE_URL="$MIROTHINKER_JOB_DATABASE_URL"
export CANONICAL_V2_LEXICAL_INDEX="${CANONICAL_V2_LEXICAL_INDEX:-0}"
export CHAT_CONTEXTUAL_INTERPRETATION="${CHAT_CONTEXTUAL_INTERPRETATION:-on}"
export CHAT_LLM_PROFILE="${CHAT_LLM_PROFILE:-deepseekv4flash}"
export CHAT_LLM_TIMEOUT_SECONDS="${CHAT_LLM_TIMEOUT_SECONDS:-30}"
export CHAT_LLM_HEDGE_PROFILE="${CHAT_LLM_HEDGE_PROFILE:-gemma4}"
export CHAT_LLM_HEDGE_DELAY_SECONDS="${CHAT_LLM_HEDGE_DELAY_SECONDS:-6}"

# --- non-secret environment only (never key material: managed secrets own those) ---
if [ -f "$B/code/apps/miroflow-agent/.env" ]; then
  set -a; . "$B/code/apps/miroflow-agent/.env"; set +a
fi
# legacy key files stay in code/ (last-resort fallback under the managed file);
# nothing reads .sglang_api_key on this line — kept only as a rollback artifact.

export PYTHONPATH="$B/code/apps/admin-console:$B/code/apps/miroflow-agent"

exec "$PY" "$B/code/serve-script/serve_s12e_port.py" "$PORT" \
  --database-url "postgresql://miroflow@127.0.0.1:5432/$DB" \
  --expected-database "$DB" \
  --database-target-kind disposable \
  --accepted-backup-gate-root "$GATE" \
  --source-manifest "$B/gate-evidence/p4/source-build-manifest-p4.json" \
  --source-manifest-sha256 a6e82fcd9dd5b2da22fd0c73cfe81b674ad04827092eb01fd4442956f70e184d \
  --candidate-staging-root "$B/var/staging-smoke" \
  --index-root "$INDEX" \
  --index-marker-sha256 df594dc5a8b3c0f73ba90e362122087e3e85d13cd1160bd963cb27941a2b5497 \
  --candidate-release-id candidate-v2-20260922-r1 \
  --run-id fembed-build-20260922-v1 \
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
  --recorded-decision-bundle "$B/gate-evidence/s12a/recorded-decision-bundle-v1.json" \
  --recorded-embedding-bundle "$B/gate-evidence/s12c/qwen3.7-text-embedding-flash-embedding-bundle-v1.json" \
  --recorded-serving-bundle "$B/gate-evidence/s12g/serving-bundle-fembed.json" \
  --recorded-serving-bundle-sha256 8ec351c947cef4414e8b6a3053eee44c6f5d7e554cc9a0e773ca93df5c441fb3 \
  --envelope-output "$GATE/s12a/complete-candidate-build-envelope.json" \
  --accepted-original-milvus-path /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --accepted-original-milvus-sha256 43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc \
  --accepted-original-milvus-record-sha256 df3715a0be8560d523ce2abb589bdaf690e0fe07babcad26c03a4da0ad8cbe6b \
  --serve --serve-existing \
  --serving-pack "$PACK"
