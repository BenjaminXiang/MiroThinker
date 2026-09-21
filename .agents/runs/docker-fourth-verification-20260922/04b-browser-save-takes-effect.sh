#!/usr/bin/env bash
# 命题 2 收尾：验证"页面保存的凭据在下次启动后真的生效"（不是只写了个文件）。
# 步骤：docker compose restart app → 等健康 → llm 连接测试 → 看运行期凭据来源是否变化。
set -uo pipefail
B=/home/longxiang/delivery-xfer-v11/site-bundle
STATE=/var/tmp/mirothinker-fourth-verify-20260922/var/tmp/mirothinker-canonical-v2-s12f
PORT=18298
EVDIR=/home/longxiang/MiroThinker/.worktrees/delivery-docker/.agents/runs/docker-fourth-verification-20260922
cd "$B" || exit 1

echo "== 重启前：受管文件里的状态（不回显内容） =="
sudo stat -c 'managed: %n owner=%U:%G mode=%a mtime=%y' state/config-managed/secrets.json
echo "== docker compose restart app =="
sudo docker compose -f "$B/compose.yaml" restart app >/dev/null 2>&1
t0=$(date +%s)
while (( $(date +%s) - t0 < 420 )); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null)" == "200" ]] \
    && { echo "health OK after $(( $(date +%s) - t0 ))s"; break; }
  sleep 5
done
echo "== 重启后：llm 连接测试（运行期凭据来源） =="
python3 "$EVDIR/llm_probe.py" "$PORT" "$STATE" "$EVDIR/raw/04-llm-probe-after-restart.json" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);b=d["llm_test"]["body"];print(json.dumps({"login":d["login"],"ok":b.get("ok"),"http":b.get("http_status"),"detail":b.get("detail"),"used":b.get("used"),"runtime_note":(b.get("runtime") or {}).get("runtime_note"),"api_key_origin":(b.get("runtime") or {}).get("api_key_origin"),"config_origin_fields":d.get("llm_origin_fields")},ensure_ascii=False))'
echo "== 嵌入连接测试（确认这一步没把别的弄坏） =="
python3 "$EVDIR/key_probe.py" "$PORT" "$STATE" "$EVDIR/raw/04-embed-after-restart.json" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print(json.dumps(d.get("summary",{}),ensure_ascii=False))'
