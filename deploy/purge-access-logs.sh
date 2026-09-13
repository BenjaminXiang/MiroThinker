#!/usr/bin/env bash
# 访问日志滚动清理：删除保留期之前的 turn 和空 session。
#
# 保留期解析顺序（与受管配置的 env > file > default 优先级镜像）：
#   1. 位置参数（运维手工覆盖）
#   2. CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS
#   3. 受管配置文件 paths.access_log_retention_days（默认 config/managed/settings.json，
#      可用 CANONICAL_V2_MANAGED_SETTINGS 指定；页面同源读取该项）
#   4. 默认 90 天
# 配置值不可读/类型不对/超出 1..3650 时回落到 90 天并打 warning，绝不因配置问题少删或多删。
# 用法: purge-access-logs.sh [保留天数]
# 注意：不做 VACUUM（服务持有库句柄，需独占锁），文件体积不回收但可复用页。
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB="${CANONICAL_V2_ACCESS_LOG_DB:-/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3}"
SETTINGS="${CANONICAL_V2_MANAGED_SETTINGS:-$(dirname "$DEPLOY_DIR")/config/managed/settings.json}"
ARG_DAYS="${1:-}"

if [ ! -f "$DB" ]; then
  echo "no access log db at $DB, skip"
  exit 0
fi

python3 - "$DB" "$ARG_DAYS" "$SETTINGS" <<'PY'
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

DEFAULT_DAYS = 90
MIN_DAYS = 1
MAX_DAYS = 3650

db_path, arg_days, settings_path = sys.argv[1], sys.argv[2], sys.argv[3]


def _whole_days(raw):
    """Return the value as a usable day count, or None when it is not one."""

    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if MIN_DAYS <= value <= MAX_DAYS else None


def _from_settings_file(path):
    """Stdlib-only read of one whitelisted key; cron must not import the app."""

    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload["paths"]["access_log_retention_days"]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


candidates = (
    ("argument", arg_days),
    ("env", os.environ.get("CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS")),
    ("file", _from_settings_file(settings_path)),
)

days, source = DEFAULT_DAYS, "default"
for name, raw in candidates:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        continue
    resolved = _whole_days(raw)
    if resolved is None:
        print(
            f"warning: {name} retention value {raw!r} is not a whole number of"
            f" days in {MIN_DAYS}..{MAX_DAYS}; ignoring it",
            file=sys.stderr,
        )
        continue
    days, source = resolved, name
    break

# 与 services/canonical_v2_access_log.py::_utc_iso 同格式（UTC isoformat，
# 固定 +00:00 后缀，微秒定宽，字典序可比较）
cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
    timespec="microseconds"
)
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
print(
    f"purged turns={turns} sessions={sessions} cutoff={cutoff}"
    f" retention_days={days} source={source}"
)
PY
