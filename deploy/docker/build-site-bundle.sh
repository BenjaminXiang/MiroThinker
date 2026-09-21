#!/usr/bin/env bash
# 组装「现场交付包」——运营者从我们这儿下载、带到甲方机器、跑一条命令要用的全部东西。
#
#   deploy/docker/build-site-bundle.sh [--with-local-keys] [--out DIR]
#
# 输出目录（默认 /var/tmp/mirothinker-site-bundle/）：
#   install-site.sh                       一键安装脚本（Deliverable 2）
#   README-FIRST.txt                      给运营者的三句话（生成）
#   BUNDLE-MANIFEST.txt                   逐文件 尺寸+sha256（生成）
#   mirothinker-serving-<ver>.tar.gz      +.sha256   容器镜像（v1 1.56 GiB / v1.1 2.01 GiB）
#   serving-data-<ver>.tar.gz             +.sha256   数据面（两个冻结目录）
#   compose.yaml / README.md / kit-manifest.txt       编排与 runbook
#   checksums.sha256 / sizes.tsv          10 个交付物的校验清单（来自裸机 kit）
#   bundles/{serving-bundle-run16.json,qwen-embedding-bundle-v1.json}
#   secrets.example/                      凭据模板（真值由运营者放 secrets/）
#   serve-command-v11.sh                  v1.1：覆盖镜像内命令文件的服务包路径（只差一个 token）
#   entrypoint-v11.sh                     v1.1：覆盖镜像内入口脚本的预检服务包路径（只差一个 token）
#
# 版本差异由 env 决定：MIROTHINKER_IMAGE_TGZ_NAME / MIROTHINKER_DATA_TGZ_NAME /
# MIROTHINKER_KIT_DIR / MIROTHINKER_DATA_XFER_DIR / MIROTHINKER_BM_KIT_DIR。
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
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

IMAGE_TGZ="${MIROTHINKER_IMAGE_TGZ_NAME:-mirothinker-serving-v1.tar.gz}"
DATA_TGZ="${MIROTHINKER_DATA_TGZ_NAME:-serving-data-v1.tar.gz}"
# 版本号从镜像 tar 名推导（mirothinker-serving-v1.1.tar.gz → v1.1），可 env 覆盖
DELIVERY_VERSION="${MIROTHINKER_DELIVERY_VERSION:-}"
if [[ -z "$DELIVERY_VERSION" ]]; then
  DELIVERY_VERSION="${IMAGE_TGZ#mirothinker-serving-}"
  DELIVERY_VERSION="${DELIVERY_VERSION%.tar.gz}"
fi
# compose.yaml 取**交付源树**这份（镜像 kit 里那份是构建时的快照，可能不含交付期的挂载改动）
COMPOSE_SRC="${MIROTHINKER_COMPOSE_SRC:-${DEPLOY_DIR}/compose.yaml}"
# 首启耗时说明（演练实测值可注入；默认写 v1 实测）
FIRSTBOOT_NOTE="${MIROTHINKER_FIRSTBOOT_NOTE:-校验 19 s → 解包数据 44 s → 10 件校验 40 s → docker load 23 s
            → 起服务并等到健康：首次约 8 分钟（冷数据面 + 无 mount-receipt 的全量校验），
              之后重启约 5 分钟 ⇒ 首次安装总计约 11–13 分钟（机器更慢则更久）。}"
# v1.1：冻结命令文件里仍写着旧服务包名（release/v1.1 树未改），而交付必须服务新包
# ⇒ 由本目录生成两份**只差一个 token** 的覆盖件，compose 以只读 bind 覆盖镜像内的
#    ① 冻结命令文件（决定服务装载哪个包）② 入口脚本（预检里写死了同一个包名）。
CMD_SRC="${MIROTHINKER_CMD_SRC:-/home/longxiang/MiroThinker/.worktrees/release-v11/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18188-command.sh}"
CMD_TARGET_NAME="${MIROTHINKER_CMD_NAME:-serve-command-v11.sh}"
ENTRYPOINT_SRC="${MIROTHINKER_ENTRYPOINT_SRC:-/home/longxiang/MiroThinker/.worktrees/release-v11/deploy/docker/entrypoint.sh}"
ENTRYPOINT_TARGET_NAME="${MIROTHINKER_ENTRYPOINT_NAME:-entrypoint-v11.sh}"
OLD_PACK_TOKEN="${MIROTHINKER_OLD_PACK_TOKEN:-serving-pack-run16-readerbound}"
NEW_PACK_TOKEN="${MIROTHINKER_NEW_PACK_TOKEN:-serving-pack-run16-v11}"
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
place "${COMPOSE_SRC}" "${OUT_DIR}/compose.yaml" "compose.yaml（交付源树：含命令文件覆盖挂载）"
place "${KIT_DIR}/README.md" "${OUT_DIR}/README.md" "README.md（runbook）"
place "${KIT_DIR}/kit-manifest.txt" "${OUT_DIR}/kit-manifest.txt" "kit-manifest.txt"
place "${DEPLOY_DIR}/CONFIG-GUIDE.md" "${OUT_DIR}/CONFIG-GUIDE.md" "CONFIG-GUIDE.md（配置指南）"

echo "-- 校验清单（裸机 kit 的 10 个交付物）--"
place "${BM_KIT_DIR}/checksums.sha256" "${OUT_DIR}/checksums.sha256" "checksums.sha256"
for extra in sizes.tsv site-paths.txt; do
  [[ -e "${BM_KIT_DIR}/${extra}" ]] && place "${BM_KIT_DIR}/${extra}" "${OUT_DIR}/${extra}" "$extra"
done
for bundle in serving-bundle-run16.json qwen-embedding-bundle-v1.json; do
  [[ -e "${BM_KIT_DIR}/bundles/${bundle}" ]] \
    && place "${BM_KIT_DIR}/bundles/${bundle}" "${OUT_DIR}/bundles/${bundle}" "bundles/${bundle}"
done
# 数据面里的服务包/索引名：直接从 checksums.sha256 里取（本包自证，避免写死）
DATA_PACK_NAME="$(grep -o 'serving-pack-[A-Za-z0-9._-]*' "${OUT_DIR}/checksums.sha256" 2>/dev/null | head -1)"
DATA_INDEX_NAME="$(grep -o 'index-v[0-9][A-Za-z0-9._-]*' "${OUT_DIR}/checksums.sha256" 2>/dev/null | head -1)"
DATA_PACK_NAME="${DATA_PACK_NAME:-serving-pack-<未知>}"
DATA_INDEX_NAME="${DATA_INDEX_NAME:-index-<未知>}"

echo "-- 凭据模板 --"
if [[ -d "${KIT_DIR}/secrets.example" ]]; then
  mkdir -p "${OUT_DIR}/secrets.example"
  for f in "${KIT_DIR}"/secrets.example/*; do
    [[ -e "$f" ]] || continue
    place "$f" "${OUT_DIR}/secrets.example/$(basename "$f")" "secrets.example/$(basename "$f")"
  done
fi

echo "-- 覆盖件①②：冻结命令文件 + 入口脚本（v1.1 服务包路径）--"
# 两份覆盖件同一套 token、同一套审计：先断言"源里这个 token 只出现 N 次"，
# 再断言"生成件与源只差这个 token"，最后断言生成件里目标路径确实变了。
generate_override() {
  local src="$1" name="$2" mode="$3" expect_hits="$4" assert_grep="$5" what="$6"
  local generated="${OUT_DIR}/${name}" hits
  hits="$(grep -c "${OLD_PACK_TOKEN}" "$src" 2>/dev/null || true)"
  if [[ "$hits" == "0" ]]; then
    printf '  [warn] %s 里没有 %s（源已是新包名？）⇒ 覆盖件与源一致\n' "$what" "$OLD_PACK_TOKEN"
  elif [[ "$hits" != "$expect_hits" ]]; then
    printf '  [FAIL] %s 里 %s 出现 %s 次（预期 %s 次）—— 覆盖范围可能变了，拒绝出包\n' \
      "$what" "$OLD_PACK_TOKEN" "$hits" "$expect_hits" >&2
    exit 1
  fi
  sed "s#${OLD_PACK_TOKEN}#${NEW_PACK_TOKEN}#g" "$src" > "$generated"
  chmod "$mode" "$generated"
  if diff <(tr ' ' '\n' < "$src" | sed "s#${OLD_PACK_TOKEN}#${NEW_PACK_TOKEN}#g") \
          <(tr ' ' '\n' < "$generated") >/dev/null; then
    printf '  [ok]   %s（只改服务包名 %s → %s ×%s；mode %s；sha256=%s）\n' \
      "$name" "$OLD_PACK_TOKEN" "$NEW_PACK_TOKEN" "${hits:-0}" "$mode" "$(sha256sum "$generated" | cut -c1-16)"
  else
    echo "  [FAIL] $name 与源 $what 差异不止服务包名 —— 拒绝出包" >&2
    exit 1
  fi
  if grep -q -- "$assert_grep" "$generated"; then
    printf '  [ok]   %s 里 %s\n' "$name" "$assert_grep"
  else
    echo "  [FAIL] $name 里没找到「$assert_grep」" >&2
    exit 1
  fi
}
if [[ -f "$CMD_SRC" ]]; then
  generate_override "$CMD_SRC" "$CMD_TARGET_NAME" 0644 1 "--serving-pack .*${NEW_PACK_TOKEN}" 冻结命令文件
else
  printf '  [warn] 缺冻结命令文件源（%s）⇒ 交付包不含覆盖件（现场会服务镜像里写的旧包）\n' "$CMD_SRC"
fi
if [[ -f "$ENTRYPOINT_SRC" ]]; then
  generate_override "$ENTRYPOINT_SRC" "$ENTRYPOINT_TARGET_NAME" 0755 1 'PACK_DIR=' 入口脚本
  if grep -F -q -- "PACK_DIR=\"\${DATA_ROOT}/${NEW_PACK_TOKEN}\"" "${OUT_DIR}/${ENTRYPOINT_TARGET_NAME}"; then
    printf '  [ok]   %s 预检路径 = %s（容器内同路径，镜像里那份是旧包名）\n' \
      "$ENTRYPOINT_TARGET_NAME" "$NEW_PACK_TOKEN"
  else
    echo "  [FAIL] ${ENTRYPOINT_TARGET_NAME} 里的预检路径不是 ${NEW_PACK_TOKEN} —— 拒绝出包" >&2
    exit 1
  fi
else
  printf '  [warn] 缺入口脚本源（%s）⇒ 交付包不含入口覆盖件（新数据面下容器预检会 exit 78）\n' "$ENTRYPOINT_SRC"
fi

echo "-- 两个大文件 --"
place "${KIT_DIR}/${IMAGE_TGZ}" "${OUT_DIR}/${IMAGE_TGZ}" "$IMAGE_TGZ"
place "${KIT_DIR}/${IMAGE_TGZ}.sha256" "${OUT_DIR}/${IMAGE_TGZ}.sha256" "${IMAGE_TGZ}.sha256"
place "${DATA_XFER_DIR}/${DATA_TGZ}" "${OUT_DIR}/${DATA_TGZ}" "$DATA_TGZ"
place "${DATA_XFER_DIR}/${DATA_TGZ}.sha256" "${OUT_DIR}/${DATA_TGZ}.sha256" "${DATA_TGZ}.sha256"
# 两个 .sha256 一律改写成**相对文件名**：README-FIRST 让操作者在交付包目录里
# `sha256sum -c <name>.sha256`，绝对路径在他们的机器上不存在（打包机上还会校验到
# 另一个同名文件）。
for tgz in "$IMAGE_TGZ" "$DATA_TGZ"; do
  sha_out="${OUT_DIR}/${tgz}.sha256"
  [[ -s "$sha_out" ]] || continue
  digest="$(awk '{print $1}' "$sha_out")"
  printf '%s  %s\n' "$digest" "$tgz" > "$sha_out"
  printf '  [ok]   %s.sha256 改写为相对文件名（%s…）\n' "$tgz" "${digest:0:16}"
done

echo "-- 密钥目录（空目录 + 说明；4 个密钥由操作者在此落位）--"
mkdir -p "${OUT_DIR}/secrets"
if [[ -s "${KIT_DIR}/secrets/README.txt" ]]; then
  cp "${KIT_DIR}/secrets/README.txt" "${OUT_DIR}/secrets/README.txt"
  printf '  [ok]   secrets/ 已建（含 README.txt）—— CONFIG-GUIDE §2 的 install 命令才有落点\n'
else
  printf '把 4 个密钥文件放进本目录（文件名必须完全一致，0600）：\n  .deepseek_api_key  .bocha_api_key  .serper_api_key  .sglang_api_key\n' \
    > "${OUT_DIR}/secrets/README.txt"
  printf '  [warn] kit 里没有 secrets/README.txt，已就地生成一份\n'
fi

echo "-- 预置受管配置（非机密：端点/档位/窗口）--"
mkdir -p "${OUT_DIR}/state/config-managed"
place "${DEPLOY_DIR}/site-config/managed-settings.json" \
      "${OUT_DIR}/state/config-managed/settings.json" "state/config-managed/settings.json（预置）"

echo "-- 出包自检：交付件里的数字/名字 vs 随包 bundle --"
# 硬规则（预置不许钉嵌入地址/模型）会 exit 1 拦下出包；软规则只逐条报（file:line），
# 提醒随包更新文档里的端点/维度/模型/包名 —— 改不改由出包人判断，脚本不改任何文字。
if ! python3 "${DEPLOY_DIR}/check-delivery-consistency.py" "${OUT_DIR}"; then
  printf '  [FAIL] 出包自检不通过：先修预置（或对应的交付件），再重新出包\n' >&2
  exit 1
fi

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
image_tag="$(awk -F': ' '/^image_tag:/ {print $2}' "${OUT_DIR}/kit-manifest.txt" 2>/dev/null)"
{
  echo "# 现场交付包清单 (BUNDLE-MANIFEST.txt)"
  echo "# 生成: $(date -Is)  主机: $(hostname)"
  echo "# 生成脚本: deploy/docker/build-site-bundle.sh"
  echo "# 交付版本: ${DELIVERY_VERSION}"
  echo "# 镜像: ${image_id:-<见 kit-manifest.txt>}（tag ${image_tag:-mirothinker-serving:v1}）"
  echo "# 数据面: ${DATA_TGZ} = ${DATA_PACK_NAME} + ${DATA_INDEX_NAME}"
  echo "# 服务包路径: 由 ${CMD_TARGET_NAME} 覆盖镜像内冻结命令文件（--serving-pack → ${NEW_PACK_TOKEN}）"
  echo "#           并由 ${ENTRYPOINT_TARGET_NAME} 覆盖镜像内入口脚本的同名预检（两者都只差这一个 token）"
  echo "#   （kit-manifest.txt 的 data_plane_not_included 一行是镜像构建脚本写死的提示语，"
  echo "#     若与上一行的服务包名不一致，以本清单为准）"
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
Canonical V2 服务栈 · 现场交付包（${DELIVERY_VERSION}）
================================================================

给操作者（三步）：

  配置（只有这一步是人工）：把 4 个密钥写进这个目录的 secrets/（见 CONFIG-GUIDE.md §2）。
  其余全部已预置：不需要改任何配置文件 / 路径 / 数据库。

  ①  校验
        cd <本目录>
        sha256sum -c ${IMAGE_TGZ}.sha256
        sha256sum -c ${DATA_TGZ}.sha256
        再逐文件核对本目录的 BUNDLE-MANIFEST.txt（可选，最稳）

  ②  传到甲方机器
        把**整个目录**（≈3.6 GB，可先压成一个 tar 再传）放到目标机的任意目录，
        例如 /srv/mirothinker-delivery/。两个大文件必须与 install-site.sh 同目录。

  ③  安装（需要 sudo）
        cd /srv/mirothinker-delivery
        sudo ./install-site.sh              # 正式安装
        sudo ./install-site.sh --dry-run    # 只检查不落地（推荐先跑一遍）

  本包内容：镜像 tag ${image_tag:-mirothinker-serving:v1}；数据面 = ${DATA_PACK_NAME} + ${DATA_INDEX_NAME}。
  服务包路径由同目录两份覆盖件钉住（都是"只差一个 token"，compose.yaml 里已按只读 bind 挂好）：
    · ${CMD_TARGET_NAME} → 覆盖镜像内冻结命令文件（--serving-pack → ${NEW_PACK_TOKEN}）
    · ${ENTRYPOINT_TARGET_NAME} → 覆盖镜像内入口脚本的预检路径（同一个包名，否则容器会 exit 78）
  这两个文件别删、别改：删了服务会回到旧包 / 起不来。

  预计耗时（本机实测）：${FIRSTBOOT_NOTE}

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
    （本包 state/config-managed/settings.json 若在位，则端点/档位已预置，只差密钥。）


  浏览 http://<机器IP>:18188/main   → 用状态目录里的首启口令登录并立即改密
        /var/tmp/mirothinker-canonical-v2-s12f/admin-initial-password.txt
  问答页：http://<机器IP>:18188/chat
  验收：
        docker compose -f compose.yaml exec -T app mirothinker-verify
        docker compose -f compose.yaml exec -T app mirothinker-replay --out-dir /tmp/accept

细节：配置只看 CONFIG-GUIDE.md（给运维看，含"只填 key"的边界与症状表）；
      运维/故障/备份/回滚看 README.md（runbook）。
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
