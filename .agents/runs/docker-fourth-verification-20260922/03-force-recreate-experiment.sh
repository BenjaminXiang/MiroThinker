#!/usr/bin/env bash
# 命题 1：--force-recreate 的**反向实验**（判决性，全部结论由观测支撑）
#
#   A. 基线：容器已 boot，宿主/容器内看到的 key 一致，嵌入连接测试 OK
#   B. 文档命令（sudo install -m 600 /dev/stdin …）换成一个**故意错的** key（in-place，inode 不变）
#        B1 运行中的容器是否立刻看到新字节？（文件级）
#        B2 docker compose restart app → 容器内看到什么？（文件级，容器刚起 10 s 内）
#        B3 等健康 → 管理员"测试"（功能级）：服务是按旧 key 还是新 key 工作？
#   C. 若 B3 = 仍按旧 key 工作 → 按指南 --force-recreate → 文件级 + 功能级
#      若 B3 = 已按新 key 工作 → 文档的"必须 --force-recreate"是过度保守；再做 inode 级对照
#   D. 换回真 key（文档命令）+ --force-recreate（文档给出的"文件方式"命令）→ 复原
#
# 全程不回显密钥内容；只打印路径、inode、sha256 前 12 位与连接测试响应。
set -uo pipefail
B=/home/longxiang/delivery-xfer-v11/site-bundle
SITE_ROOT=/var/tmp/mirothinker-fourth-verify-20260922
STATE="$SITE_ROOT/var/tmp/mirothinker-canonical-v2-s12f"
PORT=18298
EVDIR=/home/longxiang/MiroThinker/.worktrees/delivery-docker/.agents/runs/docker-fourth-verification-20260922
REAL_KEY=/home/longxiang/MiroThinker/.sglang_api_key
KEY="secrets/.sglang_api_key"
cd "$B" || exit 1
dc() { sudo docker compose -f "$B/compose.yaml" "$@"; }
ts() { date '+%H:%M:%S'; }

host_hash() { sudo sha256sum "$KEY" | cut -c1-12; }
host_inode() { sudo stat -c '%i' "$KEY"; }
ctr_hash() { dc exec -T app sha256sum /opt/mirothinker/.sglang_api_key 2>/dev/null | cut -c1-12; }
wait_health() {
  local deadline=$(( $(date +%s) + ${1:-400} )) t0=$(date +%s)
  while (( $(date +%s) < deadline )); do
    [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null)" == "200" ]] \
      && { echo "    health OK after $(( $(date +%s) - t0 ))s"; return 0; }
    sleep 5
  done
  echo "    health TIMEOUT after $(( $(date +%s) - t0 ))s（容器状态：$(dc ps --format '{{.Status}}' | tr '\n' ' ')）"
  return 1
}
probe() { python3 "$EVDIR/key_probe.py" "$PORT" "$STATE" "$1" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({"login":d["login"], **d.get("summary",{}), "raw":d["embedding_test"]["body"]}, ensure_ascii=False))'; }

echo "===== A. 基线（$(ts)） ====="
echo "host:  inode=$(host_inode) hash=$(host_hash)"
echo "container: hash=$(ctr_hash)"
probe "$EVDIR/raw/03-A-baseline.json" | tee "$EVDIR/raw/03-A-baseline.txt"
echo

echo "===== B. 文档命令换成一个故意错的 key（in-place） ====="
i0=$(host_inode)
printf 'deliberately-wrong-key-for-inode-experiment\n' | sudo install -m 600 /dev/stdin "$KEY"
i1=$(host_inode)
echo "host: inode $i0 -> $i1  $([[ "$i0" == "$i1" ]] && echo '(install 是 in-place：inode 不变)' || echo '(inode 变了)')"
echo "host: hash=$(host_hash)（= 新内容）"
echo "B1 运行中的容器（未重启）看到的：hash=$(ctr_hash)  ← in-place 写在挂载点上是否立即可见"
echo "B2 docker compose restart app（$(ts)）"
dc restart app >/dev/null 2>&1
sleep 12
echo "    restart 后容器内看到的：hash=$(ctr_hash)"
health_ok=1; wait_health 400 || health_ok=0
echo "B3 管理员连接测试（功能级，重启后）："
probe "$EVDIR/raw/03-B3-after-restart.json" | tee "$EVDIR/raw/03-B3-after-restart.txt"
B3_RAW="$(cat "$EVDIR/raw/03-B3-after-restart.txt")"
echo

echo "===== C. mv 换 inode（新文件顶掉旧 inode）+ 判决 ====="
i1=$(host_inode)
printf 'second-wrong-key-new-inode\n' > /tmp/third-wrong.key
sudo cp /tmp/third-wrong.key "$KEY.$$.tmp" && sudo chmod 600 "$KEY.$$.tmp" && sudo mv -f "$KEY.$$.tmp" "$KEY"; rm -f /tmp/third-wrong.key
i2=$(host_inode)
echo "host: inode $i1 -> $i2  $([[ "$i1" != "$i2" ]] && echo '(mv 换了 inode)' || echo '(inode 未变)')"
echo "C1 运行中的容器（未重启）看到的：hash=$(ctr_hash)  ← 挂载是否绑在旧 inode 上"
if echo "$B3_RAW" | grep -q '"ok": *true'; then
  echo "  判定：B3 = 服务**仍按旧 key 工作** ⇒ 只 restart 不够，走 --force-recreate"
  NEED_RECREATE=1
else
  echo "  判定：B3 = 服务**已按新 key 工作** ⇒ 文档说'只 restart 不够'与实测不符（见报告）"
  NEED_RECREATE=0
fi
echo "C2 docker compose up -d --force-recreate app（$(ts)）"
dc up -d --force-recreate app >/dev/null 2>&1
sleep 12
echo "    recreate 后容器内看到的：hash=$(ctr_hash)（host=${i2} 的 hash=$(host_hash)）"
wait_health 400 || true
echo "C3 管理员连接测试（功能级，recreate 后）："
probe "$EVDIR/raw/03-C3-after-recreate.json" | tee "$EVDIR/raw/03-C3-after-recreate.txt"
echo

echo "===== D. 换回真 key（文档命令）+ --force-recreate 复原 ====="
sudo install -m 600 "$REAL_KEY" "$KEY"
echo "host: inode=$(host_inode) hash=$(host_hash)（= 真 key 的内容哈希）"
dc up -d --force-recreate app >/dev/null 2>&1
sleep 12
echo "    recreate 后容器内看到的：hash=$(ctr_hash)"
dc inspect -f '' 2>/dev/null || true
wait_health 400 || true
echo "D1 管理员连接测试（复原后）："
probe "$EVDIR/raw/03-D1-restored.json" | tee "$EVDIR/raw/03-D1-restored.txt"
echo
echo "===== 汇总 ====="
for f in 03-A-baseline 03-B3-after-restart 03-C3-after-recreate 03-D1-restored; do
  printf '%-26s %s\n' "$f" "$(cat "$EVDIR/raw/$f.txt" 2>/dev/null | head -c 400)"
done
