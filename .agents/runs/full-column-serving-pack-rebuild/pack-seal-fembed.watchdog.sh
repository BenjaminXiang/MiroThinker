#!/usr/bin/env bash
# Sampler for the fembed seal: one line every 2 minutes with pid/cpu/rss and the
# log's last line (the sealer prints phase=<name> lines), so a later reader can tell
# "advancing" from "stalled" without replaying the log.
set -uo pipefail
PID="$1"; LOG="$2"; OUT="$3"
while kill -0 "$PID" 2>/dev/null; do
  s=$(ps -o stat=,time=,rss=,pcpu= -p "$PID" 2>/dev/null | tr -s ' ')
  printf '%s pid=%s ps=[%s] log_bytes=%s last=%s\n' \
    "$(date -Is)" "$PID" "${s:-gone}" "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" \
    "$(grep -v '^$' "$LOG" 2>/dev/null | tail -1 | cut -c1-150)" >> "$OUT"
  sleep 120
done
printf '%s pid=%s EXITED log_bytes=%s\n' "$(date -Is)" "$PID" "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" >> "$OUT"
