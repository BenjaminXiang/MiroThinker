#!/usr/bin/env bash
# 命题 3（第 3 次补跑）：上次被工具超时打断在"健康检查通过"之后（log 停在 7m32s，
# 但 /api/health 已 200）。服务已在跑 ⇒ 重跑安装器（幂等）拿一份完整记录：
# exit 0 + ok/warn/FAIL + 容器内验收探针。
set -uo pipefail
B=/home/longxiang/delivery-xfer-v11/site-bundle
SITE_ROOT=/var/tmp/mirothinker-fourth-verify-20260922
PORT=18298
PGVOL=mirothinker-pgdata-fourth-v11
cd "$B" || exit 1

echo "== 0. 前一次被打断时的现场 =="
echo "-- health: $(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${PORT}/api/health")"
echo "-- 容器 StartedAt / 重启次数："
cid="$(sudo docker compose -f "$B/compose.yaml" ps -q app)"
sudo docker inspect -f 'StartedAt={{.State.StartedAt}} restarts={{.RestartCount}} status={{.State.Status}} health={{.State.Health.Status}}' "$cid"
echo "-- 首启耗时（对比容器 StartedAt 与 health 首次 200 的时间）："
echo "   安装器记录：…已等 7m32s 后 /api/health 200（见 raw/02c-sudo-attempt3.log 末尾）"
echo

echo "== 1. 幂等重跑安装器（服务已在跑，健康检查应立刻通过） =="
t0=$(date +%s)
sudo env MIROTHINKER_SITE_ROOT="$SITE_ROOT" MIROTHINKER_SITE_PORT="$PORT" \
     MIROTHINKER_SITE_PG_VOLUME="$PGVOL" ./install-site.sh
rc=$?
echo "install exit=$rc  总耗时=$(( $(date +%s) - t0 ))s"
echo

echo "== 2. 属主/权限终态 =="
sudo stat -c '%-72n owner=%U:%G mode=%a' \
  "$SITE_ROOT/var/tmp/mirothinker-data-v2" \
  "$SITE_ROOT/var/tmp/mirothinker-data-v2/index-v3-v2" \
  "$SITE_ROOT/var/tmp/mirothinker-canonical-v2-s12f" \
  "$B/secrets" "$B/secrets/.sglang_api_key" "$B/state/config-managed" "$B/state/logs" "$B/.env"
echo "-- 容器内视角："
sudo docker compose -f "$B/compose.yaml" exec -T app sh -lc \
  'echo "uid=$(id -u) key_readable=$(test -r /opt/mirothinker/.sglang_api_key && echo yes || echo NO) state_writable=$(touch /var/tmp/mirothinker-canonical-v2-s12f/.probe 2>/dev/null && echo yes && rm -f /var/tmp/mirothinker-canonical-v2-s12f/.probe || echo NO)"'
echo
echo "== 3. 普通用户（非 sudo）视角 =="
if head -c 0 "$B/.env" 2>/dev/null; then echo "  .env 可读（非 sudo compose 可用）"; else echo "  ✗ .env 不可读"; fi
( cd "$B" && docker compose ps 2>&1 | head -4 )
echo "-- 首启口令文件（容器内生成了吗）："
sudo ls -l "$SITE_ROOT/var/tmp/mirothinker-canonical-v2-s12f/" | head -12
