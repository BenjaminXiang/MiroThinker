#!/usr/bin/env bash
# 访问日志滚动清理：删除 RETENTION_DAYS 之前的 turn 和空 session。
# 用法: purge-access-logs.sh [保留天数，默认 90]
# 注意：不做 VACUUM（服务持有库句柄，需独占锁），文件体积不回收但可复用页。
set -euo pipefail

DB="${CANONICAL_V2_ACCESS_LOG_DB:-/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3}"
RETENTION_DAYS="${1:-90}"

if [ ! -f "$DB" ]; then
  echo "no access log db at $DB, skip"
  exit 0
fi

python3 - "$DB" "$RETENTION_DAYS" <<'PY'
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

db_path, days = sys.argv[1], int(sys.argv[2])
# 与 services/canonical_v2_access_log.py::_utc_iso 同格式（UTC isoformat，
# 固定 +00:00 后缀，字典序可比较）
cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
con = sqlite3.connect(db_path)
with con:
    turns = con.execute(
        "DELETE FROM turns WHERE finished_at < ?", (cutoff,)
    ).rowcount
    sessions = con.execute(
        """DELETE FROM sessions
           WHERE last_active_at < ?
             AND NOT EXISTS (SELECT 1 FROM turns
                             WHERE turns.session_id = sessions.session_id)""",
        (cutoff,),
    ).rowcount
con.close()
print(f"purged turns={turns} sessions={sessions} cutoff={cutoff}")
PY
