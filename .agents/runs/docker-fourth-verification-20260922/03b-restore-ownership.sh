#!/usr/bin/env bash
# 反向实验收尾：把 key 属主归一（这一步正是安装器该做的），**只 restart** 一次复原。
# 这一段同时给出两个结论：
#   ① 复原（服务回到 ok:true/200）；
#   ② 再次印证"restart 足够"——这次是**可读**的新文件，容器内 hash 应立刻等于宿主 hash。
set -uo pipefail
B=/home/longxiang/delivery-xfer-v11/site-bundle
SITE_ROOT=/var/tmp/mirothinker-fourth-verify-20260922
STATE="$SITE_ROOT/var/tmp/mirothinker-canonical-v2-s12f"
PORT=18298
EVDIR=/home/longxiang/MiroThinker/.worktrees/delivery-docker/.agents/runs/docker-fourth-verification-20260922
cd "$B" || exit 1

echo "== 0. 复原前的状态（D1 之后） =="
sudo stat -c 'host: %n owner=%U:%G mode=%a inode=%i' secrets/.sglang_api_key
echo "host hash: $(sudo sha256sum secrets/.sglang_api_key | cut -c1-12)"
echo "container: $(sudo docker compose -f "$B/compose.yaml" exec -T app sha256sum /opt/mirothinker/.sglang_api_key 2>&1 | cut -c1-60)"

echo "== 1. 属主归一（= install-site.sh 现在会自动做的事），然后只 restart =="
sudo chown 1004:1004 secrets/.sglang_api_key
sudo stat -c 'host: %n owner=%U:%G mode=%a inode=%i' secrets/.sglang_api_key
echo "host hash: $(sudo sha256sum secrets/.sglang_api_key | cut -c1-12)"
sudo docker compose -f "$B/compose.yaml" restart app
sleep 12
echo "restart 后容器内看到的：$(sudo docker compose -f "$B/compose.yaml" exec -T app sha256sum /opt/mirothinker/.sglang_api_key 2>&1 | cut -c1-12)  ← 应等于宿主 hash"

t0=$(date +%s)
while (( $(date +%s) - t0 < 420 )); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null)" == "200" ]] \
    && { echo "health OK after $(( $(date +%s) - t0 ))s"; break; }
  sleep 5
done
echo "== 2. 复原后的连接测试 =="
python3 "$EVDIR/key_probe.py" "$PORT" "$STATE" "$EVDIR/raw/03-E-restored-readable.json" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({"login":d["login"], **d.get("summary",{}), "raw_detail":(d["embedding_test"]["body"] or {}).get("detail")}, ensure_ascii=False))'
