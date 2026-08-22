#!/usr/bin/env bash
# Start or restart the light-lane API on 127.0.0.1:18201 (idempotent).
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$DIR/.env" ]; then
  set -a; . "$DIR/.env"; set +a
fi

if [ -n "${LIGHT_LANE_VENV_PYTHON:-}" ]; then
  VENV="$LIGHT_LANE_VENV_PYTHON"
elif [ -x "$DIR/.venv/bin/python" ]; then
  VENV="$DIR/.venv/bin/python"
else
  VENV=/home/longxiang/MiroThinker/apps/admin-console/.venv/bin/python
fi

for pid in $(ps -eo pid,cmd | awk '/api[.]py/ && /admin-console/ {print $1}'); do
  kill "$pid" 2>/dev/null || true
done
sleep 1

cd "$DIR"
nohup "$VENV" api.py > api.log 2>&1 &
sleep 4

if curl -s -m 5 http://127.0.0.1:18201/healthz; then
  echo
  echo "light-lane API up: http://127.0.0.1:18201/"
else
  echo "FAILED to start; see $DIR/api.log" >&2
  exit 1
fi
