#!/usr/bin/env bash
# agent-browser 包装：所有输出做密钥/口令脱敏后写 raw/04-browser.log
# 用法： ab.sh open http://127.0.0.1:18298/main
#       ab.sh snapshot -i
set -uo pipefail
EVDIR=/home/longxiang/MiroThinker/.worktrees/delivery-docker/.agents/runs/docker-fourth-verification-20260922
STATE=/var/tmp/mirothinker-fourth-verify-20260922/var/tmp/mirothinker-canonical-v2-s12f
LOG="$EVDIR/raw/04-browser.log"
KEY="$(cat /home/longxiang/MiroThinker/.deepseek_api_key 2>/dev/null || true)"
PW="$(sudo cat "$STATE/admin-initial-password.txt" 2>/dev/null || true)"

{
  echo "### $(date -Is)  agent-browser $*" | sed -e "s|${KEY}|<redacted-key>|g" -e "s|${PW}|<redacted-password>|g"
  agent-browser "$@" 2>&1 | sed -e "s|${KEY}|<redacted-key>|g" -e "s|${PW}|<redacted-password>|g"
  echo "### exit=${PIPESTATUS[0]}"
} | tee -a "$LOG"
