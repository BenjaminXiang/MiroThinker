#!/usr/bin/env bash
# Retire the star.sustech.edu.cn /guoxian entry on dbg21 (100.64.0.34).
#
# Context — openspec/changes/retire-star-domain-couplings, user decision
# 2026-10-15: the entry stays up until the school fixes a shutdown date; this
# script is the prepared, reversible removal to run on that day.
#
# What it does (on dbg21):
#   1. timestamped backup of /etc/nginx/conf.d/sustech-ai.conf
#   2. delete every `location ... /guoxian...` block (6 blocks today)
#   3. nginx -t, reload
#   4. verify: no guoxian location left, star host no longer served, gpu01 app
#      untouched (health 200 on gpu01:18188)
#
# Usage:
#   ssh longxiang@100.64.0.34 'bash -s -- --apply' < deploy/retire-star-entry.sh
#   bash deploy/retire-star-entry.sh --dry-run        # prints the diff only
set -euo pipefail

CONF="/etc/nginx/conf.d/sustech-ai.conf"
APP_HEALTH="http://100.64.0.4:18188/api/health"
MODE="${1:---dry-run}"
TS="$(date +%Y%m%d-%H%M%S)"

[[ -f "$CONF" ]] || { echo "FAIL: $CONF not found (run this on dbg21)"; exit 2; }

TMP="$(mktemp)"
awk '
  BEGIN { skip = 0; depth = 0 }
  /^[ \t]*location[ \t].*\/guoxian/ { skip = 1; depth = 0 }
  skip {
    opens = gsub(/\{/, "{"); closes = gsub(/\}/, "}")
    depth += opens - closes
    if (closes > 0 && depth <= 0) { skip = 0 }
    next
  }
  { print }
' "$CONF" > "$TMP"

if ! diff -u "$CONF" "$TMP"; then
  echo "--- diff shown above (removals prefixed with '-')"
else
  echo "no /guoxian blocks found — already retired?"
  rm -f "$TMP"
  exit 0
fi

if [[ "$MODE" != "--apply" ]]; then
  echo "[dry-run] nothing changed; re-run with --apply to execute"
  rm -f "$TMP"
  exit 0
fi

cp -a "$CONF" "$CONF.bak-retire-guoxian-$TS"
cat "$TMP" > "$CONF"
rm -f "$TMP"
nginx -t
systemctl reload nginx

echo "== verification =="
left="$(grep -c '/guoxian' "$CONF" || true)"
echo "guoxian blocks left in conf: $left"
served="$(curl -s -m 10 -o /dev/null -w '%{http_code}' -H 'Host: star.sustech.edu.cn' http://127.0.0.1:3001/guoxian/chat || true)"
echo "star host /guoxian/chat via dbg21: $served (expect 404)"
health="$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$APP_HEALTH" || true)"
echo "gpu01 app health: $health (expect 200)"
cat <<EOF

Rollback: cp -a $CONF.bak-retire-guoxian-$TS $CONF && nginx -t && systemctl reload nginx
After this script: the school side still needs the star gateway rule for
/guoxian removed; also tighten gpu01's firewall (deploy/firewall-18188.sh keeps
100.64.0.34 open only for this entry).
EOF
