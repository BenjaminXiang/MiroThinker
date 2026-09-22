#!/usr/bin/env bash
# Alert watcher for the fembed build (PID 2077915).
#
# Why this exists: the embedding pass aborts the whole run on any transport error
# (no checkpoint, no retries). The 2-minute sampler records the *last* log line, so
# an error followed by more output would scroll past unnoticed. This watcher reads
# only the new bytes each tick and writes every hit to the alert log, plus a
# BUILD-ALERT marker file on a fatal signature — so a failure is visible within a
# minute instead of hours later.
#
#   bash build-fembed-20260922.alerts.sh <pid> <log> <alert-out> <marker>
set -uo pipefail

PID="$1"; LOG="$2"; OUT="$3"; MARKER="${4:-/nonexistent}"

# Fatal: the run cannot continue. Warning: needs a human look, not necessarily fatal.
FATAL='Traceback|TimeoutError|ConnectionError|vector audit|audit failed|refus|mismatch|differ'
BAD='\bERROR\b|\berror\b|HTTP 400|BadRequest|InvalidParameter|retry|reconnect'

OFFSET=0
: > "$OUT"

# Scan the bytes appended since the last call. MUST also run once after the process
# exits: on 2026-09-22 the fatal traceback (~6 KB) landed less than one 45 s tick
# before the process died, the `while kill -0` loop then exited without reading it,
# and the alert log kept only the EXITED line — the failure was found by a human
# instead. The final flush below closes that window.
scan_new_bytes() {
  local size hits
  size=$(stat -c %s "$LOG" 2>/dev/null || echo 0)
  (( size > OFFSET )) || return 0
  hits=$(tail -c +$((OFFSET + 1)) "$LOG" | head -c $((size - OFFSET)) \
    | grep -nE "$FATAL|$BAD" 2>/dev/null | head -20)
  if [[ -n "$hits" ]]; then
    { printf '%s pid=%s bytes=[%s,%s) SIG-HITS:\n' "$(date -Is)" "$PID" "$OFFSET" "$size"
      printf '%s\n' "$hits" | cut -c1-300; } >> "$OUT"
    if printf '%s\n' "$hits" | grep -qE "$FATAL"; then
      printf '%s FATAL signature seen; log=%s\n' "$(date -Is)" "$LOG" > "$MARKER"
    fi
  fi
  OFFSET=$size
}

while kill -0 "$PID" 2>/dev/null; do
  scan_new_bytes
  sleep 45
done
scan_new_bytes   # final flush — the bytes written just before exit
printf '%s pid=%s EXITED (rc unknown) log_bytes=%s\n' "$(date -Is)" "$PID" "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" >> "$OUT"
