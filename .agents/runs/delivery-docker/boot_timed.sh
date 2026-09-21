#!/usr/bin/env bash
# 计时重启：docker compose up -d（可选 --force-recreate）→ 轮询 /api/health，报 boot 秒数。
#
#   boot_timed.sh <port> <bundle_dir> [--recreate] [--timeout 900]
#
# 与 install-site.sh step 7 同一套度量口径（t0 取在 compose up 之前，健康即停），
# 用于演练第二相（预置受管配置后重启）与单测"receipt 快路径"。
set -uo pipefail

PORT="$1"; BUNDLE_DIR="$2"; shift 2
RECREATE=0; TIMEOUT=900
while [[ $# -gt 0 ]]; do
  case "$1" in
    --recreate) RECREATE=1; shift ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    *) echo "unknown: $1" >&2; exit 2 ;;
  esac
done

cd "$BUNDLE_DIR" || exit 1
up_args=(-d)
[[ "$RECREATE" == "1" ]] && up_args+=(--force-recreate)

t0=$(date +%s)
if ! docker compose up "${up_args[@]}" >/tmp/boot-timed-up.out 2>&1; then
  echo "[FAIL] docker compose up 失败："; tail -20 /tmp/boot-timed-up.out; exit 1
fi
started=$(( $(date +%s) - t0 ))

deadline=$(( $(date +%s) + TIMEOUT ))
last_note=0
while (( $(date +%s) < deadline )); do
  if [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null)" == "200" ]]; then
    echo "boot=$(( $(date +%s) - t0 ))s（其中 compose up ${started}s；health http://127.0.0.1:${PORT}/api/health）"
    exit 0
  fi
  now=$(date +%s); elapsed=$(( now - t0 ))
  if (( elapsed - last_note >= 60 )); then
    printf '  …已等 %dm%02ds（%s）\n' $((elapsed / 60)) $((elapsed % 60)) "$(docker compose ps --format '{{.Status}}' | head -1)"
    last_note=$elapsed
  fi
  sleep 5
done
echo "[FAIL] 在 ${TIMEOUT}s 内未健康"
docker compose logs --tail 30 app 2>/dev/null | sed 's/^/  /'
exit 1
