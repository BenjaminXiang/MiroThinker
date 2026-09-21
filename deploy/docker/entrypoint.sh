#!/usr/bin/env bash
# Canonical V2 容器入口：只做「容器边界该做的事」，然后原样交给冻结的生产启动脚本。
#
# 这里有意的分工：
#   * 启动逻辑（哪个命令文件、哪些参数、哪个端口）= 冻结产物，本脚本一行都不复制、
#     不重写，直接 exec deploy/start-canonical-v2.sh（生产 systemd 用的同一个脚本）；
#   * 本脚本只负责容器引入的差异：uid/权限预检、HOME 可写、把「看起来像缺文件、
#     其实是权限」的失败提前翻译成人话。
#
# 退出码：预检失败 → 78（EX_CONFIG），便于 compose/运维一眼区分「配置问题」与「服务崩溃」。
#
# 可选环境变量：
#   MIROTHINKER_SKIP_PREFLIGHT=1            跳过全部预检（自己看服务原生报错时用）
#   MIROTHINKER_ENTRYPOINT_ENV_RECEIPT=1    只打印"凭据收据"（名字 + 是否已设置）后退出，
#                                           不启动服务（现场排障：key 到底喂到哪几个槽位）
#   MIROTHINKER_EMBEDDING_KEY_FILE=<path>   嵌入 key 文件位置（默认 /opt/mirothinker/.sglang_api_key，
#                                           即 compose 的挂载点；测试/排障时可覆盖）
#   MIROTHINKER_MIGRATE_WAIT_SECONDS=<n>    采集库迁移的有界等待秒数（默认 120）

set -uo pipefail

DATA_ROOT="/var/tmp/mirothinker-data-v2"
PACK_DIR="${DATA_ROOT}/serving-pack-run16-readerbound"
INDEX_ROOT="${DATA_ROOT}/index-v3-v2"
MANUAL_RECALL_DIR="${DATA_ROOT}/manual-recall-v1"
STATE_DIR="/var/tmp/mirothinker-canonical-v2-s12f"
REPO_LINK="/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation"
START_SCRIPT="${REPO_LINK}/deploy/start-canonical-v2.sh"

log() { printf '[entrypoint] %s\n' "$*"; }
fail() { printf '[entrypoint] 预检失败：%s\n' "$*" >&2; exit 78; }

log "effective identity: uid=$(id -u) gid=$(id -g) user=$(id -un 2>/dev/null || echo '<no passwd entry>')"
log "repo=$START_SCRIPT data_root=$DATA_ROOT state=$STATE_DIR"

# --- 0. HOME 必须可写：uv / python / chromium 都会写 HOME ---------------------
if [[ -z "${HOME:-}" || ! -w "${HOME:-/nonexistent}" ]]; then
  export HOME=/var/tmp/mirothinker-home
  mkdir -p "$HOME" 2>/dev/null || true
  log "HOME 不可写，改用 $HOME"
fi
# uv 也要一个可写的缓存目录（运行期全程 offline/frozen，这里只是别让它报
# "Failed to initialize cache … Permission denied"）。HOME 不可写时退到临时目录。
export UV_CACHE_DIR="${UV_CACHE_DIR:-${HOME}/.cache/uv}"
if ! mkdir -p "$UV_CACHE_DIR" 2>/dev/null || [[ ! -w "$UV_CACHE_DIR" ]]; then
  export UV_CACHE_DIR="$(mktemp -d)/uv-cache"
  mkdir -p "$UV_CACHE_DIR"
  log "uv 缓存目录不可写，改用 $UV_CACHE_DIR"
fi
log "HOME=$HOME UV_CACHE_DIR=$UV_CACHE_DIR"

# --- 1. 冻结路径必须存在 -------------------------------------------------------
# MIROTHINKER_SKIP_PREFLIGHT=1 关掉本脚本的全部预检（现场要自己看服务原生的报错时用）。
if [[ "${MIROTHINKER_SKIP_PREFLIGHT:-0}" != "1" ]]; then
  for path in "$PACK_DIR" "$INDEX_ROOT" "$STATE_DIR"; do
    [[ -e "$path" ]] || fail "缺少 $path —— 数据面/状态目录没有挂载进来（检查 compose 的 volumes）"
  done

  # --- 2. 冻结路径必须可读（否则报错会伪装成「文件缺失或损坏」）----------------
  # 只读性检查用「能否 stat 到具体文件」表达：目录 mode 0700 且属主不是本 uid 时，
  # stat/读都可能失败，而服务侧的报错文案是 "…is missing or unsafe" —— 那是权限，
  # 不是缺文件。这里先点明。
  for probe in \
      "$PACK_DIR/manifest.json" \
      "$PACK_DIR/lookup.sqlite3" \
      "$INDEX_ROOT/.canonical-v2-isolated-index-target.json" \
      "$INDEX_ROOT/lookup.sqlite3"; do
    if [[ ! -f "$probe" ]]; then
      fail "读不到 ${probe}（存在性/权限）：若宿主机上确实有这个文件，就是 uid 不匹配 ——
      容器内 uid=$(id -u)，而该文件的属主是 $(stat -c '%u:%g' "$(dirname "$probe")" 2>/dev/null || echo '?')（父目录）。
      一行修复：在 compose 里设 user: \"\${MIROTHINKER_UID}:${MIROTHINKER_GID:-}\" = 数据属主的 uid:gid，
      或先在宿主机 chown 数据目录到容器用户。"
    fi
    [[ -r "$probe" ]] || fail "无读权限：$probe（uid 不匹配问题，见上）"
  done

  # --- 3. 状态目录必须可写（管理面账号库 / 会话密钥 / 首启口令都落在这里）------
  # 应用侧对不可写状态目录只有一行 warning 且管理面直接不可用；容器把它变成显式失败。
  mkdir -p "$STATE_DIR" 2>/dev/null || true
  probe_file="${STATE_DIR}/.entrypoint-write-probe"
  if ! touch "$probe_file" 2>/dev/null; then
    fail "状态目录不可写：$STATE_DIR（容器内 uid=$(id -u)）
    诊断：宿主上该目录属主 $(stat -c '%u:%g' "$STATE_DIR" 2>/dev/null || echo '?')，数据根属主 $(stat -c '%u:%g' "$DATA_ROOT" 2>/dev/null || echo '?') —— 容器要按**数据属主**那个 uid 跑（compose 的 user: 取 .env 里的 MIROTHINKER_UID/MIROTHINKER_GID）。
    一行修复（在宿主机、交付包目录里执行）：
      sudo ./install-site.sh        # 幂等；会把数据根 / 状态目录 / 密钥归一给数据属主
    或： sudo chown -R $(stat -c '%u' "$DATA_ROOT" 2>/dev/null || echo '<数据属主 uid>') "$STATE_DIR"
    注意：**不要**因为这里显示 root 就把 compose 的 user: 改成 0:0 —— 那是把服务跑成 root，既不对也不安全。
    若确认要带病启动：设 MIROTHINKER_SKIP_PREFLIGHT=1。"
  fi
  rm -f "$probe_file"

  # --- 4. 服务包父目录可写性：只影响性能，不影响正确性（服务侧只 warning）----
  if touch "${DATA_ROOT}/.entrypoint-write-probe" 2>/dev/null; then
    rm -f "${DATA_ROOT}/.entrypoint-write-probe"
    log "服务包父目录可写：本次启动会写 ${PACK_DIR}.mount-receipt.json（下次启动走 receipt 快路径）"
  else
    log "注意：${DATA_ROOT} 不可写（例如只读挂载）—— 服务会正常启动，健康检查照过；"
    if [[ -n "${CANONICAL_V2_SERVING_RECEIPT_PATH:-}" ]]; then
      log "      已指定 CANONICAL_V2_SERVING_RECEIPT_PATH=${CANONICAL_V2_SERVING_RECEIPT_PATH}，receipt 快路径不受影响。"
    else
      log "      未指定 CANONICAL_V2_SERVING_RECEIPT_PATH ⇒ 写 receipt 失败，每次启动都会重新全量哈希"
      log "      服务包与索引（本机实测多花约 4 s/次）。要拿回快路径：让该目录可写，或指定该变量。"
    fi
  fi
fi

# --- 5. 嵌入凭据投影：一个 key 文件喂两个槽位 ---------------------------------
# 现场（文件路线）只放 secrets/.sglang_api_key，由 compose 挂到容器内
# /opt/mirothinker/.sglang_api_key。自有端点（v1 槽位）由 load_local_api_key()
# **直接读文件**，不需要环境变量；但候选（第三方网关）嵌入 bundle 只认它自己声明的
# 那个槽位（knowledge_build_isolated._GATEWAY_EMBEDDING_API_KEY_ENV，只读环境变量）。
# 不做投影的话：文件路线的站点切到 v2 后，候选嵌入路由**拿不到任何凭据**，而向量道是
# fail-open ⇒ 静默降级（答案照出、语义检索那条道死掉），最难现场排查的一类故障。
#
# 优先级（高 → 低）：显式环境变量 > 管理页写入的受管凭据 > 这个 key 文件。
#   显式设置     ⇒ 一个字节都不动（service unit 仍是权威）；
#   受管凭据里有 ⇒ 留给服务启动时投影（它会同时填 SGLANG_API_KEY 与候选槽位）；
#   否则文件非空 ⇒ 导出候选槽位（v1 槽位保持原样：它本来就按文件读）。
# 本段只打印字段名与"是否已设置"，从不打印值。
EMBEDDING_KEY_FILE="${MIROTHINKER_EMBEDDING_KEY_FILE:-/opt/mirothinker/.sglang_api_key}"
MANAGED_SECRETS_FILE="${CANONICAL_V2_MANAGED_SECRETS:-/opt/mirothinker/config/managed/secrets.json}"
GATEWAY_EMBEDDING_KEY_ENV="CANONICAL_V2_EMBEDDING_API_KEY"

# 受管凭据（管理页写的 secrets.json）里有没有嵌入 key。
# 有 ⇒ 服务启动时会自己投影到两个槽位，这里就不该抢先把候选槽位钉死
# （否则服务侧"已存在即跳过"，管理页换的 key 在候选槽位反而不生效）。
# 只看退出码，不打印任何字段值。
managed_has_embedding_key() {
  [[ -s "$MANAGED_SECRETS_FILE" ]] || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  python3 - "$MANAGED_SECRETS_FILE" >/dev/null 2>&1 <<'PY'
import json
import sys

try:
    document = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    raise SystemExit(1)
value = document.get("secrets") if isinstance(document, dict) else None
value = value.get("embedding.api_key") if isinstance(value, dict) else None
raise SystemExit(0 if isinstance(value, str) and value.strip() else 1)
PY
}

embedding_key_value=""
if [[ -s "$EMBEDDING_KEY_FILE" && -r "$EMBEDDING_KEY_FILE" ]]; then
  embedding_key_value="$(<"$EMBEDDING_KEY_FILE")"
  # 与读侧的 .strip() 对齐：去掉首尾空白（只删首尾，不动中间）
  embedding_key_value="${embedding_key_value#"${embedding_key_value%%[![:space:]]*}"}"
  embedding_key_value="${embedding_key_value%"${embedding_key_value##*[![:space:]]}"}"
fi

if [[ -n "${!GATEWAY_EMBEDDING_KEY_ENV:-}" ]]; then
  log "嵌入凭据投影：${GATEWAY_EMBEDDING_KEY_ENV} 已显式设置 —— 不动（环境变量优先）"
elif managed_has_embedding_key; then
  log "嵌入凭据投影：受管凭据里有 embedding.api_key —— 留给服务启动时投影到 SGLANG_API_KEY + ${GATEWAY_EMBEDDING_KEY_ENV}"
elif [[ -n "$embedding_key_value" ]]; then
  export "${GATEWAY_EMBEDDING_KEY_ENV}=${embedding_key_value}"
  log "嵌入凭据投影：key 文件 → ${GATEWAY_EMBEDDING_KEY_ENV}（已设置；v1 槽位 SGLANG_API_KEY 仍按文件直读）"
else
  log "嵌入凭据投影：没有可用的嵌入凭据（${GATEWAY_EMBEDDING_KEY_ENV} 空、受管凭据里没有 embedding.api_key、key 文件 ${EMBEDDING_KEY_FILE} 不存在/为空）"
  log "      ⇒ 自有端点（v1 槽位）与候选网关（${GATEWAY_EMBEDDING_KEY_ENV}）都拿不到凭据；向量道会降级，服务照常启动"
fi

# --- 6. 凭据收据（现场排障；只报名字与是否已设置） ---------------------------
# MIROTHINKER_ENTRYPOINT_ENV_RECEIPT=1 ⇒ 打印收据后退出，不启动服务。
# 收据由**子进程**打印：只有真正 export 出去的变量才会出现在里面。
if [[ "${MIROTHINKER_ENTRYPOINT_ENV_RECEIPT:-0}" == "1" ]]; then
  log "凭据收据（只报名字与是否已设置；从不打印值）："
  EMBEDDING_KEY_FILE="$EMBEDDING_KEY_FILE" GATEWAY_ENV="$GATEWAY_EMBEDDING_KEY_ENV" /bin/sh -c '
    for name in SGLANG_API_KEY OPENAI_API_KEY API_KEY "$GATEWAY_ENV"; do
      eval "value=\${$name:-}"
      if [ -n "$value" ]; then
        printf "[entrypoint]   环境槽位 %s=已设置\n" "$name"
      else
        printf "[entrypoint]   环境槽位 %s=空\n" "$name"
      fi
    done
    if [ -s "$EMBEDDING_KEY_FILE" ]; then
      printf "[entrypoint]   key 文件 %s=已设置（v1 槽位按文件直读，不需要环境变量）\n" "$EMBEDDING_KEY_FILE"
    else
      printf "[entrypoint]   key 文件 %s=缺失/空\n" "$EMBEDDING_KEY_FILE"
    fi
  '
  exit 0
fi

# --- 7. 手工召回道目录：冻结命令文件指向它，缺了只是降级，这里顺手补齐 --------
if [[ ! -d "$MANUAL_RECALL_DIR" ]]; then
  mkdir -p "$MANUAL_RECALL_DIR" 2>/dev/null \
    && log "已创建 $MANUAL_RECALL_DIR" \
    || log "注意：$MANUAL_RECALL_DIR 不存在且创建失败（数据根只读），手工召回道将不可用"
fi

# --- 8. 采集库（PostgreSQL）DSN + 幂等迁移 -----------------------------------
# 顺序与语义（有意为之）：
#   * DSN 优先用显式 DATABASE_URL；否则由 POSTGRES_*（compose 的 env_file: secrets/postgres.env）组装；
#   * 组装好的 DSN 只经 shell 变量传递，**从不打印**（migrate.py 出错时也只打掩码）；
#   * 迁移**有界**（默认 120 s）且失败只降级：PG 不可用 ≠ 服务不可用（/chat 不依赖 PG，
#     采集面本来就设计成 503 + 导航隐藏）。
MIGRATE=/usr/local/bin/mirothinker-migrate
if [[ -z "${DATABASE_URL:-}" && -n "${POSTGRES_USER:-}" && -n "${POSTGRES_PASSWORD:-}" ]]; then
  if assembled="$("$MIGRATE" --print-dsn 2>/dev/null)" && [[ -n "$assembled" ]]; then
    DATABASE_URL="$assembled"
    export MIROTHINKER_DSN_ORIGIN="POSTGRES_*（compose env_file）"
    log "采集库 DSN 由 POSTGRES_* 组装：user=${POSTGRES_USER} host=${POSTGRES_HOST:-db} db=${POSTGRES_DB:-miroflow_collection_v1}"
  fi
fi
if [[ -n "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL
  migrate_log="/tmp/mirothinker-migrate.log"
  if "$MIGRATE" --wait "${MIROTHINKER_MIGRATE_WAIT_SECONDS:-120}" >"$migrate_log" 2>&1; then
    log "采集库迁移就绪：$(tail -n 1 "$migrate_log")"
  else
    log "注意：采集库迁移未完成 —— 服务照常启动（/chat 不受影响），采集面（/seeds /upload /jobs）将 503。"
    sed 's/^/  [migrate] /' "$migrate_log" | head -n 20
  fi
  unset migrate_log assembled
else
  log "采集库未配置（无 DATABASE_URL，也没有 POSTGRES_USER/POSTGRES_PASSWORD）"
  log "      ⇒ 采集面保持现状：503 + 导航隐藏（这是设计行为，不是故障）"
fi
unset MIGRATE

log "预检通过，交给冻结生产启动脚本：$START_SCRIPT"
exec "$START_SCRIPT"
