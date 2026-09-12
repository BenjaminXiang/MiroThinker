#!/usr/bin/env bash
# Switch the 18188 serving unit between the deterministic order (OFF) and the
# relevance-model order (ON), then wait for readiness.
#
#   switch_rerank.sh on   -> drop-in rerank.conf active   (model ordering)
#   switch_rerank.sh off  -> drop-in parked as .pending   (deterministic order)
#   switch_rerank.sh stub -> model ordering, endpoint :18099 (fault injection)
#
# Only the staged/unstaged drop-in changes; the unit's ExecStart chain
# (deploy/start-canonical-v2.sh -> s12g/serve-18188-command.sh) is untouched.
set -euo pipefail

MODE="${1:?usage: switch_rerank.sh on|off|stub}"
DROPIN_DIR="$HOME/.config/systemd/user/canonical-v2-backend.service.d"
ACTIVE="$DROPIN_DIR/rerank.conf"
PENDING="$DROPIN_DIR/rerank.conf.pending"
STUB="$DROPIN_DIR/rerank-stub.conf.pending"
UNIT=canonical-v2-backend.service

case "$MODE" in
  on)
    [ -f "$PENDING" ] || { echo "missing $PENDING"; exit 2; }
    mv -f "$PENDING" "$ACTIVE"
    ;;
  off)
    [ -f "$ACTIVE" ] && mv -f "$ACTIVE" "$PENDING"
    ;;
  stub)
    [ -f "$ACTIVE" ] && mv -f "$ACTIVE" "$PENDING"
    [ -f "$STUB" ] || { echo "missing $STUB"; exit 2; }
    mv -f "$STUB" "$ACTIVE"
    ;;
  *)
    echo "unknown mode: $MODE"; exit 2
    ;;
esac

echo "[switch:$MODE] drop-ins now: $(ls "$DROPIN_DIR" | tr '\n' ' ')"
systemctl --user daemon-reload
systemctl --user restart "$UNIT"
date '+%H:%M:%S restarted'
for _ in $(seq 1 90); do
  if curl -sf --max-time 5 http://127.0.0.1:18188/api/health >/dev/null 2>&1; then
    echo "READY at $(date '+%H:%M:%S') mode=$MODE"
    exit 0
  fi
  sleep 20
done
echo NOTREADY
exit 1
