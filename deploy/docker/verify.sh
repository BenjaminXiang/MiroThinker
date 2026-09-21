#!/usr/bin/env bash
# 容器内验收探针（只读，不改服务状态）。用法：
#   docker compose exec -T app mirothinker-verify
# 覆盖：/api/health、/chat、/main、嵌入端点（身份取自**站点在用的记录 bundle**：HTTP 200 +
# 维度与之一致；形状按"先兼容、只有 404/405 才换原生"的规则问地址）、容器内存占用。
# 退出码 0 = 全通；非 0 = 有红点（逐条打印）。

set -uo pipefail

PORT="${MIROTHINKER_PORT:-18188}"
BASE="http://127.0.0.1:${PORT}"
FAILED=0
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

say "== 嵌入端点探针（断言站点真正在用的身份）=="
# 期望身份不写死：取自**运行中的服务** argv 里的 --recorded-embedding-bundle（运行期就是按它
# 加载并逐字段比对的），退一步取冻结命令文件里的同一参数；地址取服务进程环境里的
# CANONICAL_V2_EMBEDDING_BASE_URL（受管/页面覆盖）否则 bundle 记录的地址；形状按"先兼容、
# 只有 404/405 才换 DashScope 原生"的规则问地址（与页面身份校验同一条规则）。
if "$PY" /usr/local/bin/mirothinker-verify-embedding; then :; else FAILED=1; fi

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
