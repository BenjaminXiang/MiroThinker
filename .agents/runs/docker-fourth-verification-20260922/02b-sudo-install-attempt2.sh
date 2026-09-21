#!/usr/bin/env bash
# 命题 3（第 2 次）：v1.1 原版安装器（只把两个 /tmp 固定路径换成唯一名）+ sudo。
# 目的：暴露"真 root 安装"特有的宿主属主问题（状态目录 root:root 0700）。
set -uo pipefail
B=/home/longxiang/delivery-xfer-v11/site-bundle
SITE_ROOT=/var/tmp/mirothinker-fourth-verify-20260922
PORT=18298
PGVOL=mirothinker-pgdata-fourth-v11
cd "$B" || exit 1

echo "== 1. secrets/ 目录（交付包里没有；按文档落 key 前必须先建） =="
sudo mkdir -p secrets && echo "  created $PWD/secrets"
for pair in "deepseek:.deepseek_api_key" "bocha:.bocha_api_key" "serper:.serper_api_key" "sglang:.sglang_api_key"; do
  name="${pair%%:*}"
  sudo install -m 600 "/home/longxiang/MiroThinker/.${name}_api_key" "secrets/.${name}_api_key"
done
sudo ls -l secrets/
echo

echo "== 2. sudo 安装（v1.1 原版 + 唯一 /tmp 路径；健康等待上限 200 s） =="
t0=$(date +%s)
sudo env MIROTHINKER_SITE_ROOT="$SITE_ROOT" MIROTHINKER_SITE_PORT="$PORT" \
     MIROTHINKER_SITE_PG_VOLUME="$PGVOL" \
     ./install-site-attempt2.sh --timeout-seconds 200
rc=$?
echo "install exit=$rc  总耗时=$(( $(date +%s) - t0 ))s"
echo

echo "== 3. 失败现场 =="
echo "-- 宿主侧属主（root 建的目录 vs 数据属主）："
sudo stat -c '%-70n owner=%U:%G mode=%a' \
  "$SITE_ROOT" "$SITE_ROOT/var/tmp" "$SITE_ROOT/var/tmp/mirothinker-data-v2" \
  "$SITE_ROOT/var/tmp/mirothinker-data-v2/index-v3-v2" \
  "$SITE_ROOT/var/tmp/mirothinker-canonical-v2-s12f" 2>&1
echo "-- .env："
sudo stat -c '%n owner=%U:%G mode=%a' "$B/.env" 2>&1
sudo grep -E 'MIROTHINKER_UID|MIROTHINKER_GID|MIROTHINKER_HOST_PORT' "$B/.env" 2>&1
echo "-- 容器："
sudo docker compose -f "$B/compose.yaml" ps -a 2>&1 | head -6
for cid in $(sudo docker compose -f "$B/compose.yaml" ps -aq app 2>/dev/null); do
  sudo docker inspect -f 'app: status={{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}} oom={{.State.OOMKilled}}' "$cid"
done
echo "-- app 日志（entrypoint 预检）："
sudo docker compose -f "$B/compose.yaml" logs --tail 20 app 2>&1 | tail -22
echo "-- db："
sudo docker inspect -f 'db: status={{.State.Status}} health={{.State.Health.Status}}' \
  "$(sudo docker compose -f "$B/compose.yaml" ps -aq db 2>/dev/null)" 2>/dev/null
