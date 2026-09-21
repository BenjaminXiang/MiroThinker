#!/usr/bin/env bash
# 命题 3（第 1 次）：按 CONFIG-GUIDE §2 的原文命令放 key，然后 **sudo** 跑 v1.1 原版安装器。
# 预期：暴露 root 属主导致的运行时不可读/不可写。健康等待上限 300 s 以控制成本。
set -uo pipefail
B=/home/longxiang/delivery-xfer-v11/site-bundle
SITE_ROOT=/var/tmp/mirothinker-fourth-verify-20260922
PORT=18298
PGVOL=mirothinker-pgdata-fourth-v11
cd "$B" || exit 1

echo "== 0. 交付包当前状态（传输后副本） =="
ls -la secrets/ 2>/dev/null || echo "(secrets/ 不存在)"
echo

echo "== 1. 放 4 个 key（CONFIG-GUIDE §2 的原文命令，sudo install -m 600） =="
for pair in "deepseek:/home/longxiang/MiroThinker/.deepseek_api_key" \
            "bocha:/home/longxiang/MiroThinker/.bocha_api_key" \
            "serper:/home/longxiang/MiroThinker/.serper_api_key" \
            "sglang:/home/longxiang/MiroThinker/.sglang_api_key"; do
  name="${pair%%:*}"; src="${pair#*:}"
  sudo install -m 600 "$src" "secrets/.${name}_api_key" && echo "  placed secrets/.${name}_api_key (内容未回显)"
done
echo "  落位后的属主/权限（无内容）："
sudo ls -l secrets/
echo "  ⇒ 注意：全部 root:root 0600（这就是甲方第一条命令的样子）"
echo

echo "== 2. sudo ./install-site.sh --dry-run（runbook 推荐先跑） =="
sudo env MIROTHINKER_SITE_ROOT="$SITE_ROOT" MIROTHINKER_SITE_PORT="$PORT" \
     MIROTHINKER_SITE_PG_VOLUME="$PGVOL" ./install-site.sh --dry-run
echo "  dry-run exit=$?"
echo

echo "== 3. sudo ./install-site.sh（正式；健康等待上限 300 s） =="
t0=$(date +%s)
sudo env MIROTHINKER_SITE_ROOT="$SITE_ROOT" MIROTHINKER_SITE_PORT="$PORT" \
     MIROTHINKER_SITE_PG_VOLUME="$PGVOL" MIROTHINKER_SITE_FORCE_LOAD=1 \
     ./install-site.sh --timeout-seconds 300
rc=$?
echo "install exit=$rc  总耗时=$(date -Is)  $(( $(date +%s) - t0 ))s"
echo

echo "== 4. 失败现场（若失败） =="
echo "-- 宿主侧属主："
sudo ls -ld "$SITE_ROOT" "$SITE_ROOT/var/tmp" "$SITE_ROOT/var/tmp/mirothinker-canonical-v2-s12f" \
            "$SITE_ROOT/var/tmp/mirothinker-data-v2" "$SITE_ROOT/var/tmp/mirothinker-data-v2/index-v3-v2" 2>&1
echo "-- .env（无内容敏感项）:"
sudo sh -c "grep -E 'UID|GID|PORT' '$B/.env'"
echo "-- 容器状态 / 重启次数 / 退出码："
sudo docker compose -f "$B/compose.yaml" ps -a 2>&1 | head -10
for cid in $(sudo docker compose -f "$B/compose.yaml" ps -q app 2>/dev/null); do
  sudo docker inspect -f 'app container: status={{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}} oom={{.State.OOMKilled}}' "$cid"
done
echo "-- app 日志尾部："
sudo docker compose -f "$B/compose.yaml" logs --tail 25 app 2>&1 | tail -30
echo "-- db 状态："
sudo docker inspect -f 'db: status={{.State.Status}} health={{.State.Health.Status}}' \
  "$(sudo docker compose -f "$B/compose.yaml" ps -q db 2>/dev/null)" 2>/dev/null
