#!/usr/bin/env bash
# Minimal run16 watchdog: one line every 5 minutes with pid, state, CPU time,
# written bytes (/proc/<pid>/io) and envelope size.  Detached; safe to ignore.
set -u
RUN_DIR=/home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/full-column-serving-pack-rebuild
LOG="$RUN_DIR/watchdog-run16.log"
ENVELOPE=/home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope.json
echo "$(date +%F_%H:%M:%S) watchdog started" >> "$LOG"
while true; do
  pid="$(pgrep -f '[\.]venv/bin/python3 .*complete_candidate_runner' | head -1)"
  pid="${pid:-$(pgrep -f 'complete_candidate_runner' | tail -1)}"
  stamp="$(date +%F_%H:%M:%S)"
  if [[ -z "$pid" ]]; then
    echo "$stamp runner-not-running" >> "$LOG"
  else
    state="$(ps -o stat= -p "$pid" 2>/dev/null | tr -d ' ')"
    cpu="$(ps -o time= -p "$pid" 2>/dev/null | tr -d ' ')"
    wchar="$(awk '/^wchar/ {print $2}' "/proc/$pid/io" 2>/dev/null)"
    env_size="$(stat -c %s "$ENVELOPE" 2>/dev/null || echo absent)"
    echo "$stamp pid=$pid state=$state cpu=$cpu wchar=$wchar envelope=$env_size" >> "$LOG"
  fi
  sleep 300
done
