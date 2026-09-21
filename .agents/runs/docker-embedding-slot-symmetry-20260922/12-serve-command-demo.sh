#!/usr/bin/env bash
# 生成 raw/12-serve-command-container.txt —— 四段证据（只读；无外呼）：
#   ① v1.1 交付件的容器命令文件            → 期望 exit 0（绿）
#   ② 宿主裸机草案（母 agent 的 DRAFT）    → 期望 exit 1（判红：宿主构造 + 宿主路径）
#   ③ convert（真 v1.1 镜像）             → 期望 exit 1：把草案的 identity 搬进容器时，
#      容器里的账本仍是 v1 身份（Qwen/Qwen3-Embedding-8B·4096·openai-compatible），
#      与候选（qwen3.7-text-embedding-flash·1024·dashscope-native）不是同一向量空间
#      ⇒ 身份守护位必须红
#   ④ convert（构造的 "v2 出包后镜像形状" 树）→ 期望 exit 0（绿）
#
# 用法：bash 12-serve-command-demo.sh > raw/12-serve-command-container.txt 2>&1
set -uo pipefail   # 不用 -e：这里**故意**期待非零退出码

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WT=/home/longxiang/MiroThinker/.worktrees/delivery-docker
TOOL=$WT/deploy/docker/serve-command-container.py
IMAGE=mirothinker-serving:v1.1
V11=/home/longxiang/delivery-xfer-v11/site-bundle/serve-command-v11.sh
SWITCH=/home/longxiang/MiroThinker/.worktrees/embedding-switch-line
DR=/home/longxiang/MiroThinker/.worktrees/data-rebuild
C11=/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation   # 镜像里 → /opt/mirothinker
REL=.agents/runs/rebuild-canonical-v2-knowledge-platform
DRAFT=$SWITCH/$REL/s12g/serve-18188-command-fembed.DRAFT.sh
CAND_EMB=$SWITCH/.agents/runs/embedding-model-switch-v2/qwen3.7-text-embedding-flash-embedding-bundle-v1.json
DRAFT_EMB=$DR/.agents/runs/embedding-model-switch-v2/qwen3.7-text-embedding-flash-embedding-bundle-v1.json
# 演示用的两个 64-hex：借用 v1.1 交付件里已定死的值。真 cutover 时由 step 7 / step 10 填。
SHA7=b6f78a3b1e28c280860a4210bfad286ef65090e758de5b876d7f639eefaa8373
SHA10=0a09aecde903584efb28ccc4f3851062b52891081f0b3b44e6ce5971c55115c4

TMP=$(mktemp -d /tmp/serve-command-demo.XXXXXX)
trap 'rm -rf "$TMP"' EXIT

echo "== 0. 输入指纹（只读）=="
sha256sum "$TOOL" "$V11" "$DRAFT"
echo "-- 宿主候选嵌入 bundle（凭据外泄面：只打印身份字段）--"
python3 - "$CAND_EMB" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
print("   " + "  ".join(f"{k}={doc.get(k)!r}" for k in ("model_id", "dimension", "provider", "base_url")))
PY
echo "-- 草案引用的宿主路径是否存在 --"
for p in "$DRAFT_EMB" "$SWITCH/$REL/s12g/serving-bundle-fembed.json"; do
  if [ -e "$p" ]; then echo "   存在 $p"; else echo "   不存在 $p"; fi
done

run() {  # run <标题> <期望退出码> <命令...>
  local title=$1 expect=$2; shift 2
  echo
  echo "══ $title（期望 exit $expect）══"
  echo "\$ $*"
  "$@"; local rc=$?
  echo "exit=$rc"
  if [ "$rc" -ne "$expect" ]; then echo "!!! 与期望不符：期望 $expect，实得 $rc"; fi
}

run "① v1.1 交付件 serve-command-v11.sh：能不能当容器命令文件用" 0 \
  python3 "$TOOL" check --image "$IMAGE" --command "$V11"

run "② 宿主草案 serve-18188-command-fembed.DRAFT.sh：直接当容器命令文件用" 1 \
  python3 "$TOOL" check --image "$IMAGE" --command "$DRAFT"

run "③ convert（真 v1.1 镜像）：草案 → 容器命令文件，账本身份守护位" 1 \
  python3 "$TOOL" convert --host-command "$DRAFT" --image "$IMAGE" \
    --out "$TMP/serve-command-fembed.v1image.sh" \
    --map "$SWITCH/$REL/s12e/serve_s12e_port.py=$C11/$REL/s12e/serve_s12e_port.py" \
    --map "/home/longxiang/MiroThinker/.venv/bin/python=uv run python" \
    --map "$DRAFT_EMB=$DR/$REL/s12c/qwen-embedding-bundle-v1.json" \
    --map "$CAND_EMB=$DR/$REL/s12c/qwen-embedding-bundle-v1.json" \
    --map "$SWITCH/$REL/s12g/serving-bundle-fembed.json=$C11/$REL/s12g/serving-bundle-run16.json" \
    --map "__STEP7_INDEX_MARKER_SHA256__=$SHA7" \
    --map "__STEP10_SERVING_BUNDLE_SHA256__=$SHA10" \
    --host-embedding-bundle "$CAND_EMB"

# ④ 构造 "v2 出包后的镜像形状"：ledger 里放**候选** bundle，COPY 到命令文件引用的路径
ROOT=$TMP/root
EMB_V2=$DR/$REL/s12c/qwen3.7-text-embedding-flash-embedding-bundle-v1.json
SERVING_V2=$C11/$REL/s12g/serving-bundle-fembed.json
mkdir -p "$ROOT/var/tmp/mirothinker-data-v2" "$ROOT/var/tmp/mirothinker-canonical-v2-s12f" \
         "$ROOT$C11/$REL/s12e" "$ROOT$DR/$REL/s12a" "$ROOT$DR/$REL/s12c" "$ROOT$C11/$REL/s12g"
: > "$ROOT$C11/$REL/s12e/serve_s12e_port.py"
cp "$WT/deploy/docker/ledger/s12a/recorded-decision-bundle-v1.json" "$ROOT$DR/$REL/s12a/recorded-decision-bundle-v1.json"
cp "$CAND_EMB" "$ROOT$EMB_V2"                      # ← v2 出包要做的：候选 bundle 进 ledger
# step 10 会封存 fembed 的 serving bundle（真值由那一窗生成）；这里按同一 identity 造一份，
# 好让 "bundle 自述 ↔ 旗标" 那条运行期比对在这里就能走通。
python3 - "$ROOT$SERVING_V2" "$SHA10" <<'PY'
import json, sys

doc = {
    "content_sha256": sys.argv[2],
    "release_id": "candidate-v2-20260922-r1",
    "database_name": "miroflow_candidate_v2_20260922_r1",
    "database_target_kind": "disposable",
    "index_target_id": "index:candidate-v2-20260922-r1",
    "index_root": "/var/tmp/mirothinker-data-v2/index-v4-v2",
    "envelope_path": (
        "/home/longxiang/MiroThinker/.worktrees/data-rebuild"
        "/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope.json"
    ),
    "embedding_model_id": "qwen3.7-text-embedding-flash",
}
with open(sys.argv[1], "w", encoding="utf-8") as sink:
    sink.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
PY
echo
echo "══ ④ 的前置：构造的假镜像树（v2 出包后应当长这样）══"
echo "   候选 bundle 在容器里的位置：$EMB_V2"
find "$ROOT" -type f | sed "s|^$ROOT|   镜像内|" | sort

run "④ convert（构造树 --probe-root，代替 docker run）：同样映射 + 候选 bundle 进账本" 0 \
  python3 "$TOOL" convert --host-command "$DRAFT" --image "probe-root:$ROOT" \
    --out "$TMP/serve-command-fembed.v2shape.sh" --probe-root "$ROOT" \
    --map "$SWITCH/$REL/s12e/serve_s12e_port.py=$C11/$REL/s12e/serve_s12e_port.py" \
    --map "/home/longxiang/MiroThinker/.venv/bin/python=uv run python" \
    --map "$DRAFT_EMB=$EMB_V2" \
    --map "$CAND_EMB=$EMB_V2" \
    --map "$SWITCH/$REL/s12g/serving-bundle-fembed.json=$SERVING_V2" \
    --map "__STEP7_INDEX_MARKER_SHA256__=$SHA7" \
    --map "__STEP10_SERVING_BUNDLE_SHA256__=$SHA10" \
    --host-embedding-bundle "$CAND_EMB"

echo
echo "══ ⑤ ④ 写出的容器命令文件（那份要是绿的就长这样）══"
sed -e 's/ /\n    /g' "$TMP/serve-command-fembed.v2shape.sh"
echo
echo "══ ⑥ /tmp 里的中间产物（演示用，随 trap 删除；镜像里那份路径即上文 $EMB_V2）══"
ls -l "$TMP"/*.sh
