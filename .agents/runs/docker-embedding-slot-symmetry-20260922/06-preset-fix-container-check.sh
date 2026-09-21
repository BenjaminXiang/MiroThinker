#!/usr/bin/env bash
# R1 的容器内验证：把交付预置换成"不含 v1 地址/模型"的版本 ⇒ 生效端点必须回到
# **发布包记录的地址**（来源不再是受管覆盖）。只打印来源与是否可用，不打印值以外的敏感信息
# （地址不是密钥，可以打印）。
set -uo pipefail
B=/home/longxiang/delivery-xfer-v11/site-bundle
REPO=/home/longxiang/MiroThinker/.worktrees/delivery-docker
SITE_ROOT=/var/tmp/mirothinker-fourth-verify-20260922
STATE="$SITE_ROOT/var/tmp/mirothinker-canonical-v2-s12f"
PORT=18298
EVDIR=/home/longxiang/MiroThinker/.worktrees/delivery-docker/.agents/runs/docker-embedding-slot-symmetry-20260922
export MIROTHINKER_ADMIN_PASSWORD_FILE="$STATE/admin-password-rotated-20260922.txt"
dc() { sudo docker compose -f "$B/compose.yaml" "$@"; }
probe() { python3 "$REPO/.agents/runs/docker-fourth-verification-20260922/key_probe.py" "$PORT" "$STATE" "$1" 2>/dev/null | python3 -c '
import json,sys
d=json.load(sys.stdin); b=d["embedding_test"]["body"]
if not isinstance(b, dict): print(json.dumps({"status": d["embedding_test"]["status"], "raw": b}, ensure_ascii=False)); raise SystemExit
rt = b.get("runtime") or {}
print(json.dumps({"login": d["login"], "ok": b.get("ok"), "http": b.get("http_status"), "detail": b.get("detail"),
                  "base_url": rt.get("base_url"), "model": rt.get("model"),
                  "endpoint_origin": rt.get("endpoint_origin"), "api_key_origin": rt.get("api_key_origin"),
                  "runtime_note": rt.get("runtime_note")}, ensure_ascii=False))'; }

echo "===== 0. 换预置之前的基线（运行中的进程仍在用启动时投影的值） $(date '+%H:%M:%S') ====="
echo "宿主受管文件：$(stat -c '%n %U:%G %a' "$B/state/config-managed/settings.json")"
python3 -c "
import json; d=json.load(open('$B/state/config-managed/settings.json'))
print('  extraction_endpoints（旧预置）:', json.dumps(d['extraction_endpoints'], ensure_ascii=False))"
probe "$EVDIR/raw/06-baseline-before-preset-fix.json" | sed 's/^/  /'

echo
echo "===== 1. 落位修好的交付预置（= build-site-bundle.sh 会打进包的那份）$(date '+%H:%M:%S') ====="
cp -a "$B/state/config-managed/settings.json" "$B/state/config-managed/settings.json.pre-r1-fix"
cp -a "$REPO/deploy/docker/site-config/managed-settings.json" "$B/state/config-managed/settings.json"
python3 -c "
import json; d=json.load(open('$B/state/config-managed/settings.json'))
print('  extraction_endpoints（新预置）:', json.dumps(d['extraction_endpoints'], ensure_ascii=False))
print('  含 embedding 字段吗：', [k for k in d['extraction_endpoints'] if k.startswith('embedding')] or '否')"
diff <(git -C "$REPO" show HEAD:deploy/docker/site-config/managed-settings.json) "$B/state/config-managed/settings.json" >/dev/null \
  && echo "  ⚠ 与仓库源一致（预期：仓库源刚从 HEAD 改过，应显示差异）" \
  || echo "  与仓库源 diff（应为本轮改动）:"; diff "$REPO/deploy/docker/site-config/managed-settings.json" "$B/state/config-managed/settings.json" && echo "  与仓库当前源逐字一致 ✓"

echo
echo "===== 2. 重启服务让新预置生效（R16：启动时投影）$(date '+%H:%M:%S') ====="
dc restart app >/dev/null 2>&1
t0=$(date +%s)
while (( $(date +%s) - t0 < 500 )); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null)" == "200" ]] \
    && { echo "health OK after $(( $(date +%s) - t0 ))s"; break; }
  sleep 5
done

echo
echo "===== 3. 生效端点（改后）$(date '+%H:%M:%S') ====="
probe "$EVDIR/raw/06-after-preset-fix.json" | sed 's/^/  /'
echo
echo "===== 4. 服务进程环境里还有没有那个覆盖（只有名字与是否为空） ====="
dc exec -T app sh -lc '
  pid=""; for c in $(ls /proc | grep -E "^[0-9]+$"); do
    tr "\0" " " < /proc/$c/cmdline 2>/dev/null | grep -q serve_s12e_port && pid="$c" && break; done
  for name in CANONICAL_V2_EMBEDDING_BASE_URL CANONICAL_V2_EMBEDDING_MODEL CHAT_LLM_PROFILE LOCAL_LLM_BASE_URL; do
    if tr "\0" "\n" < /proc/$pid/environ | grep -q "^$name=.\+"; then echo "  $name=已设置"; else echo "  $name=空"; fi
  done'
