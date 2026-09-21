#!/usr/bin/env bash
# Canonical V2 服务栈 · 现场一键安装器（在甲方机器上、以 sudo 运行，幂等，支持 --dry-run）
#
#   sudo ./install-site.sh [--dry-run] [--fast] [--skip-probes] [--strict-probes]
#                          [--accept-degraded-keys] [--port N] [--bundle-dir DIR]
#                          [--no-up] [--timeout-seconds N]
#
# 环境变量（**测试专用**）：
#   MIROTHINKER_SITE_ROOT=<prefix>   给所有"宿主路径"加前缀，使整套流程可以在不碰
#                                    真实 /var/tmp/mirothinker-data-v2 与活线状态目录的
#                                    前提下排练。默认空 = 用真实绝对路径。
#   MIROTHINKER_SITE_PORT            等价于 --port
#   MIROTHINKER_SITE_PG_VOLUME       PG 数据卷名（默认 mirothinker-pgdata）
#
# 退出码：0 全通 / 2 用法错 / 10 预检失败 / 11 校验失败 / 12 配置失败
#         / 13 compose 或健康检查失败 / 14 验收（verify）失败
#
# 设计约定：容器内的**冻结绝对路径**一律不改（compose 负责映射）；本脚本只改宿主侧。

set -uo pipefail

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SITE_ROOT="${MIROTHINKER_SITE_ROOT:-}"
DRY_RUN=0
FAST=0
SKIP_PROBES=0
STRICT_PROBES=0
ACCEPT_DEGRADED_KEYS=0
DO_UP=1
PORT="${MIROTHINKER_SITE_PORT:-}"
HEALTH_TIMEOUT="${MIROTHINKER_SITE_HEALTH_TIMEOUT:-900}"
PG_VOLUME="${MIROTHINKER_SITE_PG_VOLUME:-mirothinker-pgdata}"
CMD_OVERRIDE_NAME="${MIROTHINKER_CMD_NAME:-serve-command-v11.sh}"
ENTRYPOINT_OVERRIDE_NAME="${MIROTHINKER_ENTRYPOINT_NAME:-entrypoint-v11.sh}"
# 交付物文件名与镜像 tag 由交付包自证（kit-manifest.txt），避免把 v1/v1.1 写死
IMAGE_TGZ="${MIROTHINKER_IMAGE_TGZ_NAME:-}"
DATA_TGZ="${MIROTHINKER_DATA_TGZ_NAME:-}"
IMAGE_TAG="${MIROTHINKER_IMAGE_TAG:-}"

# 冻结的容器内路径（仅供打印/对照；改它们等于改交付契约）
CONTAINER_DATA_ROOT="/var/tmp/mirothinker-data-v2"
CONTAINER_STATE_DIR="/var/tmp/mirothinker-canonical-v2-s12f"

PASS=0; FAIL=0; WARN=0
declare -a SUMMARY=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --fast) FAST=1; shift ;;
    --skip-probes) SKIP_PROBES=1; shift ;;
    --strict-probes) STRICT_PROBES=1; shift ;;
    --accept-degraded-keys) ACCEPT_DEGRADED_KEYS=1; shift ;;
    --port) PORT="$2"; shift 2 ;;
    --bundle-dir) BUNDLE_DIR="$(cd "$2" && pwd)"; shift 2 ;;
    --no-up) DO_UP=0; shift ;;
    --timeout-seconds) HEALTH_TIMEOUT="$2"; shift 2 ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1（--help 看用法）" >&2; exit 2 ;;
  esac
done
PORT="${PORT:-18188}"

# ---- 宿主路径（全部可被 MIROTHINKER_SITE_ROOT 加前缀） ------------------------
DATA_ROOT="${SITE_ROOT}/var/tmp/mirothinker-data-v2"
STATE_DIR="${SITE_ROOT}/var/tmp/mirothinker-canonical-v2-s12f"
HOST_TMP="${SITE_ROOT}/var/tmp"          # 磁盘/空间检查落在哪
ENV_FILE="${BUNDLE_DIR}/.env"
SECRETS_DIR="${BUNDLE_DIR}/secrets"
PG_ENV_FILE="${SECRETS_DIR}/postgres.env"
MANAGED_DIR="${BUNDLE_DIR}/state/config-managed"

ok()   { PASS=$((PASS+1)); printf '  [ok]   %s\n' "$*"; }
warn() { WARN=$((WARN+1)); printf '  [warn] %s\n' "$*"; SUMMARY+=("[warn] $*"); }
fail() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$*"; SUMMARY+=("[FAIL] $*"); }
step() { printf '\n== %s ==\n' "$*"; }
die()  { local code="$1"; shift; fail "$*"; summary_block; exit "$code"; }

summary_block() {
  printf '\n================ 安装结果 ================\n'
  printf '  [ok] %d   [warn] %d   [FAIL] %d\n' "$PASS" "$WARN" "$FAIL"
  if [[ ${#SUMMARY[@]} -gt 0 ]]; then
    printf '  需要你知道的条目：\n'
    printf '    %s\n' "${SUMMARY[@]}"
  fi
  if [[ "$FAIL" == "0" ]]; then
    printf '  结论：安装完成（或 --dry-run 检查通过）\n'
  else
    printf '  结论：有未通过项 —— 按上面的 [FAIL] 逐条处理后重跑本脚本（幂等）\n'
  fi
  if [[ -n "$SITE_ROOT" ]]; then
    printf '  注意：本次用了测试前缀 MIROTHINKER_SITE_ROOT=%s（所有宿主路径都在它下面）\n' "$SITE_ROOT"
  fi
  printf '==========================================\n'
}

# 在测试前缀模式下，checksums.sha256 / sizes.tsv 里写的是真实绝对路径，
# 需要把前缀补上；正式安装（无前缀）时是恒等替换。
rewrite_paths() {
  local src="$1" dst="$2"
  if [[ -z "$SITE_ROOT" ]]; then cp "$src" "$dst"; return 0; fi
  sed "s#/var/tmp/mirothinker-data-v2#${DATA_ROOT}#g" "$src" > "$dst"
}

human_elapsed() { printf '%dm%02ds' $(($1 / 60)) $(($1 % 60)); }

# 交付物校验/加载的中间输出必须用 mktemp：**不能**用 /tmp 下的固定文件名。
# 实测（Ubuntu 24.04，fs.protected_regular=2）：非 root 跑过一次之后，再用 sudo 跑，
# root 打不开那个属于别人的 /tmp 文件（O_CREAT 被拒）⇒ 装到一半以"校验失败"退出，
# 而报错文案还指向校验和，最难查。
tmp_checksums_out="$(mktemp)"
tmp_load_out="$(mktemp)"
cleanup_tmp() { rm -f "$tmp_checksums_out" "$tmp_load_out"; }
trap cleanup_tmp EXIT

# 数据属主 = 容器内运行 uid（compose 的 user:）。真 root 安装时宿主侧资产默认是
# root:root，而容器里 uid 是数据属主 ⇒ 状态目录 0700 会让入口预检 exit 78、
# 密钥 0600 会让容器读不到（能力静默降级）。凡是容器要读/写的东西都归一到这里。
owner_uid=""
owner_gid=""
normalize_owner() {
  [[ "$(id -u)" == "0" && -n "$owner_uid" && -e "$1" ]] || return 0
  chown -R "${owner_uid}:${owner_gid}" "$1" 2>/dev/null
}

# 覆盖件检查（--dry-run 也跑）：这两份文件缺失/不可执行 ⇒ 容器 exit 78 或服务错包，
# 是最该在"动任何东西之前"发现的问题。
check_overrides() {
  if [[ -s "${BUNDLE_DIR}/${CMD_OVERRIDE_NAME}" ]]; then
    if grep -q -- "--serving-pack .*serving-pack-run16-v11" "${BUNDLE_DIR}/${CMD_OVERRIDE_NAME}"; then
      ok "命令文件覆盖件在位且指向 serving-pack-run16-v11（v1.1 服务包）"
    else
      warn "命令文件覆盖件存在但没指向 serving-pack-run16-v11：请用 v1.1 的交付包"
    fi
  else
    warn "缺命令文件覆盖件 ${CMD_OVERRIDE_NAME}：将服务镜像内默认的服务包（可能是旧包）"
  fi
  # 入口覆盖件：镜像内那份入口脚本的预检把服务包路径写死成旧包名，新数据面下会 exit 78。
  # 覆盖件必须**可执行**（bind mount 保留宿主权限，容器内 uid 非 root）。
  if [[ -s "${BUNDLE_DIR}/${ENTRYPOINT_OVERRIDE_NAME}" ]]; then
    if ! grep -F -q -- 'PACK_DIR="${DATA_ROOT}/serving-pack-run16-v11"' "${BUNDLE_DIR}/${ENTRYPOINT_OVERRIDE_NAME}"; then
      warn "入口覆盖件存在但预检路径不是 serving-pack-run16-v11：请用 v1.1 的交付包"
    elif [[ ! -x "${BUNDLE_DIR}/${ENTRYPOINT_OVERRIDE_NAME}" ]]; then
      if [[ "$DRY_RUN" == "1" ]]; then
        fail "入口覆盖件不可执行（容器内会 exec 失败）：chmod 0755 ${BUNDLE_DIR}/${ENTRYPOINT_OVERRIDE_NAME}"
      elif chmod 0755 "${BUNDLE_DIR}/${ENTRYPOINT_OVERRIDE_NAME}" 2>/dev/null; then
        ok "入口覆盖件在位（权限已补成 0755）"
      else
        fail "入口覆盖件不可执行（容器内会 exec 失败）：chmod 0755 ${BUNDLE_DIR}/${ENTRYPOINT_OVERRIDE_NAME}"
      fi
    else
      ok "入口覆盖件在位且可执行（预检路径 serving-pack-run16-v11）"
    fi
  else
    warn "缺入口覆盖件 ${ENTRYPOINT_OVERRIDE_NAME}：容器预检会因找不到旧服务包而 exit 78（新数据面下起不来）"
  fi
}

# ==============================================================================
step "0. 前置：身份 / 目录 / 参数"
printf '  运行身份: uid=%s（%s）\n' "$(id -u)" "$(id -un 2>/dev/null || echo '?')"
printf '  交付包:   %s\n' "$BUNDLE_DIR"
printf '  宿主路径: 数据 %s\n' "$DATA_ROOT"
printf '            状态 %s\n' "$STATE_DIR"
printf '            端口 %s（容器内固定 18188）\n' "$PORT"
if [[ "$SITE_ROOT" == "" && "$(id -u)" != "0" ]]; then
  warn "未以 root 运行：能装（若当前用户在 docker 组）但状态目录/数据目录属主可能不对；建议 sudo"
fi
if [[ -z "$IMAGE_TGZ" ]]; then
  IMAGE_TGZ="$(cd "$BUNDLE_DIR" && ls -1 mirothinker-serving-*.tar.gz 2>/dev/null | head -1)"
fi
if [[ -z "$DATA_TGZ" ]]; then
  DATA_TGZ="$(cd "$BUNDLE_DIR" && ls -1 serving-data-*.tar.gz 2>/dev/null | head -1)"
fi
if [[ -z "$IMAGE_TAG" && -s "${BUNDLE_DIR}/kit-manifest.txt" ]]; then
  IMAGE_TAG="$(awk -F': ' '/^image_tag:/ {print $2}' "${BUNDLE_DIR}/kit-manifest.txt" | head -1)"
fi
IMAGE_TAG="${IMAGE_TAG:-mirothinker-serving:v1}"
printf '  交付物:   镜像 %s（tag %s） / 数据 %s\n' "${IMAGE_TGZ:-<缺失>}" "$IMAGE_TAG" "${DATA_TGZ:-<缺失>}"
for f in "${BUNDLE_DIR}/${IMAGE_TGZ}" "${BUNDLE_DIR}/${DATA_TGZ}" \
         "${BUNDLE_DIR}/compose.yaml" "${BUNDLE_DIR}/checksums.sha256"; do
  [[ -e "$f" ]] || die 10 "交付包缺少文件：$f（是不是只拷了一部分？）"
done
ok "交付包关键文件齐全"

# ==============================================================================
step "1. 预检"
if command -v docker >/dev/null 2>&1; then ok "docker 存在：$(docker --version 2>/dev/null | head -1)"; else die 10 "缺少 docker"; fi
if docker compose version >/dev/null 2>&1; then ok "compose v2 存在：$(docker compose version --short 2>/dev/null)"; else die 10 "缺少 docker compose v2（插件）"; fi
docker info >/dev/null 2>&1 && ok "docker daemon 可用" || die 10 "docker daemon 不可用（权限？未启动？）"

mem_gb="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)"
if (( mem_gb >= 64 )); then ok "内存 ${mem_gb} GB（≥64 GB 达标）"
elif (( mem_gb >= 24 )); then warn "内存 ${mem_gb} GB < 建议的 64 GB：服务稳态 RSS ≈17.6 GB + 采集库，可能被 OOM"
else fail "内存 ${mem_gb} GB < 24 GB：不够（服务稳态 RSS ≈17.6 GB）"; fi

probe_dir="$HOST_TMP"
while [[ ! -d "$probe_dir" && "$probe_dir" != "/" ]]; do probe_dir="$(dirname "$probe_dir")"; done
avail_gb="$(df -BG --output=avail "$probe_dir" 2>/dev/null | tail -1 | tr -dc '0-9')"
avail_gb="${avail_gb:-0}"
if (( avail_gb >= 25 )); then ok "磁盘可用 ${avail_gb} GB（按 ${probe_dir} 所在分区；安装期需要 ≈25 GB：压缩包 3.2 GB + 解包 7 GB + 镜像 5.2 GB）"
else fail "磁盘可用 ${avail_gb} GB < 25 GB（${probe_dir} 所在分区）"; fi

holder="$(ss -ltnp 2>/dev/null | awk -v p=":${PORT}" '$4 ~ p {print $4" "$NF; exit}')"
if [[ -n "$holder" ]]; then
  # 幂等重跑/升级时，端口往往正是**本栈自己**占着 —— 那不是错误
  self_ports="$(cd "$BUNDLE_DIR" 2>/dev/null && docker compose ps --format '{{.Ports}}' 2>/dev/null | tr ',' '\n' | grep -c ":${PORT}->" || true)"
  if [[ "${self_ports:-0}" -gt 0 ]]; then
    ok "端口 ${PORT} 由**本栈**占用（幂等重跑/升级场景，正常）"
  else
    fail "端口 ${PORT} 已被占用：${holder}"
  fi
else
  ok "端口 ${PORT} 空闲"
fi

if [[ "$SKIP_PROBES" == "1" ]]; then
  warn "已跳过出网探针（--skip-probes）"
else
  # ① 嵌入端点：用交付包里的 qwen-embedding-bundle-v1.json 拿端点与维度，用密钥实测
  emb_bundle="${BUNDLE_DIR}/bundles/qwen-embedding-bundle-v1.json"
  key_file="${SECRETS_DIR}/.sglang_api_key"
  if [[ -f "$emb_bundle" ]]; then
    emb_url="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["base_url"])' "$emb_bundle" 2>/dev/null)"
    emb_dim="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["dimension"])' "$emb_bundle" 2>/dev/null)"
  fi
  if [[ -f "$emb_bundle" && -n "${emb_url:-}" && -n "${emb_dim:-}" ]]; then
    if [[ -r "$key_file" ]]; then
      resp_file="$(mktemp)"
      code=$(curl -sS --max-time 30 -o "$resp_file" -w '%{http_code}' "${emb_url%/}/embeddings" \
        -H "Authorization: Bearer $(cat "$key_file")" \
        -H 'Content-Type: application/json' \
        -d '{"model":"Qwen/Qwen3-Embedding-8B","input":["安装器探针"]}' 2>/dev/null)
      dims=$(python3 -c "import json,sys;print(len(json.load(open(sys.argv[1]))['data'][0]['embedding']))" "$resp_file" 2>/dev/null || echo 0)
      rm -f "$resp_file"
      dims="${dims:-0}"
      if [[ "$code" == "200" && "$dims" == "$emb_dim" ]]; then
        ok "嵌入端点 ${emb_url}：HTTP 200，维度 ${dims}（期望 ${emb_dim}）"
      elif [[ "$STRICT_PROBES" == "1" ]]; then
        fail "嵌入端点探针未过：HTTP ${code}，维度 ${dims}（期望 ${emb_dim}）"
      else
        warn "嵌入端点探针未过：HTTP ${code}，维度 ${dims}（期望 ${emb_dim}）—— 服务仍能起，但向量道会降级；确认端点/密钥后可重跑"
      fi
    else
      warn "嵌入端点探针跳过：缺 ${key_file}（安装器稍后会要求补齐 4 个密钥）"
    fi
  else
    warn "嵌入端点探针跳过：交付包里没有 bundles/qwen-embedding-bundle-v1.json"
  fi
  # ② chat LLM 端点：默认探 deepseek（凭 .deepseek_api_key）；可用 MIROTHINKER_SITE_LLM_PROBE 覆盖
  llm_probe="${MIROTHINKER_SITE_LLM_PROBE:-https://api.deepseek.com/v1/models}"
  if [[ -r "${SECRETS_DIR}/.deepseek_api_key" ]]; then
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -H "Authorization: Bearer $(cat "${SECRETS_DIR}/.deepseek_api_key")" "$llm_probe" 2>/dev/null)"
    if [[ "$code" == "200" ]]; then ok "chat LLM 端点可达（${llm_probe} → 200）"
    else warn "chat LLM 端点 ${llm_probe} → HTTP ${code}（不影响起服；答案质量相关，确认端点/密钥）"; fi
  else
    warn "chat LLM 探针跳过：缺 ${SECRETS_DIR}/.deepseek_api_key"
  fi
  ok "不需要访问 PyPI / apt 源（镜像与数据面都是离线交付物）"
fi

if [[ "$FAIL" != "0" ]]; then summary_block; exit 10; fi

# ==============================================================================
step "2. 校验交付包（sha256，动任何东西之前）"
t0=$(date +%s)
for pair in "${IMAGE_TGZ}" "${DATA_TGZ}"; do
  sha_file="${BUNDLE_DIR}/${pair}.sha256"
  if [[ ! -f "$sha_file" ]]; then fail "缺少校验文件 ${pair}.sha256"; continue; fi
  # .sha256 里写的是**打包机上的绝对路径**，现场要对本目录里的同名文件校验
  expected="$(awk '{print $1}' "$sha_file")"
  actual="$(sha256sum "${BUNDLE_DIR}/${pair}" | cut -d' ' -f1)"
  if [[ "$expected" == "$actual" ]]; then
    ok "${pair} sha256 一致（${actual:0:16}…，$(numfmt --to=iec --suffix=B "$(stat -c %s "${BUNDLE_DIR}/${pair}")" 2>/dev/null)）"
  else
    fail "${pair} sha256 不一致：期望 ${expected:0:16}… 实际 ${actual:0:16}…（传输损坏？重新下载）"
  fi
done
printf '  （校验耗时 %s）\n' "$(human_elapsed $(( $(date +%s) - t0 )))"
if [[ "$FAIL" != "0" ]]; then summary_block; exit 11; fi

# ==============================================================================
step "3. 数据面落位（$DATA_ROOT，容器内路径固定为 $CONTAINER_DATA_ROOT）"
if [[ "$DRY_RUN" == "1" ]]; then
  printf '  [dry-run] 会创建 %s 并解包 %s（约 7 GB 解包后）\n' "$DATA_ROOT" "$DATA_TGZ"
else
  mkdir -p "$DATA_ROOT" || die 11 "无法创建 $DATA_ROOT"
  t0=$(date +%s)
  if tar -xzf "${BUNDLE_DIR}/${DATA_TGZ}" -C "$DATA_ROOT"; then
    ok "解包完成（$(human_elapsed $(( $(date +%s) - t0 )))）"
  else
    die 11 "解包失败（磁盘满？压缩包损坏？）"
  fi
fi

step "3.1 10 个交付物校验（checksums.sha256）"
if [[ "$DRY_RUN" == "1" ]]; then
  printf '  [dry-run] 会用 checksums.sha256 校验 8 个数据文件 + bundles/ 里 2 个发布 bundle\n'
else
  tmp_list="$(mktemp)"
  rewrite_paths "${BUNDLE_DIR}/checksums.sha256" "$tmp_list"
  t0=$(date +%s)
  if [[ "$FAST" == "1" && -f "${BUNDLE_DIR}/sizes.tsv" ]]; then
    tmp_sizes="$(mktemp)"; rewrite_paths "${BUNDLE_DIR}/sizes.tsv" "$tmp_sizes"
    bad=0
    while IFS=$'\t' read -r path bytes; do
      [[ -z "${path:-}" || "$path" == \#* ]] && continue
      actual="$(stat -c %s "$path" 2>/dev/null || echo missing)"
      if [[ "$actual" != "$bytes" ]]; then printf '  [FAIL] 尺寸不符 %s（期望 %s 实际 %s）\n' "$path" "$bytes" "$actual"; bad=1; fi
    done < "$tmp_sizes"
    [[ "$bad" == "0" ]] && ok "--fast：$(grep -c $'\t' "$tmp_sizes") 个文件尺寸全部一致（未算 sha256）" || fail "--fast 尺寸校验有差异"
    rm -f "$tmp_sizes"
  else
    if (cd "$BUNDLE_DIR" && sha256sum -c "$tmp_list" > "$tmp_checksums_out" 2>&1); then
      ok "$(grep -c ': OK$' "$tmp_checksums_out") 个交付物 sha256 全部一致（$(human_elapsed $(( $(date +%s) - t0 )))）"
    else
      fail "校验失败，前几行差异："; grep -v ': OK$' "$tmp_checksums_out" | head -5 | sed 's/^/         /'
    fi
  fi
  rm -f "$tmp_list"
fi
if [[ "$FAIL" != "0" ]]; then summary_block; exit 11; fi

# ==============================================================================
# 数据属主（= 容器内运行 uid，compose 的 user:）在解包之后就能确定了；后面的
# 状态目录/密钥/受管配置都要按它归一属主（真 root 安装时它们默认是 root:root）。
owner_uid="$(stat -c '%u' "${DATA_ROOT}/index-v3-v2" 2>/dev/null || stat -c '%u' "$DATA_ROOT" 2>/dev/null || echo "$(id -u)")"
owner_gid="$(stat -c '%g' "${DATA_ROOT}/index-v3-v2" 2>/dev/null || stat -c '%g' "$DATA_ROOT" 2>/dev/null || echo "$(id -g)")"

step "4. 状态目录（$STATE_DIR）"
if [[ "$DRY_RUN" == "1" ]]; then
  printf '  [dry-run] 会创建 %s（0700，属主 %s:%s）\n' "$STATE_DIR" "$owner_uid" "$owner_gid"
else
  mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR" \
    && ok "状态目录就位（0700）：admin 账号库 / 密钥 / 首启口令 / 访问日志都落在这里" \
    || die 12 "无法创建 $STATE_DIR"
  normalize_owner "$DATA_ROOT"
  normalize_owner "$STATE_DIR"
  printf '  属主归一（容器内 uid=%s）：数据根=%s 状态目录=%s\n' \
    "${owner_uid}:${owner_gid}" "$(stat -c '%u:%g' "$DATA_ROOT")" "$(stat -c '%u:%g' "$STATE_DIR")"
fi

# ==============================================================================
step "5. 载入镜像"
if docker image inspect "$IMAGE_TAG" >/dev/null 2>&1 && [[ "${MIROTHINKER_SITE_FORCE_LOAD:-0}" != "1" ]]; then
  ok "镜像 ${IMAGE_TAG} 已在本地（$(docker image inspect -f '{{.Id}}' "$IMAGE_TAG" | cut -c1-19)…），跳过 load（要强制重载：MIROTHINKER_SITE_FORCE_LOAD=1）"
elif [[ "$DRY_RUN" == "1" ]]; then
  printf '  [dry-run] 会 docker load -i %s\n' "$IMAGE_TGZ"
else
  t0=$(date +%s)
  if docker load -i "${BUNDLE_DIR}/${IMAGE_TGZ}" > "$tmp_load_out" 2>&1; then
    image_id="$(docker image inspect -f '{{.Id}}' "$IMAGE_TAG" 2>/dev/null | cut -c1-19)"
    ok "docker load 完成（$(human_elapsed $(( $(date +%s) - t0 )))：$(tail -1 "$tmp_load_out" | head -c 80)… id=${image_id}…）"
  else
    die 12 "docker load 失败：$(tail -3 "$tmp_load_out" | head -c 300)"
  fi
fi

# ==============================================================================
step "6. 现场配置（.env / PG 凭据 / 4 个密钥）"
if [[ "$DRY_RUN" == "1" ]]; then
  printf '  [dry-run] 会写 %s（uid:gid=%s:%s，端口 %s，路径见上）\n' "$ENV_FILE" "$owner_uid" "$owner_gid" "$PORT"
  printf '  [dry-run] 会生成 %s（随机口令，0600），并检查 secrets/ 下 4 个密钥\n' "$PG_ENV_FILE"
  check_overrides
else
  cat > "$ENV_FILE" <<ENVEOF
# 由 install-site.sh 生成（$(date -Is)）。改完重跑 installer 或 docker compose up -d 生效。
MIROTHINKER_DATA_ROOT=${DATA_ROOT}
MIROTHINKER_STATE_DIR=${STATE_DIR}
MIROTHINKER_SECRETS_DIR=${SECRETS_DIR}
MIROTHINKER_MANAGED_DIR=${MANAGED_DIR}
MIROTHINKER_LOG_DIR=${BUNDLE_DIR}/state/logs
MIROTHINKER_UID=${owner_uid}
MIROTHINKER_GID=${owner_gid}
MIROTHINKER_HOST_PORT=${PORT}
MIROTHINKER_PG_ENV_FILE=${PG_ENV_FILE}
MIROTHINKER_PG_VOLUME=${PG_VOLUME}
MIROTHINKER_IMAGE=${IMAGE_TAG}
MIROTHINKER_COMMAND_FILE=${BUNDLE_DIR}/${CMD_OVERRIDE_NAME}
MIROTHINKER_ENTRYPOINT_FILE=${BUNDLE_DIR}/${ENTRYPOINT_OVERRIDE_NAME}
ENVEOF
  chmod 600 "$ENV_FILE"
  ok "写入 ${ENV_FILE}（uid:gid=${owner_uid}:${owner_gid} 取自数据属主；端口 ${PORT}）"

  mkdir -p "$SECRETS_DIR" "$MANAGED_DIR" "${BUNDLE_DIR}/state/logs" 2>/dev/null
  check_overrides
  # 真 root 安装：.env 与 secrets/ 里后补的密钥都是 root:root。容器不读 .env，但
  # **读 secrets/**；.env 则要留给操作者（sudo 之外的 docker compose 也要能读）。
  normalize_owner "$SECRETS_DIR"
  normalize_owner "$MANAGED_DIR"
  normalize_owner "${BUNDLE_DIR}/state/logs"
  if [[ "$(id -u)" == "0" && -n "${SUDO_UID:-}" ]]; then
    chown "${SUDO_UID}:${SUDO_GID:-$SUDO_UID}" "$ENV_FILE" 2>/dev/null
  fi
  # 预置受管配置（端点/档位/采集窗口，非机密）——已存在则不动，避免覆盖现场在页面上的改动
  if [[ ! -s "${MANAGED_DIR}/settings.json" && -s "${BUNDLE_DIR}/state/config-managed/settings.json" ]]; then
    cp "${BUNDLE_DIR}/state/config-managed/settings.json" "${MANAGED_DIR}/settings.json"
    ok "预置受管配置已就位（端点/档位/窗口；现场无需编辑）"
  elif [[ -s "${MANAGED_DIR}/settings.json" ]]; then
    ok "受管配置已存在（保留现场版本，不覆盖）"
  else
    warn "交付包里没有预置受管配置：chat LLM 档位会退回默认（gemma4），放 .deepseek_api_key 也不够用"
  fi
  if [[ ! -s "$PG_ENV_FILE" ]]; then
    ( umask 077; printf 'POSTGRES_USER=miroflow\nPOSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)" > "$PG_ENV_FILE" )
    ok "生成 PG 凭据 ${PG_ENV_FILE}（随机口令，0600；已存在则不动）"
  else
    ok "PG 凭据已存在（保留）：${PG_ENV_FILE}"
  fi
  chmod 600 "$PG_ENV_FILE" 2>/dev/null
  if [[ -f "${BUNDLE_DIR}/secrets.example/postgres.env" && ! -f "${BUNDLE_DIR}/secrets.example/README.txt" ]]; then
    printf '把 4 个密钥文件放进 %s（文件名必须一致，0600）：\n  .deepseek_api_key  .bocha_api_key  .serper_api_key  .sglang_api_key\n' \
      "$SECRETS_DIR" > "${SECRETS_DIR}/README.txt"
  fi
fi

# 密钥校验：必须是**普通文件且非空**。
# 特别处理一个实测踩过的坑：docker 的 bind mount 在源文件缺失时会**建一个同名目录**，
# 之后"后补 key"就变成无法覆盖的目录 —— 这里主动识别并修复（rmdir + 建空占位文件）。
missing_keys=()
for key in .deepseek_api_key .bocha_api_key .serper_api_key .sglang_api_key; do
  path="${SECRETS_DIR}/${key}"
  if [[ -d "$path" ]]; then
    rmdir "$path" 2>/dev/null \
      && warn "${key} 被 docker 建成了目录（源文件曾缺失）；已删除，改放普通文件" \
      || warn "${key} 是目录且非空，无法自动处理：请手动 rm -rf '$path' 后放普通文件"
    path_ok=0
  elif [[ -f "$path" && -s "$path" ]]; then
    path_ok=1
  elif [[ -e "$path" ]]; then
    warn "${key} 存在但是空文件 ⇒ 视为未配置（服务按"没有这个 key"降级）"
    path_ok=0
  else
    path_ok=0
  fi
  [[ "$path_ok" == "1" ]] || missing_keys+=("$path")
done
if [[ ${#missing_keys[@]} -gt 0 ]]; then
  if [[ "$ACCEPT_DEGRADED_KEYS" == "1" ]]; then
    warn "缺少 ${#missing_keys[@]} 个密钥文件（--accept-degraded-keys：继续，但相应能力会降级）"
  else
  fail "缺少 ${#missing_keys[@]} 个密钥文件（服务会起来但采集/问答会降级；**不允许**半配置上栈）"
  printf '         现场请创建（0600，内容为各自的 API key）：\n'
  printf '           %s\n' "${missing_keys[@]}"
  printf '         命令模板：\n'
  printf '           sudo install -m 600 /dev/stdin %s <<< "<你的key>"\n' "${missing_keys[0]}"
  printf '         也可先只放 .sglang_api_key + .deepseek_api_key 让问答可用，其余走 /admin 密钥页。\n'
  die 12 "密钥不齐：补齐后重跑本脚本（幂等；确实要降级安装：--accept-degraded-keys）"
  fi
  degraded_keys=()
  for key in .deepseek_api_key .bocha_api_key .serper_api_key .sglang_api_key; do
    [[ -f "${SECRETS_DIR}/${key}" && -s "${SECRETS_DIR}/${key}" ]] && continue
    degraded_keys+=("${key}")
    # 放一个空的 0600 占位文件：compose 的密钥挂载设了 create_host_path:false，
    # 没有文件会直接失败；空文件等价于"没有这个 key"（服务侧按未配置降级），
    # 且之后把真 key 写进同一个路径即可（普通文件，不会变成目录）。
    if [[ "$DRY_RUN" != "1" && ! -e "${SECRETS_DIR}/${key}" ]]; then
      ( umask 077; : > "${SECRETS_DIR}/${key}" )
    fi
  done
  warn "缺的密钥：${degraded_keys[*]}（各自影响：.sglang_api_key=语义检索, .deepseek_api_key=成文答案, .bocha/.serper=联网补充）"
fi
key_modes=""
key_mode_warn=0
for key in .deepseek_api_key .bocha_api_key .serper_api_key .sglang_api_key; do
  [[ -s "${SECRETS_DIR}/${key}" ]] || continue          # 缺的 key 由下面的缺失清单负责
  mode="$(stat -L -c %a "${SECRETS_DIR}/${key}")"
  key_modes="${key_modes}${key}=${mode} "
  [[ "$mode" != "600" ]] && key_mode_warn=1
done
present=$(( 4 - ${#missing_keys[@]} ))
if [[ "$present" == "4" ]]; then
  ok "4 个密钥就位且非空（内容未打印；权限：${key_modes}）"
else
  warn "就位的密钥 ${present}/4（内容未打印；权限：${key_modes}）"
fi
if [[ "$key_mode_warn" == "1" ]]; then
  warn "有密钥文件不是 0600（同机器其它用户可读）：chmod 600 ${SECRETS_DIR}/.*_api_key"
fi
if [[ "$DRY_RUN" == "1" ]]; then summary_block; echo; echo "--dry-run 结束：以上检查通过，未做任何落地改动"; exit 0; fi

# ==============================================================================
step "7. 起服务（docker compose，容器内固定 18188 → 宿主 ${PORT}）"
if [[ "$DO_UP" != "1" ]]; then
  warn "--no-up：按要求停在起服务之前（数据面/状态目录/配置/密钥检查都已就位）"
  cat <<DONE

================ 安装（--no-up）完成 ================
  数据/状态：   ${DATA_ROOT}
                ${STATE_DIR}（首启口令在 admin-initial-password.txt）
  起服务：      cd ${BUNDLE_DIR} && docker compose up -d
  健康检查：    http://127.0.0.1:${PORT}/api/health（启动相位实测 ≈276 s）
  验收：        cd ${BUNDLE_DIR} && docker compose exec -T app mirothinker-verify
===================================================
DONE
  summary_block
  [[ "$FAIL" == "0" ]] && exit 0 || exit 14
fi
cd "$BUNDLE_DIR" || die 13 "无法进入 $BUNDLE_DIR"
t0=$(date +%s)
if ! docker compose up -d; then
  fail "docker compose up -d 失败：$BUNDLE_DIR（看上面的输出）"
  docker compose logs --tail 30 app 2>/dev/null | sed 's/^/         /'
  die 13 "compose 启动失败"
fi
ok "容器已创建：$(docker compose ps --format '{{.Service}}={{.Status}}' | tr '\n' ' ')"

printf '  等待健康（启动相位实测 ≈276 s；端口在相位结束前不会 bind，属正常）…\n'
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
health_ok=0
last_note=0
while (( $(date +%s) < deadline )); do
  if [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null)" == "200" ]]; then
    health_ok=1; break
  fi
  now=$(date +%s); elapsed=$(( now - t0 ))
  if (( elapsed - last_note >= 30 )); then
    printf '    …已等 %s（容器状态：%s）\n' "$(human_elapsed "$elapsed")" "$(docker compose ps --format '{{.Status}}' | head -1)"
    last_note=$elapsed
  fi
  sleep 5
done
boot_seconds=$(( $(date +%s) - t0 ))
if [[ "$health_ok" == "1" ]]; then
  ok "健康检查通过：boot=${boot_seconds}s（http://127.0.0.1:${PORT}/api/health）"
else
  fail "在 ${HEALTH_TIMEOUT}s 内未健康（boot 已耗 $(human_elapsed "$boot_seconds")）"
  docker compose logs --tail 40 app 2>/dev/null | sed 's/^/         /'
  die 13 "服务未健康"
fi

# ==============================================================================
step "8. 验收"
if docker compose exec -T app mirothinker-verify; then
  ok "容器内验收探针（mirothinker-verify）全通"
else
  fail "mirothinker-verify 有红点（见上）"
fi

cat <<DONE

================ 安装完成 ================
  问答页：      http://<本机IP>:${PORT}/chat
  管理台：      http://<本机IP>:${PORT}/main
  首启口令：    ${STATE_DIR}/admin-initial-password.txt   （登录后立即改密）
  状态/日志：   ${STATE_DIR}   与  ${BUNDLE_DIR}/state/logs
  采集库：      docker compose -f ${BUNDLE_DIR}/compose.yaml exec -T db psql -U miroflow -d miroflow_collection_v1
  ⚠ 先做 /admin 配置再跑 replay 门：首装时受管配置为空，答案会走降级渲染路径
     ⇒ replay 门会红在 G1_framing（第 3 轮首句是"以下为基于本地数据的简要信息"）。
     这不是安装故障：先在 http://<本机IP>:${PORT}/admin 配好 chat LLM 选档 + 密钥，门即 7/7。
  验收（replay 门，7 组会话）：
      cd ${BUNDLE_DIR} && docker compose exec -T app mirothinker-replay --out-dir /tmp/accept
  停止/启动：
      cd ${BUNDLE_DIR} && docker compose down      # / up -d（数据与状态在宿主，不丢）
  配置只剩密钥这一步：见 ${BUNDLE_DIR}/CONFIG-GUIDE.md（甲方运维版）
  备份采集库（pg_dump）与常见故障处置：见 ${BUNDLE_DIR}/README.md
==========================================
DONE

summary_block
[[ "$FAIL" == "0" ]] && exit 0 || exit 14
