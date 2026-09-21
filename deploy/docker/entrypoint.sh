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
    一行修复：user: \"$(stat -c '%u:%g' "$STATE_DIR" 2>/dev/null || echo '数据属主 uid:gid')\"，
    或宿主机 chown -R 该 uid "$STATE_DIR"。若确认要带病启动：设 MIROTHINKER_SKIP_PREFLIGHT=1。"
  fi
  rm -f "$probe_file"

  # --- 4. 服务包父目录可写性：只影响性能，不影响正确性（服务侧只 warning）----
  if touch "${DATA_ROOT}/.entrypoint-write-probe" 2>/dev/null; then
    rm -f "${DATA_ROOT}/.entrypoint-write-probe"
    log "服务包父目录可写：本次启动会写 ${PACK_DIR}.mount-receipt.json（下次启动走 receipt 快路径）"
  else
    log "注意：${DATA_ROOT} 不可写 —— 服务仍会正常启动，但无法写 mount-receipt，"
    log "      每次启动都会重新全量哈希服务包与索引。要拿到 receipt 快路径："
    log "      把该目录改成可写，或指定 CANONICAL_V2_SERVING_RECEIPT_PATH 到可写路径。"
  fi
fi

# --- 5. 手工召回道目录：冻结命令文件指向它，缺了只是降级，这里顺手补齐 --------
if [[ ! -d "$MANUAL_RECALL_DIR" ]]; then
  mkdir -p "$MANUAL_RECALL_DIR" 2>/dev/null \
    && log "已创建 $MANUAL_RECALL_DIR" \
    || log "注意：$MANUAL_RECALL_DIR 不存在且创建失败（数据根只读），手工召回道将不可用"
fi

log "预检通过，交给冻结生产启动脚本：$START_SCRIPT"
exec "$START_SCRIPT"
