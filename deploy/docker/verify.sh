#!/usr/bin/env bash
# 容器内验收探针（只读，不改服务状态）。用法：
#   docker compose exec -T app mirothinker-verify
# 覆盖：/api/health、/chat、/main、嵌入端点（HTTP 200 + 维度 4096）、容器内存占用。
# 退出码 0 = 全通；非 0 = 有红点（逐条打印）。

set -uo pipefail

PORT="${MIROTHINKER_PORT:-18188}"
BASE="http://127.0.0.1:${PORT}"
FAILED=0
EMBEDDING_BUNDLE="/home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/qwen-embedding-bundle-v1.json"
PY=/opt/mirothinker/.venv/bin/python

say() { printf '%s\n' "$*"; }
ok() { printf '  [OK]   %s\n' "$*"; }
bad() { printf '  [FAIL] %s\n' "$*"; FAILED=1; }

say "== HTTP 探针 ($BASE) =="
for path in /api/health /chat /main; do
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "${BASE}${path}" 2>/dev/null)"
  if [[ "$code" == "200" || "$code" == "302" ]]; then
    ok "${path} -> HTTP ${code}"
  else
    bad "${path} -> HTTP ${code:-<无响应>}（服务未监听或端口映射不对）"
  fi
done

say "== 嵌入端点探针（断言 HTTP 200 + 维度 4096）=="
if "$PY" - "$EMBEDDING_BUNDLE" <<'PY'
import json, sys, urllib.request
from pathlib import Path
sys.path.insert(0, "/opt/mirothinker/apps/miroflow-agent")
from src.data_agents.providers.local_api_key import load_local_api_key  # noqa: E402

bundle = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
base_url = bundle["base_url"].rstrip("/")
expected = int(bundle["dimension"])
key = load_local_api_key() or ""
if not key:
    print("  [FAIL] 未找到本地嵌入密钥（.sglang_api_key / SGLANG_API_KEY / API_KEY）")
    raise SystemExit(1)
req = urllib.request.Request(
    f"{base_url}/embeddings",
    data=json.dumps({"model": bundle["model_id"], "input": ["探针"]}).encode(),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        status = resp.status
        payload = json.loads(resp.read())
except Exception as exc:  # noqa: BLE001
    print(f"  [FAIL] 嵌入端点不可达：{type(exc).__name__}: {exc}")
    raise SystemExit(1) from exc
dims = len(payload["data"][0]["embedding"])
if status == 200 and dims == expected:
    print(f"  [OK]   {base_url} HTTP 200，维度 {dims}（model={bundle['model_id']}）")
else:
    print(f"  [FAIL] HTTP {status}，维度 {dims}（期望 {expected}）")
    raise SystemExit(1)
PY
then :; else FAILED=1; fi

say "== 内存 =="
"$PY" - <<'PY'
# 容器内所有进程 RSS 之和（与裸机上 `ps -o rss` 的那个数同口径）；
# 另打印 cgroup v2 当前用量（含页缓存，会比 RSS 大）。
import re
from pathlib import Path

total_kb = 0
for status in Path("/proc").glob("[0-9]*/status"):
    try:
        text = status.read_text(errors="ignore")
    except OSError:
        continue
    match = re.search(r"^VmRSS:\s+(\d+) kB", text, re.MULTILINE)
    if match:
        total_kb += int(match.group(1))
print(f"  RSS 合计: {total_kb / 1024 / 1024:.2f} GiB")
try:
    current = int(Path("/sys/fs/cgroup/memory.current").read_text().strip())
    print(f"  cgroup memory.current: {current / 1024 ** 3:.2f} GiB")
except OSError:
    pass
PY

if [[ "$FAILED" == "0" ]]; then
  say "== 结果：全通 =="
else
  say "== 结果：有红点（见上）=="
fi
exit "$FAILED"
