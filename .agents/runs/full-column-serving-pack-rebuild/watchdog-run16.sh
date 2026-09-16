#!/usr/bin/env bash
# run16 watchdog + failure reporter.
#
# Every 5 minutes: sample the runner (pid, state, cpu seconds, written bytes,
# envelope size).  Two extra duties:
#   1) SUSPECT-STALL: the process is alive but its CPU time stopped growing for
#      two consecutive samples -> capture a py-spy stack to /tmp and flag it
#      (the known long phases burn ~100% CPU, so frozen CPU = a hang);
#   2) FAILURE DOSSIER: the moment the runner disappears, write
#      run16-failure-report-<ts>.md once (log tails + artifact state) so triage
#      starts immediately instead of hunting for context.
set -u
RUN_DIR=/home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/full-column-serving-pack-rebuild
LOG="$RUN_DIR/watchdog-run16.log"
BUILD_LOG="$RUN_DIR/build-run16.log"
NOHUP_LOG="$RUN_DIR/build-run16-detached-nohup.log"
ENVELOPE=/home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope.json
REPORT_FLAG="$RUN_DIR/.run16-failure-reported"

echo "$(date +%F_%H:%M:%S) watchdog started (failure-reporter build)" >> "$LOG"
prev_utime=""
frozen_rounds=0
while true; do
  pid="$(pgrep -f 'complete_candidate_runner\.py --database-url' | tail -1)"
  stamp="$(date +%F_%H:%M:%S)"
  if [[ -z "$pid" ]]; then
    echo "$stamp runner-not-running" >> "$LOG"
    if [[ ! -e "$REPORT_FLAG" ]]; then
      report="$RUN_DIR/run16-failure-report-$(date +%Y%m%d-%H%M%S).md"
      {
        echo "# run16 failure dossier"
        echo
        echo "- detected: $(date +%F_%H:%M:%S) (runner process absent)"
        echo "- last sample above; see watchdog-run16.log for the last live line"
        echo
        echo "## build-run16.log (tail -40)"
        echo '```'
        tail -40 "$BUILD_LOG" 2>&1 || true
        echo '```'
        echo
        echo "## build-run16-detached-nohup.log (tail -25)"
        echo '```'
        tail -25 "$NOHUP_LOG" 2>&1 || true
        echo '```'
        echo
        echo "## artifacts"
        echo '```'
        echo "envelope: $(stat -c '%s bytes, mtime %y' "$ENVELOPE" 2>&1 || echo absent)"
        ls -ld /var/tmp/mirothinker-data-v2/staging-v3 /var/tmp/mirothinker-data-v2/index-v3 2>&1 || true
        du -sh /var/tmp/mirothinker-data-v2/staging-v3 /var/tmp/mirothinker-data-v2/index-v3 2>/dev/null || true
        echo '```'
        echo
        echo "## triage checklist"
        echo "1. first failing line in the traceback chain (cause is printed last in the chain);"
        echo "2. if it is the publication gate: the message now names offenders (domain.field_path: value);"
        echo "3. relaunch only after a fix + targeted tests; archive staging-v3/index-v3 first."
      } > "$report"
      touch "$REPORT_FLAG"
      echo "$stamp FAILURE DOSSIER WRITTEN: $report" >> "$LOG"
    fi
  else
    [[ -e "$REPORT_FLAG" ]] && rm -f "$REPORT_FLAG"  # a live runner means a new attempt
    state="$(ps -o stat= -p "$pid" 2>/dev/null | tr -d ' ')"
    utime="$(awk '{print $14}' "/proc/$pid/stat" 2>/dev/null || echo 0)"
    cpu="$(ps -o time= -p "$pid" 2>/dev/null | tr -d ' ')"
    wchar="$(awk '/^wchar/ {print $2}' "/proc/$pid/io" 2>/dev/null)"
    env_size="$(stat -c %s "$ENVELOPE" 2>/dev/null || echo absent)"
    echo "$stamp pid=$pid state=$state cpu=$cpu utime=$utime wchar=$wchar envelope=$env_size" >> "$LOG"
    if [[ -n "$prev_utime" && "$utime" == "$prev_utime" ]]; then
      frozen_rounds=$((frozen_rounds + 1))
    else
      frozen_rounds=0
    fi
    prev_utime="$utime"
    if (( frozen_rounds >= 2 )); then
      stack="/tmp/run16-stall-$(date +%Y%m%d-%H%M%S).txt"
      sudo -n env "PATH=$PATH" py-spy dump --pid "$pid" > "$stack" 2>&1 || true
      echo "$stamp SUSPECT-STALL cpu frozen ${frozen_rounds} rounds; stack -> $stack" >> "$LOG"
    fi
  fi
  sleep 300
done
