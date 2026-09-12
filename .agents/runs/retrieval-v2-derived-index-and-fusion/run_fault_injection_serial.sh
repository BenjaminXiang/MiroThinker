#!/usr/bin/env bash
# Serial fault injection for the rerank lane on 18188.
#
#   malformed  -> drop-in points at the local stub (:18099), stub answers a
#                 payload the adapter must reject
#   refused    -> the stub is stopped first, so the same instance now sees a
#                 refused connection
#
# Both modes drive one real /api/chat/stream turn. The run then restores the
# drop-in directory to the OFF state by content (switch_rerank.sh stub|off
# renames *.pending and would overwrite the real ON config with the stub one).
#
# Never prints the credential.
set -uo pipefail

HERE="$HOME/MiroThinker/.agents/runs/retrieval-v2-derived-index-and-fusion"
DROPIN="$HOME/.config/systemd/user/canonical-v2-backend.service.d"
UNIT=canonical-v2-backend.service
BK="$HERE/dropin-backup-20260913"
STAMP="$(date '+%Y%m%d-%H%M%S')"
LOG="$HERE/fault-injection-serial-$STAMP.log"

exec > >(tee -a "$LOG") 2>&1

step() { echo; echo "=== [$(date '+%H:%M:%S')] $* ==="; }

wait_ready() {
  for _ in $(seq 1 90); do
    if curl -sf --max-time 5 http://127.0.0.1:18188/api/health >/dev/null 2>&1; then
      echo "READY at $(date '+%H:%M:%S')"
      return 0
    fi
    sleep 20
  done
  echo "NOTREADY"
  return 1
}

step "phase 0: preconditions"
curl -s -m 5 http://127.0.0.1:18188/api/health || { echo "18188 down"; exit 2; }
echo
echo "active drop-ins: $(ls "$DROPIN" | tr '\n' ' ')"
echo "journal cursor: $(date '+%Y-%m-%d %H:%M:%S')"
JOURNAL_FROM="$(date '+%Y-%m-%d %H:%M:%S')"
echo "$JOURNAL_FROM" > "$HERE/fault-injection-journal-from.txt"
sha256sum "$BK"/* | sed "s#$HERE/##"

step "phase 1: start the malformed-payload stub on :18099"
pkill -f fault_stub_rerank.py >/dev/null 2>&1 || true
sleep 1
nohup python3 "$HERE/fault_stub_rerank.py" >/dev/null 2>&1 &
sleep 2
curl -s -m 5 -X POST http://127.0.0.1:18099/v1/rerank -H 'Content-Type: application/json' \
  -d '{"query":"q","documents":["a"]}'; echo
echo "stub pid: $(pgrep -f fault_stub_rerank.py | tr '\n' ' ')"

step "phase 2: switch the unit to the stub endpoint"
"$HERE/switch_rerank.sh" stub || { echo "switch stub failed"; exit 3; }

step "phase 3: real turn under malformed payload"
FAULT_QUERY="${FAULT_QUERY:-深圳有哪些做激光雷达的公司}" \
  "$HERE/run_fault_injection.sh" malformed stub

step "phase 4: stop the stub -> refused connection"
pkill -f fault_stub_rerank.py >/dev/null 2>&1 || true
sleep 2
if curl -s -m 3 -X POST http://127.0.0.1:18099/v1/rerank -d '{}' >/dev/null 2>&1; then
  echo "WARNING: stub still answering"
else
  echo "stub stopped, :18099 refuses connections"
fi

step "phase 5: real turn under refused connection"
FAULT_QUERY="${FAULT_QUERY:-深圳有哪些做激光雷达的公司}" \
  "$HERE/run_fault_injection.sh" refused refused

step "phase 6: restore the drop-in directory to the OFF state (by content)"
rm -f "$DROPIN/rerank.conf"
cp -p "$BK/rerank.conf.on-active"   "$DROPIN/rerank.conf.pending"
cp -p "$BK/rerank-stub.conf.parked" "$DROPIN/rerank-stub.conf.pending"
ls -la "$DROPIN"
systemctl --user daemon-reload
systemctl --user restart "$UNIT"
echo "restarted at $(date '+%H:%M:%S'); waiting for health"
wait_ready || { echo "final restart did not become ready"; exit 4; }

step "phase 7: verify the final state"
echo "active drop-ins: $(ls "$DROPIN" | tr '\n' ' ')"
echo "rerank env in the running unit (expect none):"
tr '\0' '\n' < "/proc/$(systemctl --user show "$UNIT" -p MainPID --value)/environ" \
  | grep -E '^CANONICAL_V2_RERANK' | sed 's/\(API_KEY=\).*/\1<redacted>/' || echo "  (none)"
echo "lexical env:"
tr '\0' '\n' < "/proc/$(systemctl --user show "$UNIT" -p MainPID --value)/environ" \
  | grep -E '^CANONICAL_V2_LEXICAL' || echo "  (none)"
curl -s -m 5 http://127.0.0.1:18188/api/health; echo
sha256sum "$BK"/* | sed "s#$HERE/##"
sha256sum "$DROPIN"/rerank.conf.pending "$DROPIN"/rerank-stub.conf.pending

step "phase 8: fallback evidence in the service journal"
journalctl --user -u "$UNIT" --no-pager --since "$JOURNAL_FROM" \
  | grep -iE "rerank|fell back" | sed 's/[[:space:]]\+/ /g' | cut -c1-260 || echo "(no rerank lines)"
echo
echo "journal line count in window: $(journalctl --user -u "$UNIT" --no-pager --since "$JOURNAL_FROM" | wc -l)"

step "phase 9: artifact leak check (no credential, no candidate text)"
for f in "$HERE"/fault-injection-*.txt "$HERE"/fault-injection-*.json; do
  [ -f "$f" ] || continue
  printf '%s: bearer=%s keyfile_ref=%s\n' "$(basename "$f")" \
    "$(grep -c 'Bearer ' "$f" || true)" \
    "$(grep -c 'rerank-api-key' "$f" || true)"
done

step "done"
echo "log: $LOG"
