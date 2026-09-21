#!/usr/bin/env bash
# 命题（本轮）机制级验收：换成含"嵌入凭据投影"的 entrypoint 后，
# 只给文件、不设环境变量 ⇒ 容器里必须能看到候选槽位（只打印名字与是否为空）。
set -uo pipefail
B=/home/longxiang/delivery-xfer-v11/site-bundle
SITE_ROOT=/var/tmp/mirothinker-fourth-verify-20260922
STATE="$SITE_ROOT/var/tmp/mirothinker-canonical-v2-s12f"
PORT=18298
EVDIR=/home/longxiang/MiroThinker/.worktrees/delivery-docker/.agents/runs/docker-embedding-slot-symmetry-20260922
export MIROTHINKER_ADMIN_PASSWORD_FILE="$STATE/admin-password-rotated-20260922.txt"
dc() { sudo docker compose -f "$B/compose.yaml" "$@"; }
ts() { date '+%H:%M:%S'; }

echo "===== 0. 换 entrypoint 前的现场（$(ts)） ====="
echo "bundle entrypoint-v11.sh sha256: $(sha256sum "$B/entrypoint-v11.sh" | cut -c1-16)…（旧版备份 .pre-slot-projection）"
echo "运行中容器的配置环境（名字与是否为空；由 docker exec 视角）："
dc exec -T app sh -lc 'for n in SGLANG_API_KEY CANONICAL_V2_EMBEDDING_API_KEY; do eval "v=\${$n:-}"; [ -n "$v" ] && echo "  $n=已设置" || echo "  $n=空（容器配置未设，符合"只给文件"的现场）"; done'
echo

echo "===== 1. 重启 app 容器（bind 挂的入口覆盖件内容已换；restart 即重新挂载） ====="
dc restart app >/dev/null 2>&1
t0=$(date +%s)
while (( $(date +%s) - t0 < 500 )); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null)" == "200" ]] \
    && { echo "health OK after $(( $(date +%s) - t0 ))s"; break; }
  sleep 5
done
echo
echo "===== 2. 新 entrypoint 在真实容器里的启动日志（投影那一行） ====="
dc logs --tail 200 app 2>&1 | grep -E "嵌入凭据投影|凭据收据" | tail -5
echo
echo "===== 3. 机制级验收①：容器内跑 entrypoint 的凭据收据模式（名字与是否为空，无值） ====="
echo "\$ docker compose exec -T app env MIROTHINKER_ENTRYPOINT_ENV_RECEIPT=1 /usr/local/bin/mirothinker-entrypoint"
dc exec -T app env MIROTHINKER_ENTRYPOINT_ENV_RECEIPT=1 /usr/local/bin/mirothinker-entrypoint 2>&1 | sed -n '/凭据收据/,$p'
echo "收据 exit=${PIPESTATUS[0]}"
echo
echo "===== 4. 机制级验收②：**运行中的服务进程**自己的环境（只有名字与是否为空） ====="
dc exec -T app sh -lc '
  pid=""
  for candidate in $(ls /proc | grep -E "^[0-9]+$"); do
    cmd="$(tr "\0" " " < /proc/$candidate/cmdline 2>/dev/null)"
    case "$cmd" in *start-canonical-v2*|*serve_s12e_port*) pid="$candidate"; echo "  服务进程 pid=$pid cmd=$(echo "$cmd" | cut -c1-70)…"; break;; esac
  done
  [ -n "$pid" ] || { echo "  找不到服务进程"; exit 0; }
  for name in SGLANG_API_KEY API_KEY OPENAI_API_KEY CANONICAL_V2_EMBEDDING_API_KEY; do
    if tr "\0" "\n" < /proc/$pid/environ | grep -q "^$name=.\+"; then echo "  进程环境 $name=已设置"; else echo "  进程环境 $name=空"; fi
  done'
echo
echo "===== 5. 无回归：v1 槽位仍按文件工作（连接测试）+ 页面档位（llm）不受影响 ====="
python3 "$EVDIR/../docker-fourth-verification-20260922/key_probe.py" "$PORT" "$STATE" "$EVDIR/raw/05-embed-after-projection.json" 2>/dev/null \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);b=d["embedding_test"]["body"];print("  embedding:",json.dumps({"login":d["login"],"ok":b.get("ok"),"http":b.get("http_status"),"detail":b.get("detail"),"api_key_source":(b.get("used") or {}).get("api_key_source")},ensure_ascii=False))'
python3 "$EVDIR/../docker-fourth-verification-20260922/llm_probe.py" "$PORT" "$STATE" "$EVDIR/raw/05-llm-after-projection.json" 2>/dev/null \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);b=d["llm_test"]["body"];print("  llm     :",json.dumps({"login":d["login"],"ok":b.get("ok"),"http":b.get("http_status"),"api_key_source":(b.get("used") or {}).get("api_key_source")},ensure_ascii=False))'
