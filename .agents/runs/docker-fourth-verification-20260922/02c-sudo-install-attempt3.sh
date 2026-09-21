#!/usr/bin/env bash
# 命题 3（第 3 次）：换成**修好的** install-site.sh（属主归一 + mktemp + --no-up），
# 真 root 安装跑到全通。同一 site root（幂等重跑），并强制 docker load 走一遍传送后的
# tar.gz（证明跨 fs 拷贝出来的镜像归档可直接 load）。
set -uo pipefail
B=/home/longxiang/delivery-xfer-v11/site-bundle
W=/home/longxiang/MiroThinker/.worktrees/delivery-docker/deploy/docker
SITE_ROOT=/var/tmp/mirothinker-fourth-verify-20260922
PORT=18298
PGVOL=mirothinker-pgdata-fourth-v11
cd "$B" || exit 1

echo "== 0. 换用修好的安装器（机制修复；v2 重打交付件时自动带上） =="
cp -a install-site.sh install-site.v11-orig.sh
install -m 0755 "$W/install-site.sh" install-site.sh
echo "  install-site.sh: $(sha256sum install-site.sh | cut -c1-16)…  （原版留档 install-site.v11-orig.sh）"
echo "  修复点：① /tmp 固定文件 → mktemp；② 真 root 下宿主侧属主归一（数据属主）；③ --no-up 生效"
echo

echo "== 1. sudo 安装（全量校验 + 强制 docker load + 默认健康等待 900 s） =="
t0=$(date +%s)
sudo env MIROTHINKER_SITE_ROOT="$SITE_ROOT" MIROTHINKER_SITE_PORT="$PORT" \
     MIROTHINKER_SITE_PG_VOLUME="$PGVOL" MIROTHINKER_SITE_FORCE_LOAD=1 \
     ./install-site.sh
rc=$?
echo "install exit=$rc  总耗时=$(( $(date +%s) - t0 ))s"
echo

echo "== 2. 落位后的属主/权限（root 安装下最该看的东西） =="
sudo stat -c '%-72n owner=%U:%G mode=%a' \
  "$SITE_ROOT/var/tmp/mirothinker-data-v2" \
  "$SITE_ROOT/var/tmp/mirothinker-data-v2/index-v3-v2" \
  "$SITE_ROOT/var/tmp/mirothinker-canonical-v2-s12f" \
  "$B/secrets" "$B/secrets/.sglang_api_key" "$B/state/config-managed" "$B/state/logs" "$B/.env" 2>&1
echo "-- 容器内视角：数据面与状态目录的可读/可写（容器 uid=$(sudo docker compose -f "$B/compose.yaml" exec -T app id -un 2>/dev/null || echo '?')）:"
sudo docker compose -f "$B/compose.yaml" exec -T app sh -lc \
  'id; echo "key readable: $(test -r /opt/mirothinker/.sglang_api_key && echo yes || echo NO)"; echo "state writable: $(touch /var/tmp/mirothinker-canonical-v2-s12f/.probe && echo yes && rm -f /var/tmp/mirothinker-canonical-v2-s12f/.probe || echo NO)"' 2>&1
echo
echo "== 3. 普通用户视角（非 sudo） =="
echo "-- 普通用户读 .env（docker compose 要它）:"
head -c 0 "$B/.env" 2>&1 || true
if head -c 0 "$B/.env" 2>/dev/null; then echo "  可读"; else echo "  ✗ 不可读（$B/.env 是 root 的；非 sudo 的 docker compose 会失败）"; fi
echo "-- 非 sudo docker compose ps（在包里）："
( cd "$B" && docker compose ps 2>&1 | head -5 ); echo "  exit=$?"
echo "-- 状态目录（含首启口令）普通用户能否读："
ls "$SITE_ROOT/var/tmp/mirothinker-canonical-v2-s12f/admin-initial-password.txt" 2>&1 || true
