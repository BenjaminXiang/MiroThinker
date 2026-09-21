#!/usr/bin/env bash
# fembed build — the candidate rebuild (runbook step 5), launched from the SWITCH LINE.
#
# Route: dashscope-native (option B). The bundle freezes the model identity, the
# 1024 dimension, batch 20 and the query-side treatment; this build takes the
# *document* role, so the query parameters are never sent here.
#
# Zero-write guarantees vs the live line: a NEW database, a NEW staging root, a
# NEW index root, a NEW envelope at the switch line's own fixed path. The run16
# envelope in .worktrees/data-rebuild is the rollback anchor's record and is only
# read (the runner re-checks it); it is never moved.
set -Eeuo pipefail

SWITCH_LINE=/home/longxiang/MiroThinker/.worktrees/embedding-switch-line
GATE_ROOT="$SWITCH_LINE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
RUN_ROOT="$SWITCH_LINE/.agents/runs/full-column-serving-pack-rebuild"
RUNS="$SWITCH_LINE/.agents/runs/embedding-model-switch-v2"
RUNNER="$GATE_ROOT/s12a/complete_candidate_runner.py"
DEPLOY_PY=/home/longxiang/MiroThinker/.venv/bin/python       # 3.12.12 + pydantic 2.12.5
KEY_FILE=/var/tmp/mirothinker-qianwen-api-key

DATE=20260922
RELEASE_ID="candidate-v2-$DATE-r1"
TARGET_DB="miroflow_candidate_v2_${DATE}_r1"
RUN_ID="fembed-build-$DATE-v1"
STAGING=/var/tmp/mirothinker-data-v2/staging-v4
INDEX=/var/tmp/mirothinker-data-v2/index-v4
MARKER_SHA=058c0bcfa905b46d3a3dcd56a10712de6eb69791b980d2a6ccfe8f441b0a3e5c
ENVELOPE="$GATE_ROOT/s12a/complete-candidate-build-envelope.json"
# The native route, document role: the gates below are the runbook's step-5 flags.
BUNDLE="$RUNS/qwen3.7-text-embedding-flash-embedding-bundle-v1.json"

if [[ -e "$ENVELOPE" ]]; then
  echo "envelope fixed path is occupied; archive it first (runbook step 2)" >&2
  exit 2
fi
if [[ -e "$STAGING" ]]; then
  echo "staging root already exists; the build requires a fresh target" >&2
  exit 2
fi
if [[ ! -f "$INDEX/.canonical-v2-isolated-index-target.json" ]]; then
  echo "index marker is missing at $INDEX (runbook step 3)" >&2
  exit 2
fi
if ! docker ps --format '{{.Names}}' | grep -q '^canonical-v2-s12c-pg-20260726-r8$'; then
  echo "build database container canonical-v2-s12c-pg-20260726-r8 is not running" >&2
  exit 2
fi

cd "$SWITCH_LINE/apps/miroflow-agent"

# The deployment venv installs ``src`` editable from the *live* tree
# (/home/longxiang/MiroThinker/apps/miroflow-agent, via
# ``_editable_impl_miroflow_agent.pth``), and a script invocation puts the
# *script's* directory on sys.path[0] rather than the cwd — so without this line
# the runner imports the live tree's canonical_v2 (no ``role`` parameter, no
# candidate identity) instead of the switch line's. PYTHONPATH entries precede
# the .pth ones, so this pins the code tree the build actually runs.
export PYTHONPATH="$SWITCH_LINE/apps/miroflow-agent${PYTHONPATH:+:$PYTHONPATH}"

CANONICAL_V2_EMBEDDING_API_KEY="$(cat "$KEY_FILE")" \
PYTHONUNBUFFERED=1 exec "$DEPLOY_PY" "$RUNNER" \
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
  --recorded-embedding-bundle "$BUNDLE" \
  --envelope-output "$ENVELOPE" \
  --accepted-original-milvus-path /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --accepted-original-milvus-sha256 43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc \
  --accepted-original-milvus-record-sha256 df3715a0be8560d523ce2abb589bdaf690e0fe07babcad26c03a4da0ad8cbe6b
