#!/usr/bin/env bash
# 18188 收口：只放行本机回环与 dbg21 nginx（100.64.0.34），其余来源 DROP。
# 幂等：先删同规格旧规则再按固定顺序插入。需要 root（systemd unit 调用）。
set -euo pipefail

SPECS=(
  "-p tcp --dport 18188 -s 127.0.0.0/8 -j ACCEPT"
  "-p tcp --dport 18188 -s 100.64.0.34 -j ACCEPT"
  "-p tcp --dport 18188 -j DROP"
)

if [ "${1:-apply}" = "remove" ]; then
  for spec in "${SPECS[@]}"; do
    # shellcheck disable=SC2086
    iptables -D INPUT $spec 2>/dev/null || true
  done
  echo "18188 firewall rules removed"
  exit 0
fi

for spec in "${SPECS[@]}"; do
  # shellcheck disable=SC2086
  iptables -D INPUT $spec 2>/dev/null || true
done
for i in 0 1 2; do
  # shellcheck disable=SC2086
  iptables -I INPUT $((i + 1)) ${SPECS[$i]}
done
echo "18188 firewall rules applied: allow 127.0.0.0/8 + 100.64.0.34, drop others"
