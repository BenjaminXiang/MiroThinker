#!/usr/bin/env bash
# Task B 归因用的微基准：把"读代码/读 venv/读数据"三件事分别在两种环境里计时。
#
#   microbench.sh bare        在宿主机（本 worktree 的 .venv，ext4）跑
#   microbench.sh container   在容器里（镜像层里的 .venv，overlayfs）跑
#
# 测四件事：
#   1) 解释器冷启动 + 空导入
#   2) 导入服务栈的核心模块（backend.main：会拉起 fastapi/pydantic/psycopg 等一大票依赖）
#   3) 扫一遍 venv 里的 .py/.pyc（模拟导入期的文件系统开销）
#   4) 顺序读 3.47 GB 的 relationships.json（数据面读路径；宿主机与容器都读同一份 inode）

set -uo pipefail
PHASE="${1:-bare}"
WORKTREE="/home/longxiang/MiroThinker/.worktrees/delivery-docker"
DATA="/var/tmp/mirothinker-data-v2"

PY_SCRIPT=$(cat <<'PY'
import os, sys, time, pathlib, io

def timed(label, fn):
    started = time.monotonic()
    result = fn()
    print(f"  {label:46s} {time.monotonic() - started:8.3f}s  {result}")
    return result

timed("python 冷启动（空导入）", lambda: sys.version.split()[0])

def import_core():
    sys.path.insert(0, "/opt/mirothinker/apps/admin-console") if os.path.isdir("/opt/mirothinker") else None
    import backend.main  # noqa: F401
    return "backend.main ok"

timed("导入 backend.main", import_core)

def scan_venv():
    root = pathlib.Path(sys.prefix)
    count = 0
    bytes_read = 0
    for path in root.rglob("*.pyc"):
        count += 1
        try:
            bytes_read += path.stat().st_size
        except OSError:
            pass
    return f"{count} pyc, {bytes_read/1e6:.1f} MB"

timed("遍历 venv 里的 .pyc", scan_venv)
PY
)

case "$PHASE" in
  bare)
    echo "== bare metal（$WORKTREE/.venv，ext4）=="
    cd "$WORKTREE" || exit 1
    # 把上面脚本里写死的容器路径换成本 worktree
    echo "$PY_SCRIPT" | sed "s#/opt/mirothinker#$WORKTREE#g" | \
      "$WORKTREE/.venv/bin/python" -
    echo "-- 顺序读 3.47 GB relationships.json --"
    /usr/bin/time -f "  read relationships.json  %e s (maxRSS %M KB)" \
      cat "$DATA/serving-pack-run16-readerbound/relationships.json" > /dev/null
    echo "-- 读 venv 全部文件（冷热不论，量级参考）--"
    /usr/bin/time -f "  read venv tree           %e s" \
      sh -c "find '$WORKTREE/.venv' -type f -exec cat {} + > /dev/null 2>&1"
    ;;

  container)
    echo "== container（镜像内 /opt/mirothinker/.venv，overlayfs）=="
    docker rm -f mirothinker-microbench >/dev/null 2>&1
    docker run --rm --name mirothinker-microbench --user 1004:1004 \
      -v "${DATA}:/var/tmp/mirothinker-data-v2:ro" \
      --entrypoint /bin/bash mirothinker-serving:v1 -lc "
        echo '$PY_SCRIPT' | /opt/mirothinker/.venv/bin/python -
        echo '-- 顺序读 3.47 GB relationships.json --'
        /usr/bin/time -f '  read relationships.json  %e s (maxRSS %M KB)' \
          cat /var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound/relationships.json > /dev/null
        echo '-- 读 venv 全部文件 --'
        /usr/bin/time -f '  read venv tree           %e s' \
          sh -c 'find /opt/mirothinker/.venv -type f -exec cat {} + > /dev/null 2>&1'
      "
    ;;

  *) echo "usage: $0 {bare|container}" >&2; exit 2 ;;
esac
