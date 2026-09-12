#!/usr/bin/env bash
# Probe batch: testset g2/g5 + generalization (+ its checker) + latency.
# Usage: run_probe_batch.sh <label>   ->  <label>-testset-g2g5.{json,log} etc.
set -u
LABEL="${1:?label required}"
BASE_URL="${BASE_URL:-http://127.0.0.1:18188}"
RUN_DIR="$(cd "$(dirname "$0")" && pwd)"
PROBES=/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps/generalization-probes
TESTSET=/home/longxiang/MiroThinker/.agents/runs/testset-baseline-20260909/run_testset.py

echo "[batch:$LABEL] start $(date '+%H:%M:%S') base=$BASE_URL"

python3 "$TESTSET" --base-url "$BASE_URL" --only 2,5 \
  --out "$RUN_DIR/$LABEL-testset-g2g5.json" 2>&1 | tee "$RUN_DIR/$LABEL-testset-g2g5.log"

python3 "$PROBES/probe_generalization.py" --base-url "$BASE_URL" \
  --out "$RUN_DIR/$LABEL-generalization.json" 2>&1 | tee "$RUN_DIR/$LABEL-generalization.log"

python3 "$PROBES/check_generalization.py" \
  --results "$RUN_DIR/$LABEL-generalization.json" 2>&1 | tee "$RUN_DIR/$LABEL-generalization-check.txt"

python3 "$PROBES/probe_latency.py" --base-url "$BASE_URL" \
  --out "$RUN_DIR/$LABEL-latency.json" 2>&1 | tee "$RUN_DIR/$LABEL-latency.log"

echo "[batch:$LABEL] done $(date '+%H:%M:%S')"
