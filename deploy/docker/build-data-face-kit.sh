#!/usr/bin/env bash
# 生成一份「数据面 + 校验清单」交付件（v1 / v1.1 通用）。
#
#   deploy/docker/build-data-face-kit.sh [--data-root DIR] [--pack NAME] [--index NAME]
#                                        [--version TAG] [--out-dir DIR] [--no-tar]
#
# 产出（默认 out-dir = /var/tmp/mirothinker-data-face-xfer）：
#   serving-data-<version>.tar.gz        两个冻结目录（服务包 + 索引根；**不含** mount-receipt）
#   serving-data-<version>.tar.gz.sha256
#   source-listing.txt                   解包后的目录形态（给人看）
#   以及一份 BM-kit 形态的校验清单目录（默认 /var/tmp/mirothinker-delivery-kit-<version>/）：
#     checksums.sha256  8 个数据文件（绝对路径，与 v1 同格式）+ 2 个发布 bundle（相对路径）
#     sizes.tsv         路径<TAB>字节数（供安装器 --fast）
#     bundles/          两个发布 bundle（从 v1 的 BM kit 复制；v1.1 未重封）
#
# 说明：checksums 里的绝对路径是**容器内/现场落位后的冻结路径**，安装器在
# MIROTHINKER_SITE_ROOT 模式下会把前缀改写成 scratch 根。

set -euo pipefail

DATA_ROOT="/var/tmp/mirothinker-data-v2"
PACK_NAME="serving-pack-run16-v11"
INDEX_NAME="index-v3-v2"
VERSION="v1.1"
OUT_DIR="/var/tmp/mirothinker-data-face-xfer"
BM_KIT="${MIROTHINKER_BM_KIT_DIR:-/var/tmp/mirothinker-delivery-kit}"
BUILD_TAR=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-root) DATA_ROOT="$2"; shift 2 ;;
    --pack) PACK_NAME="$2"; shift 2 ;;
    --index) INDEX_NAME="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --no-tar) BUILD_TAR=0; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

BM_OUT="${MIROTHINKER_BM_OUT:-/var/tmp/mirothinker-delivery-kit-${VERSION}}"
TARBALL="${OUT_DIR}/serving-data-${VERSION}.tar.gz"
log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

for d in "$DATA_ROOT/$PACK_NAME" "$DATA_ROOT/$INDEX_NAME"; do
  [[ -d "$d" ]] || { echo "缺少目录：$d" >&2; exit 1; }
done
command -v pigz >/dev/null && COMPRESS=(--use-compress-program=pigz) || COMPRESS=()

if [[ "$BUILD_TAR" == "1" ]]; then
  mkdir -p "$OUT_DIR"
  log "打包 $PACK_NAME + $INDEX_NAME → $(basename "$TARBALL")（不含 mount-receipt；pigz ${COMPRESS:+on}）"
  started=$(date +%s)
  tar "${COMPRESS[@]}" -cf "$TARBALL" -C "$DATA_ROOT" "$PACK_NAME" "$INDEX_NAME"
  log "打包完成：$(( $(date +%s) - started ))s，$(stat -c %s "$TARBALL") bytes"
  ( cd "$OUT_DIR" && sha256sum "$(basename "$TARBALL")" > "$(basename "$TARBALL").sha256" )
  log "sha256: $(cut -c1-32 "$TARBALL.sha256")…"
  { echo "$INDEX_NAME/:"; ls -la "$DATA_ROOT/$INDEX_NAME" | tail -n +2
    echo; echo "$PACK_NAME/:"; ls -la "$DATA_ROOT/$PACK_NAME" | tail -n +2; } > "$OUT_DIR/source-listing.txt"
fi

log "生成校验清单 → $BM_OUT"
mkdir -p "$BM_OUT/bundles"
: > "$BM_OUT/checksums.sha256"
: > "$BM_OUT/sizes.tsv"
for name in "$INDEX_NAME" "$PACK_NAME"; do
  for f in "$DATA_ROOT/$name"/* "$DATA_ROOT/$name"/.[!.]*; do
    [[ -f "$f" ]] || continue
    [[ "$(basename "$f")" == *.mount-receipt.json ]] && continue
    sha256sum "$f" >> "$BM_OUT/checksums.sha256"
    printf '%s\t%s\n' "$f" "$(stat -c %s "$f")" >> "$BM_OUT/sizes.tsv"
  done
done
for bundle in serving-bundle-run16.json qwen-embedding-bundle-v1.json; do
  if [[ -f "${BM_KIT}/bundles/${bundle}" ]]; then
    cp -f "${BM_KIT}/bundles/${bundle}" "$BM_OUT/bundles/${bundle}"
    ( cd "$BM_OUT" && sha256sum "bundles/${bundle}" >> checksums.sha256 )
  else
    echo "  [warn] 缺发布 bundle：${BM_KIT}/bundles/${bundle}" >&2
  fi
done
log "清单：$BM_OUT/checksums.sha256（$(grep -c '' "$BM_OUT/checksums.sha256") 条）、sizes.tsv（$(grep -c '' "$BM_OUT/sizes.tsv") 条）"
grep -E "serving-pack|index" "$BM_OUT/checksums.sha256" | awk '{print "  " substr($1,1,12) "…  " $2}'
