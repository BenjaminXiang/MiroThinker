#!/usr/bin/env bash
# delivery-docker 演练驱动（证据可复现）。
#
# 三个阶段，互不干扰活线（18188 的 pid 519941 全程不动）：
#   rehearse.sh rw        主演练：compose 起容器（数据根可写）、跑全部探针 + replay 门
#   rehearse.sh ro        只读实验：数据根以 :ro 挂载，看启动是否失败 / 是否只 warning
#   rehearse.sh wronguid  权限实验：以非数据属主 uid 运行，抓「看起来像缺文件」的真实报错
#
# 端口：容器内固定 18188，宿主机发布 18298（避开活线 18188 与另一路演练 18299）。

set -uo pipefail

PHASE="${1:-rw}"
WORKTREE="/home/longxiang/MiroThinker/.worktrees/delivery-docker"
OUT="/var/tmp/mirothinker-docker-logs"
KIT="/var/tmp/mirothinker-docker-kit"
DATA="/var/tmp/mirothinker-docker-data-v2"
STATE="/var/tmp/mirothinker-docker-state-v1"
IMAGE="mirothinker-serving:v1"
RUN_UID=1004
RUN_GID=1004
PROJECT="mirothinker-docker-${PHASE}"
HOST_PORT="${MIROTHINKER_HOST_PORT:-18298}"
CONTAINER_IN_PORT=18188

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }

compose() {
  MIROTHINKER_IMAGE="$IMAGE" \
  MIROTHINKER_HOST_PORT="$HOST_PORT" \
  MIROTHINKER_DATA_ROOT="$DATA" \
  MIROTHINKER_STATE_DIR="$STATE" \
  MIROTHINKER_SECRETS_DIR="${KIT}/secrets" \
  MIROTHINKER_MANAGED_DIR="${KIT}/state/config-managed" \
  MIROTHINKER_LOG_DIR="${KIT}/state/logs" \
  MIROTHINKER_UID="$RUN_UID" \
  MIROTHINKER_GID="$RUN_GID" \
  docker compose -p "$PROJECT" -f "${WORKTREE}/deploy/docker/compose.yaml" "$@"
}

wait_health() {
  local deadline=$(( $(date +%s) + ${1:-900} ))
  while (( $(date +%s) < deadline )); do
    if [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${HOST_PORT}/api/health")" == "200" ]]; then
      return 0
    fi
    sleep 5
  done
  return 1
}

cleanup_project() {
  compose down --remove-orphans >/dev/null 2>&1 || true
  docker rm -f "mirothinker-${PHASE}-manual" >/dev/null 2>&1 || true
}

case "$PHASE" in
  rw)
    cleanup_project
    log "compose up（数据根可写，uid=${RUN_UID}:${RUN_GID}，宿主机端口 ${HOST_PORT}）"
    started="$(date +%s)"
    compose up -d
    log "容器已创建，等待端口 bind（启动相位 ≈291 s）…"
    if wait_health 900; then
      boot_seconds=$(( $(date +%s) - started ))
      log "健康检查通过：boot_wall_clock=${boot_seconds}s"
    else
      log "900 s 内未通过健康检查 —— 见 logs/container-${PHASE}.log"
      docker logs "mirothinker-docker-${PHASE}-app-1" > "${OUT}/container-rw.log" 2>&1 || true
      exit 1
    fi
    docker logs "mirothinker-docker-${PHASE}-app-1" > "${OUT}/container-rw.log" 2>&1 || true
    docker inspect -f '{{.State.StartedAt}} {{.State.Pid}}' "mirothinker-docker-${PHASE}-app-1"

    log "HTTP 探针（宿主机侧，发布端口 ${HOST_PORT}）"
    for path in /api/health /chat /main; do
      printf '  host  %-12s HTTP %s\n' "$path" \
        "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "http://127.0.0.1:${HOST_PORT}${path}")"
    done

    log "容器内验收探针 mirothinker-verify（含嵌入 200 + 4096 维）"
    compose exec -T app mirothinker-verify | tee "${OUT}/verify-${PHASE}.txt"

    log "内存占用（docker stats，cgroup 口径）"
    docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.MemPerc}} {{.CPUPerc}}' \
      | tee "${OUT}/stats-${PHASE}.txt"

    log "一条真实问题过 /api/chat/stream（容器内 127.0.0.1:${CONTAINER_IN_PORT}）"
    docker exec -i "mirothinker-docker-${PHASE}-app-1" /opt/mirothinker/.venv/bin/python - \
      "http://127.0.0.1:${CONTAINER_IN_PORT}" "介绍一下 国际先进技术应用推进中心（深圳）" \
      > "${OUT}/one-question.json" 2> "${OUT}/one-question.err" <<'PY'
import json, sys, urllib.request
from http.cookiejar import CookieJar

base, query = sys.argv[1], sys.argv[2]
body = json.dumps({"query": query}).encode()
req = urllib.request.Request(f"{base}/api/chat/stream", data=body,
                            headers={"Content-Type": "application/json"}, method="POST")
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
raw = b""
with opener.open(req, timeout=180) as resp:
    for chunk in resp:
        raw += chunk
text = raw.decode("utf-8", errors="replace")
events, answer, current = {}, {}, None
for line in text.splitlines():
    if line.startswith("event: "):
        current = line[7:].strip()
        events[current] = events.get(current, 0) + 1
    elif line.startswith("data: {") and current == "answer":
        try:
            answer = json.loads(line[6:])
        except json.JSONDecodeError:
            pass
citations = answer.get("citations") or []
evidence = answer.get("evidence") or []
def origin(item):
    if not isinstance(item, dict):
        return str(item)[:40]
    for key in ("url", "source_locator", "handle", "source", "kind", "origin"):
        if item.get(key):
            return str(item[key])[:80]
    return "?"
print(json.dumps({
    "query": query,
    "events": events,
    "query_type": answer.get("query_type"),
    "answer_len": len(answer.get("answer_text") or ""),
    "answer_head": (answer.get("answer_text") or "")[:300],
    "citations": len(citations),
    "citation_origins": [origin(c) for c in citations[:8]],
    "evidence_count": len(evidence),
    "evidence_origins": [origin(e) for e in evidence[:8]],
    "has_error_event": "error" in events,
    "raw_sse_bytes": len(raw),
}, ensure_ascii=False, indent=2))
PY
    cat "${OUT}/one-question.json"

    log "replay 门（容器内 mirothinker-replay，离线）"
    compose exec -T app mirothinker-replay --out-dir /tmp/docker-rehearsal \
      > "${OUT}/replay-${PHASE}.log" 2>&1
    replay_rc=$?
    tail -20 "${OUT}/replay-${PHASE}.log"
    log "replay exit=${replay_rc}"
    compose exec -T app bash -lc \
      "cp -r /tmp/docker-rehearsal /opt/mirothinker/logs/accept-${PHASE} && cat /tmp/docker-rehearsal/report.json" \
      > "${OUT}/replay-report.json" 2>/dev/null || true

    log "收尾：停止容器（保留数据与状态目录）"
    docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | tee "${OUT}/stats-final-${PHASE}.txt"
    compose down
    ;;

  ro)
    cleanup_project
    rm -f "${KIT}/receipt-ro-probe.json"
    log "只读实验：数据根 :ro 挂载，其余同主演练"
    started="$(date +%s)"
    docker run -d --name "mirothinker-${PHASE}-manual" \
      --user "${RUN_UID}:${RUN_GID}" \
      -p "${HOST_PORT}:${CONTAINER_IN_PORT}" \
      -v "${DATA}:/var/tmp/mirothinker-data-v2:ro" \
      -v "${STATE}:/var/tmp/mirothinker-canonical-v2-s12f" \
      -v "${KIT}/state/config-managed:/opt/mirothinker/config/managed" \
      -v "${KIT}/state/logs:/opt/mirothinker/logs" \
      -v "${KIT}/secrets/.deepseek_api_key:/opt/mirothinker/.deepseek_api_key:ro" \
      -v "${KIT}/secrets/.bocha_api_key:/opt/mirothinker/.bocha_api_key:ro" \
      -v "${KIT}/secrets/.serper_api_key:/opt/mirothinker/.serper_api_key:ro" \
      -v "${KIT}/secrets/.sglang_api_key:/opt/mirothinker/.sglang_api_key:ro" \
      "$IMAGE" >/dev/null
    if wait_health 900; then
      log "只读数据根：启动成功，boot_wall_clock=$(( $(date +%s) - started ))s"
    else
      log "只读数据根：900 s 内未起来（这就是结论，见下文日志）"
    fi
    docker logs "mirothinker-${PHASE}-manual" > "${OUT}/container-${PHASE}.log" 2>&1 || true
    printf 'receipt 写没写：'; ls -l "${DATA}/serving-pack-run16-readerbound.mount-receipt.json" 2>&1 | head -1
    printf '父目录内 receipt 相关文件：\n'; ls -l "${DATA}" | grep -i receipt || echo "  （无）"
    printf '日志里的 receipt 行：\n'; grep -i "receipt" "${OUT}/container-${PHASE}.log" | head -5 || echo "  （无）"
    docker rm -f "mirothinker-${PHASE}-manual" >/dev/null 2>&1 || true
    ;;

  wronguid)
    cleanup_project
    log "权限实验：以 uid 405:405 运行（数据属主是 1004）"
    docker run -d --name "mirothinker-${PHASE}-manual" \
      --user 405:405 \
      -p "${HOST_PORT}:${CONTAINER_IN_PORT}" \
      -v "${DATA}:/var/tmp/mirothinker-data-v2" \
      -v "${STATE}:/var/tmp/mirothinker-canonical-v2-s12f" \
      -v "${KIT}/secrets/.deepseek_api_key:/opt/mirothinker/.deepseek_api_key:ro" \
      -v "${KIT}/secrets/.bocha_api_key:/opt/mirothinker/.bocha_api_key:ro" \
      -v "${KIT}/secrets/.serper_api_key:/opt/mirothinker/.serper_api_key:ro" \
      -v "${KIT}/secrets/.sglang_api_key:/opt/mirothinker/.sglang_api_key:ro" \
      "$IMAGE" >/dev/null
    sleep 45
    docker logs "mirothinker-${PHASE}-manual" > "${OUT}/container-${PHASE}.log" 2>&1 || true
    tail -25 "${OUT}/container-${PHASE}.log"
    printf '\n容器状态：'; docker inspect -f '{{.State.Status}} exit={{.State.ExitCode}}' "mirothinker-${PHASE}-manual"
    docker rm -f "mirothinker-${PHASE}-manual" >/dev/null 2>&1 || true
    ;;

  *)
    echo "usage: $0 {rw|ro|wronguid}" >&2
    exit 2
    ;;
esac

log "phase=${PHASE} 结束"
