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
while kill -0 "$PID" 2>/dev/null; do
  SIZE=$(stat -c %s "$LOG" 2>/dev/null || echo 0)
  if (( SIZE > OFFSET )); then
    HITS=$(tail -c +$((OFFSET + 1)) "$LOG" | head -c $((SIZE - OFFSET)) \
      | grep -nE "$FATAL|$BAD" 2>/dev/null | head -20)
    if [[ -n "$HITS" ]]; then
      { printf '%s pid=%s bytes=[%s,%s) SIG-HITS:\n' "$(date -Is)" "$PID" "$OFFSET" "$SIZE"
        printf '%s\n' "$HITS" | cut -c1-300; } >> "$OUT"
      if printf '%s\n' "$HITS" | grep -qE "$FATAL"; then
        printf '%s FATAL signature seen; log=%s\n' "$(date -Is)" "$LOG" > "$MARKER"
      fi
    fi
    OFFSET=$SIZE
  fi
  sleep 45
done
printf '%s pid=%s EXITED (rc unknown) log_bytes=%s\n' "$(date -Is)" "$PID" "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" >> "$OUT"
