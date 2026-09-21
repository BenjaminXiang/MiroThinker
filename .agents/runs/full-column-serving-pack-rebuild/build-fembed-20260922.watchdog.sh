#!/usr/bin/env bash
# Sampler for the fembed build (watchdog-run16.sh's shape): one line every
# 2 minutes with pid/state/cpu/rss/log-bytes and the log's last real line, so a
# later reader can tell "advancing" from "stalled" without replaying the log.
#
#   bash build-fembed-20260922.watchdog.sh <pid> <log> <out>
set -uo pipefail

PID="$1"
LOG="$2"
OUT="$3"

while kill -0 "$PID" 2>/dev/null; do
  sample=$(ps -o stat=,time=,rss=,pcpu= -p "$PID" 2>/dev/null | tr -s ' ')
  bytes=$(stat -c %s "$LOG" 2>/dev/null || echo 0)
  last=$(grep -v '^$' "$LOG" 2>/dev/null | tail -1 | cut -c1-160)
  printf '%s pid=%s ps=[%s] log_bytes=%s last=%s\n' \
    "$(date -Is)" "$PID" "${sample:-gone}" "$bytes" "${last:-<none>}" >> "$OUT"
  sleep 120
done
printf '%s pid=%s EXITED\n' "$(date -Is)" "$PID" >> "$OUT"
