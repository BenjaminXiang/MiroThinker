#!/usr/bin/env bash
# Wait for the scratch line, then capture the two highest-value probes.
set -u
cd /home/longxiang/MiroThinker/.worktrees/web-lane-topical-floor
for _ in $(seq 1 40); do
  code=$(curl -s -m 4 -o /dev/null -w "%{http_code}" http://127.0.0.1:18295/api/health)
  if [ "$code" = "200" ]; then break; fi
  sleep 15
done
echo "health=$code at $(date '+%H:%M:%S')"
if [ "$code" != "200" ]; then echo "SCRATCH NOT READY"; exit 1; fi
uv run python .agents/runs/web-lane-topical-floor/probe_scratch.py \
  --base-url http://127.0.0.1:18295 \
  --query "详细介绍一下 国先中心（深圳）" \
  --out .agents/runs/web-lane-topical-floor/scratch/user-case-final.json
uv run python .agents/runs/web-lane-topical-floor/probe_scratch.py \
  --base-url http://127.0.0.1:18295 \
  --query "深圳有哪些做机器人的公司" \
  --out .agents/runs/web-lane-topical-floor/scratch/enumeration-final.json
echo "PROBES DONE at $(date '+%H:%M:%S')"
