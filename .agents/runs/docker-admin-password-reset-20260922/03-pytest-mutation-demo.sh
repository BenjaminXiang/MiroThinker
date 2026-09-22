#!/usr/bin/env bash
# 生成 raw/03-pytest-mutation.txt：口令重置这条链的测试"有没有牙"。
#
# 三处变异，每次都必须让**对应**的测试变红（否则测试只是陪着跑）：
#   变异 1 把新口令打进输出        ⇒ test_the_tool_never_prints_the_password 该红
#   变异 2 忽略环境给的库路径      ⇒ test_the_targets_the_database… 等该红
#   变异 3 去掉"库不存在就拒绝"    ⇒ test_refuses_a_missing_database… 该红
# 无论成败都用 trap 把工具还原（并核对 sha256）。
#
# 用法：bash 03-pytest-mutation-demo.sh > raw/03-pytest-mutation.txt 2>&1
set -uo pipefail

WT=/home/longxiang/MiroThinker/.worktrees/delivery-docker
TOOL=$WT/deploy/docker/reset_admin_password.py
TESTS=tests/test_reset_admin_password_cli.py
BAK=$(mktemp /tmp/reset-admin-password.XXXXXX.py)
cp "$TOOL" "$BAK"
BEFORE=$(sha256sum "$TOOL" | cut -d' ' -f1)
restore() { [ -f "$BAK" ] && cp "$BAK" "$TOOL"; return 0; }
trap 'restore; rm -f "$BAK"' EXIT

run_tests() { (cd "$WT/apps/admin-console" && timeout 280 uv run pytest "$TESTS" -q -p no:cacheprovider 2>&1 | tail -12); }

mutate() {  # mutate <配方文件>
  python3 - "$TOOL" "$1" <<'PY'
import sys
from pathlib import Path

target, recipe = Path(sys.argv[1]), Path(sys.argv[2])
text = target.read_text(encoding="utf-8")
old, new = recipe.read_text(encoding="utf-8").split("\n==>\n")
assert old in text, f"变异锚点没找到：{old!r}"
target.write_text(text.replace(old, new, 1), encoding="utf-8")
PY
}

echo "== 工具指纹 =="
echo "  变异前 sha256 = $BEFORE"
echo "  测试文件 = apps/admin-console/$TESTS"

echo
echo "══ 0. 基线：全部通过（否则下面的“变红”没意义）══"
run_tests

M1=$(mktemp /tmp/mut1.XXXXXX); M2=$(mktemp /tmp/mut2.XXXXXX); M3=$(mktemp /tmp/mut3.XXXXXX); M4=$(mktemp /tmp/mut4.XXXXXX)
printf '    print("== 管理员口令已重置 ==")\n==>\n    print("== 管理员口令已重置 ==")\n    print(f"  口令：{password}")  # MUTATION-1\n' > "$M1"
printf '    db_path = Path(args.db) if args.db else admin_auth.default_db_path()\n==>\n    db_path = Path(args.db) if args.db else admin_auth.DEFAULT_STATE_DIR / admin_auth.DB_FILENAME  # MUTATION-2\n' > "$M2"
printf '    if not db_path.is_file():\n        print(f"[FAIL] 口令库不存在：{db_path}")\n==>\n    if False:  # MUTATION-3\n        print(f"[FAIL] 口令库不存在：{db_path}")\n' > "$M3"
printf '        store.set_password(username, password)\n==>\n        # MUTATION-4：手写 SQL（跳过模块的 epoch 递增与审计）\n        _hash, _salt = admin_auth.hash_password(password)\n        with store._lock, store._connection:  # noqa: SLF001\n            store._connection.execute(\n                "UPDATE accounts SET password_hash = ?, password_salt = ? WHERE username = ?",\n                (_hash, _salt, username),\n            )\n' > "$M4"

echo
echo "══ 变异 1：把新口令打进输出 ⇒ 期望"不打印口令"那条红 ══"
mutate "$M1"
run_tests
restore

echo
echo "══ 变异 2：忽略 CANONICAL_V2_ACCESS_LOG_DB 给的库路径（改用写死状态目录）⇒ 期望目标库类测试红 ══"
mutate "$M2"
run_tests
restore

echo
echo "══ 变异 3：去掉"库不存在就拒绝"（会新建空副本）⇒ 期望那条红 ══"
mutate "$M3"
run_tests
restore

echo
echo "══ 变异 4：手写 SQL 而不是走 set_password（跳过 epoch 递增与不变量）⇒ 期望会话/代次类测试红 ══"
mutate "$M4"
run_tests
restore
rm -f "$M1" "$M2" "$M3" "$M4"

echo
echo "== 还原核对 =="
AFTER=$(sha256sum "$TOOL" | cut -d' ' -f1)
echo "  还原后 sha256 = $AFTER"
if [ "$AFTER" = "$BEFORE" ]; then echo "  OK：与变异前一致"; else echo "  FAIL：还原后不一致！"; fi
