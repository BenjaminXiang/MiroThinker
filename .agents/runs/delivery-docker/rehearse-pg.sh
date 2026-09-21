#!/usr/bin/env bash
# Task A 演练：把 PostgreSQL 服务纳入栈后的端到端验收（含 down/up 幂等与持久性）。
#
#   rehearse-pg.sh up        起栈 → 等健康 → 采集库证据 → 一次 preview → 面板 → pg_dump/restore
#   rehearse-pg.sh restart   down + up，证明迁移幂等、数据仍在
#   rehearse-pg.sh down      收尾
#
# 端口 18298（活线 18188 全程不动）；采集库不对宿主发布端口。

set -uo pipefail

PHASE="${1:-up}"
KIT="/var/tmp/mirothinker-docker-kit"
DATA="/var/tmp/mirothinker-docker-data-v2"
STATE="/var/tmp/mirothinker-docker-state-v1"
OUT="/var/tmp/mirothinker-docker-logs"
WORKTREE="/home/longxiang/MiroThinker/.worktrees/delivery-docker"
PORT=18298
PROJECT="mirothinker-docker-pg"
IMAGE="mirothinker-serving:v1"
PGVOL="mirothinker-pgdata-rehearsal"
DB="miroflow_collection_v1"

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }

compose() {
  MIROTHINKER_IMAGE="$IMAGE" MIROTHINKER_HOST_PORT="$PORT" \
  MIROTHINKER_DATA_ROOT="$DATA" MIROTHINKER_STATE_DIR="$STATE" \
  MIROTHINKER_SECRETS_DIR="${KIT}/secrets" MIROTHINKER_MANAGED_DIR="${KIT}/state/config-managed" \
  MIROTHINKER_LOG_DIR="${KIT}/state/logs" MIROTHINKER_UID=1004 MIROTHINKER_GID=1004 \
  MIROTHINKER_PG_ENV_FILE="${KIT}/secrets/postgres.env" MIROTHINKER_PG_VOLUME="$PGVOL" \
  MIROTHINKER_TIMING_PATH="${MIROTHINKER_TIMING_PATH:-}" \
  docker compose -p "$PROJECT" -f "${KIT}/compose.yaml" "$@"
}

db_psql() { compose exec -T db sh -lc "psql -qAt -U \"\$POSTGRES_USER\" -d $DB -c \"$1\""; }

db_evidence() {
  local tag="$1"
  {
    echo "### $tag $(date -Is)"
    echo "-- databases:"; compose exec -T db sh -lc 'psql -U "$POSTGRES_USER" -d postgres -c "\l" | head -8'
    echo "-- identity marker:"; compose exec -T db sh -lc \
      'psql -qAt -U "$POSTGRES_USER" -d '"$DB"' -c "SELECT shobj_description(oid,'"'"'pg_database'"'"') FROM pg_database WHERE datname=current_database()"'
    echo "-- alembic revision:"; db_psql "SELECT version_num FROM alembic_version"
    echo "-- base tables (public):"; db_psql "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"
    echo "-- professor_seed/seed_registry/pipeline_run rows:"; db_psql "SELECT (SELECT count(*) FROM professor_seed), (SELECT count(*) FROM seed_registry), (SELECT count(*) FROM pipeline_run)"
    echo "-- table list (first 12):"; db_psql "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1" | head -12
    echo
  } | tee -a "${OUT}/pg-db-evidence.log"
}

wait_health() {
  local deadline=$(( $(date +%s) + ${1:-900} ))
  while (( $(date +%s) < deadline )); do
    if [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${PORT}/api/health")" == "200" ]]; then
      return 0
    fi
    sleep 5
  done
  return 1
}

case "$PHASE" in
  up)
    : > "${OUT}/pg-db-evidence.log"
    log "compose up（app + db；采集库不发布端口；uid 1004:1004）"
    started="$(date +%s)"
    compose up -d
    # db 健康（不阻塞 app 启动，只是证据）
    for _ in $(seq 1 60); do
      status="$(docker inspect -f '{{.State.Health.Status}}' "${PROJECT}-db-1" 2>/dev/null)"
      [[ "$status" == "healthy" ]] && break
      sleep 5
    done
    log "db 健康状态：$(docker inspect -f '{{.State.Health.Status}}' "${PROJECT}-db-1")（up + $(( $(date +%s) - started ))s）"
    compose logs db > "${OUT}/pg-db.log" 2>&1
    db_evidence "after up"

    log "等 app 健康（启动相位 + 迁移）…"
    if wait_health 900; then
      log "app 健康：boot_wall_clock=$(( $(date +%s) - started ))s"
    else
      log "900 s 内未健康 —— 见 pg-app.log"
      compose logs app > "${OUT}/pg-app.log" 2>&1
      exit 1
    fi
    compose logs app > "${OUT}/pg-app.log" 2>&1
    grep -aE "entrypoint\]|console_database=" "${OUT}/pg-app.log" | head -20

    log "容器内迁移状态（幂等证据）"
    compose exec -T app mirothinker-migrate --status | tee "${OUT}/pg-migrate-status.log"

    log "HTTP 验收（登录 → 采集面 → 一次 preview → 面板）"
    /usr/bin/python3 "${WORKTREE}/.agents/runs/delivery-docker/pg_acceptance.py" \
      "$PORT" "$STATE" "${OUT}/pg-acceptance.json" | tee "${OUT}/pg-acceptance-summary.txt"

    db_evidence "after preview"

    log "pg_dump → scratch 库 → 行数对账"
    compose exec -T db sh -lc "pg_dump -U \"\$POSTGRES_USER\" -d $DB --no-owner --no-acl" > "${OUT}/pg-dump.sql" 2>"${OUT}/pg-dump.err"
    log "dump 大小：$(stat -c %s "${OUT}/pg-dump.sql") bytes"
    compose exec -T db sh -lc "psql -q -U \"\$POSTGRES_USER\" -d postgres -c 'DROP DATABASE IF EXISTS miroflow_collection_restorecheck' -c 'CREATE DATABASE miroflow_collection_restorecheck'"
    compose exec -T db sh -lc "psql -q -U \"\$POSTGRES_USER\" -d miroflow_collection_restorecheck" < "${OUT}/pg-dump.sql" > "${OUT}/pg-restore.log" 2>&1
    {
      echo "### restore check $(date -Is)"
      echo "-- source:"
      db_psql "SELECT 'professor_seed=' || (SELECT count(*) FROM professor_seed) || ' pipeline_run=' || (SELECT count(*) FROM pipeline_run) || ' alembic=' || (SELECT version_num FROM alembic_version)"
      echo "-- restored:"
      compose exec -T db sh -lc "psql -qAt -U \"\$POSTGRES_USER\" -d miroflow_collection_restorecheck -c \"SELECT 'professor_seed=' || (SELECT count(*) FROM professor_seed) || ' pipeline_run=' || (SELECT count(*) FROM pipeline_run) || ' alembic=' || (SELECT version_num FROM alembic_version)\""
      echo "-- per-table counts (source vs restored):"
      compose exec -T db sh -lc "psql -qAt -U \"\$POSTGRES_USER\" -d $DB -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1\"" > "${OUT}/pg-tables.txt"
      while read -r table; do
        [[ -z "$table" ]] && continue
        source_count="$(db_psql "SELECT count(*) FROM \"$table\"")"
        restored_count="$(compose exec -T db sh -lc "psql -qAt -U \"\$POSTGRES_USER\" -d miroflow_collection_restorecheck -c 'SELECT count(*) FROM \"$table\"'")"
        printf '%-42s source=%-8s restored=%-8s %s\n' "$table" "$source_count" "$restored_count" \
          "$([[ "$source_count" == "$restored_count" ]] && echo OK || echo MISMATCH)"
      done < "${OUT}/pg-tables.txt"
    } | tee "${OUT}/pg-restore-check.log"
    ;;

  restart)
    log "down（保留具名卷 mirothinker-pgdata-rehearsal 与宿主数据）"
    compose down
    log "up 再来一次：迁移必须幂等（revision_before == revision），数据必须还在"
    started="$(date +%s)"
    compose up -d
    if wait_health 900; then
      log "第二次健康：boot_wall_clock=$(( $(date +%s) - started ))s"
    else
      log "第二次 900 s 内未健康"; compose logs app > "${OUT}/pg-app-restart.log" 2>&1; exit 1
    fi
    compose logs app > "${OUT}/pg-app-restart.log" 2>&1
    grep -aE "采集库迁移就绪|采集库迁移未完成|console_database=" "${OUT}/pg-app-restart.log" | head -5
    compose exec -T app mirothinker-migrate --status | tee "${OUT}/pg-migrate-status-restart.log"
    db_evidence "after restart"
    compose exec -T db sh -lc "psql -qAt -U \"\$POSTGRES_USER\" -d $DB -c \"SELECT 'professor_seed=' || (SELECT count(*) FROM professor_seed) || ' pipeline_run=' || (SELECT count(*) FROM pipeline_run)\"" | tee -a "${OUT}/pg-restart-check.log"
    ;;

  down)
    log "收尾 down（具名卷保留，便于复验）"
    compose down
    docker volume ls | grep -i mirothinker || true
    ;;
  *)
    echo "usage: $0 {up|restart|down}" >&2; exit 2 ;;
esac
log "phase=${PHASE} 结束"
