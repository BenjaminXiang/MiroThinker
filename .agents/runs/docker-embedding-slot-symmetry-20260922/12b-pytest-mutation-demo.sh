#!/usr/bin/env bash
# 生成 raw/12b-pytest-mutation.txt：新测试"有没有牙"的证明。
#
# 变异测试：把工具里两条关键规则各自拆掉，对应的测试**必须**变红；否则测试只是陪着跑。
#   变异 1 `_probe_image_paths` 假装"镜像里什么都有" ⇒ 路径存在性那 3 条测试该红
#   变异 2 `_read_container_bundle` 永远返回 None ⇒ 身份比对那 2 条测试该红
# 无论成败都用 trap 把工具还原（并核对 sha256）。
#
# 用法：bash 12b-pytest-mutation-demo.sh > raw/12b-pytest-mutation.txt 2>&1
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WT=/home/longxiang/MiroThinker/.worktrees/delivery-docker
TOOL=$WT/deploy/docker/serve-command-container.py
TESTS=tests/canonical_v2/test_serving_command_container.py
BAK=$(mktemp /tmp/serve-command-container.XXXXXX.py)
cp "$TOOL" "$BAK"
BEFORE=$(sha256sum "$TOOL" | cut -d' ' -f1)
restore() { [ -f "$BAK" ] && cp "$BAK" "$TOOL"; return 0; }
trap 'restore; rm -f "$BAK"' EXIT

run_tests() { (cd "$WT/apps/miroflow-agent" && timeout 280 uv run pytest "$TESTS" -q 2>&1 | tail -12); }

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
echo "  测试文件 = $TESTS"

echo
echo "══ 0. 基线：全部通过（否则下面的"变红"没意义）══"
run_tests

M1=$(mktemp /tmp/mut1.XXXXXX); M2=$(mktemp /tmp/mut2.XXXXXX)
printf 'def _probe_image_paths(image: str, paths: list[str], probe_root: Path | None) -> list[str]:\n==>\ndef _probe_image_paths(image: str, paths: list[str], probe_root: Path | None) -> list[str]:\n    return []  # MUTATION-1\n' > "$M1"
printf 'def _read_container_bundle(bundle: str, image: str, probe_root: Path | None) -> dict | None:\n==>\ndef _read_container_bundle(bundle: str, image: str, probe_root: Path | None) -> dict | None:\n    return None  # MUTATION-2\n' > "$M2"

echo
echo "══ 变异 1：路径存在性检查被拆掉（_probe_image_paths 永远说"都在"）⇒ 期望路径类测试变红 ══"
mutate "$M1"
run_tests
restore

echo
echo "══ 变异 2：身份比对被静默跳过（_read_container_bundle 永远返回 None）⇒ 期望身份类测试变红 ══"
mutate "$M2"
run_tests
restore
rm -f "$M1" "$M2"

echo
echo "== 还原核对 =="
AFTER=$(sha256sum "$TOOL" | cut -d' ' -f1)
echo "  还原后 sha256 = $AFTER"
if [ "$AFTER" = "$BEFORE" ]; then echo "  OK：与变异前一致"; else echo "  FAIL：还原后不一致！"; fi
