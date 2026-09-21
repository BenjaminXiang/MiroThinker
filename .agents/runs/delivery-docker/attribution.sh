#!/usr/bin/env bash
# Task B：启动耗时归因（同一台机器、同一个数据根、背靠背、页缓存预热）。
#
#   attribution.sh warm        预热页缓存（把数据面读进 page cache）
#   attribution.sh bare        裸机 boot（端口 18498；代码=本 worktree；receipt/计时落 scratch）
#   attribution.sh container   容器 boot（端口 18298；**live 数据根以 :ro 挂进冻结路径**）
#   attribution.sh phases      把两侧的相位 JSON 汇总成对照表
#   attribution.sh load        记录当前负载与其它重活（排除干扰用）
#
# 关键设计（为了"同条件"）：
#   * 两侧读**同一个**宿主目录 /var/tmp/mirothinker-data-v2（容器 :ro 挂载 ⇒ 同一批 inode、
#     同一份页缓存；裸机直接读同一路径）；
#   * 两侧都把 mount-receipt 重定向到 /var/tmp/mirothinker-bare-state/（CANONICAL_V2_SERVING_RECEIPT_PATH），
#     并且**预热同一份 receipt**（从活线 receipt 复制，pack_dir 相同故可绑定）⇒ 都走快路径，
#     也保证不往活线数据目录写任何东西；
#   * 两侧都打开 CANONICAL_V2_SERVING_TIMING_PATH，逐相位落 JSONL；
#   * 启动前各自 warm，启动期间不做别的重活。

set -uo pipefail

PHASE="${1:-phases}"
WORKTREE="/home/longxiang/MiroThinker/.worktrees/delivery-docker"
DATA="/var/tmp/mirothinker-data-v2"
BARE_STATE="/var/tmp/mirothinker-bare-state"
KIT="/var/tmp/mirothinker-docker-kit"
OUT="/var/tmp/mirothinker-docker-logs"
IMAGE="mirothinker-serving:v1"
BARE_PORT=18498
CONT_PORT=18298
LIVE_PID=519941

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }

warm_cache() {
  log "预热页缓存：读 6.5 GB 数据面到 /dev/null"
  local started; started=$(date +%s)
  cat "$DATA/serving-pack-run16-readerbound/relationships.json" \
      "$DATA/serving-pack-run16-readerbound/lookup.sqlite3" \
      "$DATA/serving-pack-run16-readerbound/manifest.json" \
      "$DATA/index-v3-v2/vector_matrix.npz" > /dev/null
  log "预热完成：$(( $(date +%s) - started ))s"
}

seed_receipt() {
  mkdir -p "$BARE_STATE"
  if [[ ! -f "$BARE_STATE/serving-pack.mount-receipt.json" ]]; then
    cp "$DATA/serving-pack-run16-readerbound.mount-receipt.json" \
       "$BARE_STATE/serving-pack.mount-receipt.json" 2>/dev/null \
      && log "已从活线 receipt 播种快路径收据（pack_dir 相同）" \
      || log "没有活线 receipt 可播种 ⇒ 本次会走全量校验（记录在案）"
  fi
}

wait_http() {
  local port="$1" budget="$2" started; started=$(date +%s)
  while (( $(date +%s) - started < budget )); do
    if [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${port}/api/health")" == "200" ]]; then
      echo $(( $(date +%s) - started )); return 0
    fi
    sleep 5
  done
  echo -1; return 1
}

case "$PHASE" in
  warm) warm_cache ;;

  load)
    { echo "### load snapshot $(date -Is)"; uptime
      echo "-- top CPU consumers:"; ps -eo pcpu,pid,etime,comm --sort=-pcpu | head -6
      echo "-- live service:"; ps -o pid,rss,etime -p "$LIVE_PID" | tail -1
    } | tee -a "$OUT/attribution-load.log" ;;

  bare)
    warm_cache; seed_receipt
    : > "$BARE_STATE/boot-timing.jsonl"
    log "裸机 boot：端口 $BARE_PORT，代码 $WORKTREE，state $BARE_STATE"
    uptime | tee -a "$OUT/attribution-load.log"
    nohup bash -c "cd '$WORKTREE' && exec env \$(cat .agents/runs/delivery-docker/bare-metal-command-18498.sh)" \
      > "$OUT/attribution-bare.log" 2>&1 &
    bare_shell_pid=$!
    sleep 2
    # 真正跑 python 的那个进程（uv → python），用于收尾
    bare_pid="$(pgrep -f "serve_s12e_port.py $BARE_PORT" | head -1)"
    log "裸机 pid=$bare_pid（wrapper=$bare_shell_pid）"
    seconds="$(wait_http "$BARE_PORT" 900)"
    log "裸机 boot_wall_clock=${seconds}s"
    echo "bare_seconds=$seconds" >> "$OUT/attribution-results.txt"
    sleep 5
    kill "$bare_pid" 2>/dev/null || true
    kill "$bare_shell_pid" 2>/dev/null || true
    sleep 5
    kill -9 "$bare_pid" 2>/dev/null || true
    log "裸机已停；活线仍在？$(ps -o pid= -p "$LIVE_PID" | tr -d ' ' || echo GONE)"
    ;;

  container)
    warm_cache; seed_receipt
    mkdir -p "$KIT/state/logs"
    log "容器 boot：端口 $CONT_PORT，live 数据根 :ro，receipt/计时走 $BARE_STATE"
    uptime | tee -a "$OUT/attribution-load.log"
    docker rm -f mirothinker-attrib 2>/dev/null >/dev/null
    docker run -d --name mirothinker-attrib --user 1004:1004 \
      -p "${CONT_PORT}:18188" \
      -v "${DATA}:/var/tmp/mirothinker-data-v2:ro" \
      -v "${BARE_STATE}:${BARE_STATE}" \
      -v "${BARE_STATE}/state:/var/tmp/mirothinker-canonical-v2-s12f" \
      -v "${KIT}/secrets/.deepseek_api_key:/opt/mirothinker/.deepseek_api_key:ro" \
      -v "${KIT}/secrets/.bocha_api_key:/opt/mirothinker/.bocha_api_key:ro" \
      -v "${KIT}/secrets/.serper_api_key:/opt/mirothinker/.serper_api_key:ro" \
      -v "${KIT}/secrets/.sglang_api_key:/opt/mirothinker/.sglang_api_key:ro" \
      -e MIROTHINKER_SKIP_PREFLIGHT=0 \
      -e CANONICAL_V2_SERVING_RECEIPT_PATH="${BARE_STATE}/serving-pack.mount-receipt.json" \
      -e CANONICAL_V2_SERVING_TIMING_PATH="${BARE_STATE}/boot-timing.jsonl" \
      "$IMAGE" >/dev/null
    seconds="$(wait_http "$CONT_PORT" 900)"
    log "容器 boot_wall_clock=${seconds}s"
    echo "container_seconds=$seconds" >> "$OUT/attribution-results.txt"
    docker logs mirothinker-attrib > "$OUT/attribution-container.log" 2>&1
    docker rm -f mirothinker-attrib >/dev/null 2>&1
    log "容器已停；活线仍在？$(ps -o pid= -p "$LIVE_PID" | tr -d ' ' || echo GONE)"
    ;;

  phases)
    /usr/bin/python3 - "$BARE_STATE/boot-timing.jsonl" "$OUT/attribution-phases.md" <<'PY'
import json, sys, collections
from pathlib import Path

source = Path(sys.argv[1])
out = Path(sys.argv[2])
rows = collections.defaultdict(list)
order = collections.defaultdict(list)
if source.is_file():
    for line in source.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        pid = item.get("pid")
        rows[pid].append(item)
lines = ["# 启动相位对照（CANONICAL_V2_SERVING_TIMING_PATH）", ""]
for pid, items in rows.items():
    lines.append(f"## pid {pid}（{len(items)} 步）")
    lines.append("")
    lines.append("| # | step | seconds | 备注 |")
    lines.append("|---|---|---|---|")
    total = 0.0
    for index, item in enumerate(items, start=1):
        seconds = item.get("seconds") or 0.0
        total += seconds
        extra = {k: v for k, v in item.items() if k not in {"name", "seconds", "pid", "thread", "at", "count"}}
        lines.append(f"| {index} | {item.get('name')} | {seconds:.3f} | {extra or ''} |")
    lines.append(f"\n小计（计入命名相位）：{total:.1f} s\n")
out.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines[:40]))
print(f"\n→ 全表写入 {out}")
PY
    ;;

  *) echo "usage: $0 {warm|load|bare|container|phases}" >&2; exit 2 ;;
esac
log "phase=${PHASE} 结束"
