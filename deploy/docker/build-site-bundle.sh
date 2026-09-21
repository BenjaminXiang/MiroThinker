#!/usr/bin/env bash
# 组装「现场交付包」——运营者从我们这儿下载、带到甲方机器、跑一条命令要用的全部东西。
#
#   deploy/docker/build-site-bundle.sh [--with-local-keys] [--out DIR]
#
# 输出目录（默认 /var/tmp/mirothinker-site-bundle/）：
#   install-site.sh                       一键安装脚本（Deliverable 2）
#   README-FIRST.txt                      给运营者的三句话（生成）
#   BUNDLE-MANIFEST.txt                   逐文件 尺寸+sha256（生成）
#   mirothinker-serving-v1.tar.gz         +.sha256   容器镜像（1.56 GiB）
#   serving-data-v1.tar.gz                +.sha256   数据面（1.48 GiB，两个冻结目录）
#   compose.yaml / README.md / kit-manifest.txt       编排与 runbook
#   checksums.sha256 / sizes.tsv / site-paths.txt     10 个交付物的校验清单（来自裸机 kit）
#   bundles/{serving-bundle-run16.json,qwen-embedding-bundle-v1.json}
#   secrets.example/                      凭据模板（真值由运营者放 secrets/）
#
# **大文件一律用硬链接**（同一文件系统），所以重跑不会复制 3 GB；跨文件系统时
# 自动退化为复制并**大声警告**（那样会多占 ≈3 GB，且不再是"同一个 inode"）。
#
# 幂等：重复运行只会重新挂钩 + 重生成两个 manifest。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="${MIROTHINKER_KIT_DIR:-/var/tmp/mirothinker-docker-kit}"
DATA_XFER_DIR="${MIROTHINKER_DATA_XFER_DIR:-/var/tmp/mirothinker-data-face-xfer}"
BM_KIT_DIR="${MIROTHINKER_BM_KIT_DIR:-/var/tmp/mirothinker-delivery-kit}"
OUT_DIR="${MIROTHINKER_SITE_BUNDLE_DIR:-/var/tmp/mirothinker-site-bundle}"
WITH_LOCAL_KEYS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-local-keys) WITH_LOCAL_KEYS=1; shift ;;
    --out) OUT_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

IMAGE_TGZ="mirothinker-serving-v1.tar.gz"
DATA_TGZ="serving-data-v1.tar.gz"
LINKED=0
COPIED=0
WARNINGS=()

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

# 硬链接（同 fs）；跨 fs 退化复制并警告。
place() {
  local src="$1" dst="$2" label="${3:-$(basename "$1")}"
  if [[ ! -e "$src" ]]; then
    WARNINGS+=("缺源文件：$src（$label）")
    printf '  [warn] 缺源文件 %s\n' "$src"
    return 1
  fi
  mkdir -p "$(dirname "$dst")"
  local src_dev dst_dev
  src_dev="$(stat -c %d "$src")"
  dst_dev="$(stat -c %d "$(dirname "$dst")")"
  if [[ "$src_dev" == "$dst_dev" ]]; then
    ln -f "$src" "$dst" 2>/dev/null || cp -a "$src" "$dst"
    if [[ "$(stat -c %i "$src")" == "$(stat -c %i "$dst")" ]]; then
      LINKED=$((LINKED + 1))
      printf '  [ok]   硬链接 %-46s %12s B  %s\n' "$label" "$(stat -c %s "$src")" "$(stat -c %i "$src")"
    else
      COPIED=$((COPIED + 1))
      printf '  [warn] 链接失败退化为复制 %s\n' "$label"
    fi
  else
    cp -a "$src" "$dst"
    COPIED=$((COPIED + 1))
    WARNINGS+=("跨文件系统复制（多占空间）：$label")
    printf '  [warn] 跨 fs ⇒ 复制 %-34s %12s B\n' "$label" "$(stat -c %s "$src")"
  fi
  return 0
}

echo "== 组装现场交付包 =="
echo "  输出:      $OUT_DIR"
echo "  镜像 kit:  $KIT_DIR"
echo "  数据面:    $DATA_XFER_DIR"
echo "  裸机 kit:  $BM_KIT_DIR"
echo

mkdir -p "$OUT_DIR"

echo "-- 安装器与文档 --"
place "${DEPLOY_DIR}/install-site.sh" "${OUT_DIR}/install-site.sh" "install-site.sh"
chmod 0755 "${OUT_DIR}/install-site.sh" 2>/dev/null || true
place "${KIT_DIR}/compose.yaml" "${OUT_DIR}/compose.yaml" "compose.yaml"
place "${KIT_DIR}/README.md" "${OUT_DIR}/README.md" "README.md（runbook）"
place "${KIT_DIR}/kit-manifest.txt" "${OUT_DIR}/kit-manifest.txt" "kit-manifest.txt"

echo "-- 校验清单（裸机 kit 的 10 个交付物）--"
place "${BM_KIT_DIR}/checksums.sha256" "${OUT_DIR}/checksums.sha256" "checksums.sha256"
for extra in sizes.tsv site-paths.txt; do
  [[ -e "${BM_KIT_DIR}/${extra}" ]] && place "${BM_KIT_DIR}/${extra}" "${OUT_DIR}/${extra}" "$extra"
done
for bundle in serving-bundle-run16.json qwen-embedding-bundle-v1.json; do
  [[ -e "${BM_KIT_DIR}/bundles/${bundle}" ]] \
    && place "${BM_KIT_DIR}/bundles/${bundle}" "${OUT_DIR}/bundles/${bundle}" "bundles/${bundle}"
done

echo "-- 凭据模板 --"
if [[ -d "${KIT_DIR}/secrets.example" ]]; then
  mkdir -p "${OUT_DIR}/secrets.example"
  for f in "${KIT_DIR}"/secrets.example/*; do
    [[ -e "$f" ]] || continue
    place "$f" "${OUT_DIR}/secrets.example/$(basename "$f")" "secrets.example/$(basename "$f")"
  done
fi

echo "-- 两个大文件 --"
place "${KIT_DIR}/${IMAGE_TGZ}" "${OUT_DIR}/${IMAGE_TGZ}" "$IMAGE_TGZ"
place "${KIT_DIR}/${IMAGE_TGZ}.sha256" "${OUT_DIR}/${IMAGE_TGZ}.sha256" "${IMAGE_TGZ}.sha256"
place "${DATA_XFER_DIR}/${DATA_TGZ}" "${OUT_DIR}/${DATA_TGZ}" "$DATA_TGZ"
place "${DATA_XFER_DIR}/${DATA_TGZ}.sha256" "${OUT_DIR}/${DATA_TGZ}.sha256" "${DATA_TGZ}.sha256"

if [[ "$WITH_LOCAL_KEYS" == "1" ]]; then
  echo "-- [测试专用] 把本机 4 个密钥以符号链接放进 secrets/（绝不进正式交付包）--"
  mkdir -p "${OUT_DIR}/secrets"
  for key in .deepseek_api_key .bocha_api_key .serper_api_key .sglang_api_key; do
    if [[ -f "/home/longxiang/MiroThinker/${key}" ]]; then
      ln -sfn "/home/longxiang/MiroThinker/${key}" "${OUT_DIR}/secrets/${key}"
      printf '  [ok]   symlink secrets/%s -> %s\n' "$key" "/home/longxiang/MiroThinker/${key}"
    else
      WARNINGS+=("缺密钥文件：$key")
      printf '  [warn] 缺 %s\n' "$key"
    fi
  done
fi

# ---- 生成 BUNDLE-MANIFEST.txt -------------------------------------------------
manifest="${OUT_DIR}/BUNDLE-MANIFEST.txt"
image_id="$(awk -F': ' '/^image_id:/ {print $2}' "${OUT_DIR}/kit-manifest.txt" 2>/dev/null)"
{
  echo "# 现场交付包清单 (BUNDLE-MANIFEST.txt)"
  echo "# 生成: $(date -Is)  主机: $(hostname)"
  echo "# 生成脚本: deploy/docker/build-site-bundle.sh"
  echo "# 镜像: ${image_id:-<见 kit-manifest.txt>}（tag mirothinker-serving:v1）"
  echo "#"
  echo "# 列: kind size_bytes hardlinks sha256 relpath"
  echo "#   kind = file（普通文件） / symlink（仅测试用 secrets/）"
} > "$manifest"
total_bytes=0
while IFS= read -r -d '' path; do
  rel="${path#"$OUT_DIR"/}"
  size="$(stat -c %s "$path")"
  nlink="$(stat -c %h "$path")"
  digest="$(sha256sum "$path" | cut -d' ' -f1)"
  printf 'file %s %s %s %s\n' "$size" "$nlink" "$digest" "$rel" >> "$manifest"
  total_bytes=$((total_bytes + size))
done < <(find "$OUT_DIR" -type f ! -name 'BUNDLE-MANIFEST.txt' ! -name 'README-FIRST.txt' -print0 | sort -z)
while IFS= read -r -d '' link; do
  rel="${link#"$OUT_DIR"/}"
  printf 'symlink 0 1 - %s -> %s\n' "$rel" "$(readlink "$link")" >> "$manifest"
done < <(find "$OUT_DIR" -type l -print0 | sort -z)
{
  echo "#"
  echo "totals: files_with_bytes=$(( $(grep -c '^file ' "$manifest") ))  bytes=${total_bytes}  bytes_human=$(numfmt --to=iec --suffix=B "$total_bytes" 2>/dev/null || echo "$total_bytes")"
  echo "placement: hard_linked=${LINKED}  copied=${COPIED}"
  if [[ ${#WARNINGS[@]} -gt 0 ]]; then
    echo "warnings:"
    for w in "${WARNINGS[@]}"; do echo "  - $w"; done
  else
    echo "warnings: none"
  fi
} >> "$manifest"

# ---- 生成 README-FIRST.txt ---------------------------------------------------
cat > "${OUT_DIR}/README-FIRST.txt" <<EOF
Canonical V2 服务栈 · 现场交付包（v1）
================================================================

给操作者（三步）：

  ①  校验
        cd <本目录>
        sha256sum -c mirothinker-serving-v1.tar.gz.sha256
        sha256sum -c serving-data-v1.tar.gz.sha256
        再逐文件核对本目录的 BUNDLE-MANIFEST.txt（可选，最稳）

  ②  传到甲方机器
        把**整个目录**（≈3.2 GB，可先压成一个 tar 再传）放到目标机的任意目录，
        例如 /srv/mirothinker-delivery/。两个大文件必须与 install-site.sh 同目录。

  ③  安装（需要 sudo）
        cd /srv/mirothinker-delivery
        sudo ./install-site.sh              # 正式安装
        sudo ./install-site.sh --dry-run    # 只检查不落地（推荐先跑一遍）

  预计耗时（本机实测）：校验 19 s → 解包数据 44 s → 10 件校验 40 s → docker load 23 s
            → 起服务并等到健康：**首次 7–8 分钟**（冷数据面 + 无 mount-receipt 的全量校验），
              之后重启约 5 分钟 ⇒ 首次安装总计约 **11–13 分钟**（机器慢或磁盘慢会更久）。

安装前必须准备好（否则安装器会 [FAIL] 并逐条告诉你缺什么）：

  * 机器：Linux x86_64（Ubuntu 22.04/24.04），docker + compose v2，≥64 GB 内存
    （低于 24 GB 会直接失败），/var/tmp 所在分区空闲 ≥25 GB（安装期峰值）。
  * 4 个密钥文件，放在本目录的 secrets/ 下，权限 0600：
        secrets/.deepseek_api_key   secrets/.bocha_api_key
        secrets/.serper_api_key     secrets/.sglang_api_key
    （也可以先不放：安装器会停下并告诉你确切路径；凭据之后可走 /admin 的密钥页。）
  * 端口 18188 空闲（安装器会检查并指出占用者）。
  * 出网：能访问嵌入服务端点（默认 http://100.64.0.27:18005/v1，安装器会用密钥实测
    200 + 维度 4096）与 chat LLM 端点。**不需要**访问 PyPI 或 apt 源。

安装完成后的第一件事（**先配置，再验收**）：

  ⚠ 首装的受管配置是空的 ⇒ 答案走降级渲染路径，replay 门会红在 G1_framing。
    先到 /admin 配好 chat LLM 选档 + 密钥（+ 嵌入端点连测），门才 7/7。这是配置不是故障。


  浏览 http://<机器IP>:18188/main   → 用状态目录里的首启口令登录并立即改密
        /var/tmp/mirothinker-canonical-v2-s12f/admin-initial-password.txt
  问答页：http://<机器IP>:18188/chat
  验收：
        docker compose -f compose.yaml exec -T app mirothinker-verify
        docker compose -f compose.yaml exec -T app mirothinker-replay --out-dir /tmp/accept

细节（口径、故障处置、备份/回滚）见本目录 README.md（runbook）。
EOF

echo
echo "== 完成 =="
printf '  硬链接 %d 个，复制 %d 个\n' "$LINKED" "$COPIED"
printf '  目录大小（含两个大文件）：%s\n' "$(du -sh "$OUT_DIR" | cut -f1)"
printf '  清单：%s\n' "$manifest"
printf '  说明：%s\n' "${OUT_DIR}/README-FIRST.txt"
if [[ ${#WARNINGS[@]} -gt 0 ]]; then
  echo "  警告："
  printf '    - %s\n' "${WARNINGS[@]}"
fi
