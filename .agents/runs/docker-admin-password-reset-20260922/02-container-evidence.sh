#!/usr/bin/env bash
# 生成 raw/02-container-evidence.txt —— 在**真镜像**（mirothinker-serving:v1.1）里验证口令重置：
#
#   ① 用镜像自己的 admin_auth 播种一个 scratch 状态目录（挂载在冻结的 /var/tmp/…-s12f 上）；
#   ② 容器里模拟"服务进程"：持有长连接 + 长生命周期 store 实例，再跑重置工具（子进程），
#      然后**用同一个实例**再读一次 ⇒ 证明外部写入对持有连接的进程立即可见、不需要重启；
#   ③ 产物的权限/属主（0600、数据属主 uid）；
#   ④ 判红：只挂工具、不挂状态目录 ⇒ 必须 exit 3 且**不在容器层新建**空库；
#   ⑤ `--status` 只读。
#
# 口令全程不打印：脚本只比对布尔值，scratch 口令写在临时目录里（随 $TMP 一起删）。
# 用法：bash 02-container-evidence.sh > raw/02-container-evidence.txt 2>&1
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WT=/home/longxiang/MiroThinker/.worktrees/delivery-docker
TOOL=$WT/deploy/docker/reset_admin_password.py
IMAGE=mirothinker-serving:v1.1
STATE_IN_CONTAINER=/var/tmp/mirothinker-canonical-v2-s12f
# 容器以"数据属主"运行（compose 的 user: 来自安装器写入 .env 的 MIROTHINKER_UID，
# 实测现场是 1004）—— 这里就用 scratch 状态目录的属主，和真实运行一致。
UID_GID="$(id -u):$(id -g)"

TMP=$(mktemp -d /tmp/reset-password-evidence.XXXXXX)
trap 'rm -rf "$TMP"' EXIT
STATE=$TMP/state
mkdir -p "$STATE"
cp "$TOOL" "$TMP/reset-admin-password.py"

cat > "$TMP/driver.py" <<'PY'
"""容器内的两段驱动：seed（播种）与 hold（模拟服务进程 + 跑重置）。"""

import subprocess
import sys
from pathlib import Path

from backend.services import admin_auth

STATE = Path("/var/tmp/mirothinker-canonical-v2-s12f")
DB = STATE / "admin-auth.sqlite3"
SCRATCH = STATE / "scratch-old-password.txt"   # 临时：只为跨容器进程对比，随证据脚本一起删


def seed() -> int:
    old = admin_auth.generate_password()
    store = admin_auth.AdminAuthStore(DB)
    store.seed_initial_admin(password=old, username="admin", announce=lambda _: None)
    store.close()
    SCRATCH.write_text(old, encoding="utf-8")
    print(f"  seeded: db={DB.is_file()} initial-file={(STATE / admin_auth.PASSWORD_FILENAME).is_file()}")
    return 0


def hold_then_reset() -> int:
    old = SCRATCH.read_text(encoding="utf-8").strip()
    store = admin_auth.AdminAuthStore(DB)          # ← "服务进程"的连接，全程不关
    print(f"  service-before: old_works={store.verify_credentials('admin', old)}")
    result = subprocess.run(
        [sys.executable, "/tmp/reset-admin-password.py"], capture_output=True, text=True
    )
    print(f"  reset-exit={result.returncode}")
    print("---- 工具输出（原文；口令不在其中）----")
    print(result.stdout.rstrip())
    print("----")
    wanted = sorted(STATE.glob("admin-password-reset-*.txt"))
    assert wanted, "没有写出重置文件"
    newest = wanted[-1]
    new = newest.read_text(encoding="utf-8").strip()
    print(f"  service-after（同一个连接、不重启）: old_works={store.verify_credentials('admin', old)}")
    print(f"  service-after（同一个连接、不重启）: new_works={store.verify_credentials('admin', new)}")
    print(f"  reset-file={newest.name} mode={oct(newest.stat().st_mode & 0o777)} uid={newest.stat().st_uid}")
    print(f"  audit(admin.password_reset)={[r.result for r in store.audit_records(action='admin.password_reset')]}")
    print(f"  epoch={store.account('admin').password_epoch}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit({"seed": seed, "hold": hold_then_reset}[sys.argv[1]]())
PY

run_in_image() {  # run_in_image <额外 -v/--user 参数…> -- <容器内命令…>
  docker run --rm --user "$UID_GID" "$@"
}

echo "== 0. 输入 =="
echo "  镜像：$IMAGE（$(docker image inspect --format "{{.Id}}" "$IMAGE" | cut -c8-19)）"
echo "  容器运行身份：$UID_GID（= 数据属主，与 compose 的 user: 一致）"
echo "  工具：$TOOL（sha256 $(sha256sum "$TOOL" | cut -c1-16)…）"
echo "  scratch 状态目录：$STATE（挂到冻结路径 $STATE_IN_CONTAINER）"
echo

echo "══ ① 播种（镜像自己的 admin_auth 建的库与首启口令文件；口令不打印）══"
run_in_image \
  -v "$STATE:$STATE_IN_CONTAINER" \
  -v "$TMP/driver.py:/tmp/driver.py:ro" \
  --entrypoint /opt/mirothinker/.venv/bin/python "$IMAGE" /tmp/driver.py seed
echo

echo "══ ② 容器内：服务进程持有连接 → 跑重置 → 同一实例立刻看到新口令（旧口令立刻失效）══"
run_in_image \
  -v "$STATE:$STATE_IN_CONTAINER" \
  -v "$TMP/driver.py:/tmp/driver.py:ro" \
  -v "$TMP/reset-admin-password.py:/tmp/reset-admin-password.py:ro" \
  --entrypoint /opt/mirothinker/.venv/bin/python "$IMAGE" /tmp/driver.py hold
echo

echo "══ ③ 宿主侧看产物（容器运行身份 $UID_GID = 数据属主，与 compose 的 user: 一致）══"
ls -l "$STATE" | sed 's/^/  /'
echo "  重置文件内容长度（只打印长度，不打印口令）：$(stat -c %s "$STATE"/admin-password-reset-*.txt) 字节"
echo

echo "══ ④ 判红：只挂工具、不挂状态目录 ⇒ 期望 exit 3 且不在容器层新建空库 ══"
echo "\$ docker run --rm --user $UID_GID -v <工具>:/tmp/reset-admin-password.py:ro \\"
echo '    --entrypoint /opt/mirothinker/.venv/bin/python mirothinker-serving:v1.1 /tmp/reset-admin-password.py'
run_in_image \
  -v "$TMP/reset-admin-password.py:/tmp/reset-admin-password.py:ro" \
  --entrypoint /opt/mirothinker/.venv/bin/python "$IMAGE" /tmp/reset-admin-password.py
echo "  exit=$?"
echo "  容器层里有没有被建出空库（应当 no such file）:"
docker run --rm --user "$UID_GID" --entrypoint /bin/sh "$IMAGE" \
  -c "ls -l $STATE_IN_CONTAINER/admin-auth.sqlite3 2>&1 || true; ls -la $STATE_IN_CONTAINER | head -3"
echo

echo "══ ⑤ 逃生门（README §5.1 里写给运维的那条）：容器起不来时用一次性 compose 容器跑同一条工具 ══"
cat > "$TMP/scratch-compose.yaml" <<'YAML'
services:
  app:
    image: mirothinker-serving:v1.1
    user: "REPLACE_UID_GID"
    volumes:
      - REPLACE_STATE:/var/tmp/mirothinker-canonical-v2-s12f
      - REPLACE_TOOL:/usr/local/bin/mirothinker-reset-admin-password:ro
YAML
sed -i -e "s#REPLACE_UID_GID#$UID_GID#" -e "s#REPLACE_STATE#$STATE#" -e "s#REPLACE_TOOL#$TOOL#" \
  "$TMP/scratch-compose.yaml"
echo '$ docker compose -f <交付包目录>/compose.yaml run --rm --no-deps \'
echo '    --entrypoint /opt/mirothinker/.venv/bin/python app /usr/local/bin/mirothinker-reset-admin-password --status'
docker compose -f "$TMP/scratch-compose.yaml" -p mirothinker-reset-evidence \
  run --rm --no-deps --entrypoint /opt/mirothinker/.venv/bin/python \
  app /usr/local/bin/mirothinker-reset-admin-password --status
echo "  exit=$?"
docker network rm mirothinker-reset-evidence_default >/dev/null 2>&1 || true
echo

echo "══ ⑥ 容器内 --status（只读；只列文件名，不打印内容）══"
run_in_image \
  -v "$STATE:$STATE_IN_CONTAINER" \
  -v "$TMP/reset-admin-password.py:/tmp/reset-admin-password.py:ro" \
  --entrypoint /opt/mirothinker/.venv/bin/python "$IMAGE" \
  /tmp/reset-admin-password.py --status
echo "  exit=$?"
