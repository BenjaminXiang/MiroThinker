#!/usr/bin/env bash
# W5 scratch smoke: real HTTP on 127.0.0.1:18289 (never 18188) over a COPY of the
# live access-log database + a scratch managed-settings file. Nothing live is touched.
set -uo pipefail

RUN="/home/longxiang/MiroThinker/.worktrees/admin-audit-logs"
E="$RUN/.agents/runs/admin-audit-logs-w5"
S="/tmp/w5-scratch"
BASE="http://127.0.0.1:18289"
STATUS="$E/scratch-18289-status.txt"

rm -rf "$S"; mkdir -p "$S/managed" "$S/data"; : > "$STATUS"

LIVE="/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3"
cp "$LIVE" "$S/data/access-logs-copy.sqlite3"
cp "$LIVE" "$S/data/purge-copy.sqlite3"
chmod 600 "$S/data/"*.sqlite3
printf '{"schema_version": 1, "paths": {"access_log_retention_days": 45}}\n' > "$S/managed/settings.json"

# --- pre-migration shape of the copied legacy database -----------------------
python3 - "$S/data/access-logs-copy.sqlite3" > "$E/scratch-18289-db-before.json" <<'PY'
import json, sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
shape = {
    "path": sys.argv[1],
    "marker": con.execute("SELECT value FROM workspace_meta WHERE key='schema_version'").fetchone()[0],
    "turn_columns": [row[1] for row in con.execute("PRAGMA table_info(turns)")],
    "sessions": con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
    "turns": con.execute("SELECT COUNT(*) FROM turns").fetchone()[0],
    "query_types": con.execute("SELECT query_type, COUNT(*) FROM turns GROUP BY 1 ORDER BY 2 DESC").fetchall(),
}
con.close()
print(json.dumps(shape, ensure_ascii=False, indent=2))
PY

# --- scratch server (bare V2 shell + real access-log store) -------------------
cd "$RUN/apps/admin-console" || exit 1
CANONICAL_V2_ACCESS_LOG_DB="$S/data/access-logs-copy.sqlite3" \
CANONICAL_V2_MANAGED_SETTINGS="$S/managed/settings.json" \
  nohup timeout 900 uv run python "$E/scratch_18289_server.py" \
  > "$E/scratch-18289-server.log" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 60); do
  if curl -sf -o /dev/null "$BASE/api/health"; then break; fi
  sleep 1
done
curl -sS -o "$E/scratch-18289-health.json" -w "%{http_code}" "$BASE/api/health" > /tmp/w5-health-code
echo "health HTTP $(cat /tmp/w5-health-code)" >> "$STATUS"

hit() { # hit <name> <curl args...>
  local name="$1"; shift
  local code
  code=$(curl -sS -o "$E/scratch-18289-$name" -w "%{http_code}" "$@")
  printf '%-28s HTTP %s\n' "$name" "$code" >> "$STATUS"
}

hit page-logs.html "$BASE/logs"
hit sessions-before.json "$BASE/api/canonical-v2/admin/access-logs/sessions?limit=2"
hit sessions-anonymous.json "$BASE/api/canonical-v2/admin/access-logs/sessions?identity=anonymous&limit=2"

# 1) write one turn through the real record choke point, with the admin identity
hit write-turn.json -X POST "$BASE/scratch/record" \
  -H 'Content-Type: application/json' -H 'X-Remote-User: smoke-auditor' \
  -d '{"session_id":"session:chat:smoke","query":"冒烟：这条记录应带身份","error_detail":"canonical_v2_invalid_option"}'
hit write-turn-noheader.json -X POST "$BASE/scratch/record" \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"session:chat:smoke-anon","query":"冒烟：这条记录应为匿名"}'

# 2) identity visible on list + detail
hit sessions-identity.json "$BASE/api/canonical-v2/admin/access-logs/sessions?identity=smoke-auditor"
hit session-detail.json "$BASE/api/canonical-v2/admin/access-logs/sessions/session:chat:smoke"
hit session-detail-anon.json "$BASE/api/canonical-v2/admin/access-logs/sessions/session:chat:smoke-anon"

# 3) combined filters (time range + query_type + identity + status)
hit filtered-combined.json "$BASE/api/canonical-v2/admin/access-logs/sessions?since=2026-08-10&until=2026-08-13&status=completed&query_type=canonical_v2:A:answer&identity=anonymous&limit=100"
hit filtered-empty-bucket.json "$BASE/api/canonical-v2/admin/access-logs/sessions?query_type=&limit=100"
hit filtered-invalid.json "$BASE/api/canonical-v2/admin/access-logs/sessions?since=2026-09-01T10:00:00"
hit filtered-invalid-order.json "$BASE/api/canonical-v2/admin/access-logs/sessions?since=2026-09-05&until=2026-09-01"

# 4) export (same filters as the page) + unknown format
hit export.csv "$BASE/api/canonical-v2/admin/access-logs/export?format=csv&since=2026-09-01&until=2026-09-30"
hit export.jsonl "$BASE/api/canonical-v2/admin/access-logs/export?format=jsonl&since=2026-09-01&until=2026-09-30"
hit export-filtered.csv "$BASE/api/canonical-v2/admin/access-logs/export?format=csv&identity=smoke-auditor"
hit export-bad-format.json "$BASE/api/canonical-v2/admin/access-logs/export?format=xlsx"

# 5) statistics
hit stats.json "$BASE/api/canonical-v2/admin/access-logs/stats?since=2026-09-01&until=2026-09-30&top_limit=10"
hit stats-default.json "$BASE/api/canonical-v2/admin/access-logs/stats"
hit stats-empty.json "$BASE/api/canonical-v2/admin/access-logs/stats?since=2026-01-01&until=2026-01-31"

# 6) retention source read by the page
hit admin-config.json "$BASE/api/canonical-v2/admin/config"

# --- post-migration shape of the same copy ------------------------------------
python3 - "$S/data/access-logs-copy.sqlite3" > "$E/scratch-18289-db-after.json" <<'PY'
import json, sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
shape = {
    "marker": con.execute("SELECT value FROM workspace_meta WHERE key='schema_version'").fetchone()[0],
    "turn_columns": [row[1] for row in con.execute("PRAGMA table_info(turns)")],
    "sessions": con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
    "turns": con.execute("SELECT COUNT(*) FROM turns").fetchone()[0],
    "identities": con.execute(
        "SELECT COALESCE(NULLIF(user_identity,''),'anonymous'), COUNT(*) FROM turns GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall(),
}
con.close()
print(json.dumps(shape, ensure_ascii=False, indent=2))
PY

echo "$SERVER_PID" > /tmp/w5-scratch-server.pid
echo "server pid $SERVER_PID (kill after evidence collection)"
