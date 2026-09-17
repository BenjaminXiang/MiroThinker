#!/usr/bin/env bash
# Scratch smoke for add-admin-auth-and-console.
#
# Runs the shell app on its own port (18295, never 18188) against a scratch
# state directory, then walks the acceptance path: redirect → login → dashboard
# → gate on page + API → account management → forged header → logout.
# Secrets stay inside this script (fabricated values) and are never echoed.
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../apps/admin-console" && pwd)"
PORT="${SMOKE_PORT:-18295}"
BASE="http://127.0.0.1:${PORT}"
STATE="$(mktemp -d /tmp/admin-auth-smoke-XXXXXX)"
JAR="$STATE/cookies.txt"
JAR2="$STATE/cookies-ops2.txt"
LOG="$STATE/server.log"

PASSWORD="scratch-smoke-password"
SECOND="scratch-smoke-reset-password"

export CANONICAL_V2_ADMIN_AUTH_DB="$STATE/admin-auth.sqlite3"
export CANONICAL_V2_ADMIN_AUTH_KEY="$STATE/admin-auth.key"
export CANONICAL_V2_ADMIN_INITIAL_PASSWORD="$PASSWORD"
export CANONICAL_V2_MANAGED_SETTINGS="$STATE/managed-settings.json"
export CANONICAL_V2_MANAGED_SECRETS="$STATE/managed-secrets.json"
export CANONICAL_V2_ACCESS_LOG_DB="$STATE/access-logs.sqlite3"
export CANONICAL_V2_CORRECTIONS_DB="$STATE/corrections.sqlite3"
export CANONICAL_V2_MANUAL_RECALL_DIR="$STATE/manual-recall-v1"

cd "$APP_DIR" || exit 1
uv run uvicorn backend.main:app --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT

for _ in $(seq 1 90); do
  curl -fsS "$BASE/api/health" >/dev/null 2>&1 && break
  sleep 1
done

say() { printf '\n$ %s\n' "$*"; }
code() { curl -s -o "$STATE/body.txt" -w '%{http_code}' "$@"; }

status() { printf '%s' "$1"; }

echo "state_dir=$STATE port=$PORT pid=$SERVER_PID"

say "journal: first-boot seeding line (password masked)"
grep -m1 'first-boot administrator' "$LOG" | sed 's/password:.*/password: <masked>/'
say "password file mode"
stat -c '%a %n' "$STATE/admin-initial-password.txt" 2>/dev/null || echo "missing"

say "GET /logs (no session)"
curl -s -o /dev/null -D - "$BASE/logs" | tr -d '\r' | grep -Ei '^(HTTP/|location:)'
say "GET /api/canonical-v2/admin/system-status (no session)"
body=$(curl -s -w '\n%{http_code}' "$BASE/api/canonical-v2/admin/system-status")
echo "$body" | tail -1
echo "$body" | head -1
say "GET /chat and /static/nav_auth.js (public)"
echo "/chat -> $(code "$BASE/chat")"
echo "/static/nav_auth.js -> $(code "$BASE/static/nav_auth.js")"
echo "/api/health -> $(code "$BASE/api/health")"

say "POST /api/auth/login (wrong password)"
echo "wrong -> $(code -X POST -H 'Content-Type: application/json' -d "{\"username\":\"admin\",\"password\":\"nope\"}" "$BASE/api/auth/login")"

say "POST /api/auth/login (correct password)"
login_status=$(code -c "$JAR" -X POST -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"$PASSWORD\"}" "$BASE/api/auth/login")
echo "login -> $login_status"
sed 's/\(cv2_admin_session=\)[^;]*/\1<masked>/' "$JAR" | grep -c cv2_admin_session | sed 's/^/session cookies stored: /'

say "GET /main with the session"
curl -s -b "$JAR" "$BASE/main" | grep -o 'data-admin-user="[^"]*"' | head -1
say "GET /logs and status API with the session"
echo "GET /logs -> $(code -b "$JAR" "$BASE/logs")"
echo "GET status -> $(code -b "$JAR" "$BASE/api/canonical-v2/admin/system-status")"
curl -s -b "$JAR" "$BASE/api/auth/me" | sed 's/"expires_at":"[^"]*"/"expires_at":"<iso>"/'

say "PATCH admin config with a forged X-Remote-User header (CLI client, no Origin)"
echo "PATCH -> $(code -b "$JAR" -X PATCH -H 'Content-Type: application/json' -H 'X-Remote-User: boss' \
  -d '{"paths":{"access_log_retention_days":30}}' "$BASE/api/canonical-v2/admin/config")"
grep -o '"operator": *"[^"]*"' "$STATE/audit.jsonl" | tail -1
say "PATCH with a foreign Origin"
echo "cross-site PATCH -> $(code -b "$JAR" -X PATCH -H 'Content-Type: application/json' -H 'Origin: https://evil.example' \
  -d '{"paths":{"access_log_retention_days":31}}' "$BASE/api/canonical-v2/admin/config")"

say "account management: create ops2"
create_status=$(code -b "$JAR" -X POST -H 'Content-Type: application/json' -d '{"username":"ops2"}' "$BASE/api/auth/accounts")
generated=$(uv run python -c 'import json,sys;print(json.load(open(sys.argv[1]))["password"])' "$STATE/body.txt")
echo "create -> $create_status (generated password captured, not printed)"
echo "login as ops2 -> $(code -c "$JAR2" -X POST -H 'Content-Type: application/json' \
  -d "{\"username\":\"ops2\",\"password\":\"$generated\"}" "$BASE/api/auth/login")"
echo "ops2 /api/auth/me -> $(code -b "$JAR2" "$BASE/api/auth/me")"

say "lockout: five wrong passwords for ops3, then the right one after the window"
third=$(code -b "$JAR" -X POST -H 'Content-Type: application/json' -d '{"username":"ops3"}' "$BASE/api/auth/accounts")
ops3_password=$(uv run python -c 'import json,sys;print(json.load(open(sys.argv[1]))["password"])' "$STATE/body.txt")
echo "create ops3 -> $third (generated password captured, not printed)"
for _ in 1 2 3 4 5; do code -X POST -H 'Content-Type: application/json' \
  -d "{\"username\":\"ops3\",\"password\":\"wrong-$RANDOM\"}" "$BASE/api/auth/login" >/dev/null; done
locked=$(code -X POST -H 'Content-Type: application/json' \
  -d "{\"username\":\"ops3\",\"password\":\"$ops3_password\"}" "$BASE/api/auth/login")
echo "sixth attempt (right password, inside the window) -> $locked $(head -c 80 "$STATE/body.txt")"
sleep 61
recovered=$(code -X POST -H 'Content-Type: application/json' \
  -d "{\"username\":\"ops3\",\"password\":\"$ops3_password\"}" "$BASE/api/auth/login")
echo "after the 60s window -> $recovered"

say "administrator resets the ops2 password (ops2 session must die)"
reset_status=$(code -b "$JAR" -X POST -H 'Content-Type: application/json' \
  -d "{\"password\":\"$SECOND\"}" "$BASE/api/auth/accounts/ops2/password")
echo "reset -> $reset_status"
echo "old ops2 session -> $(code -b "$JAR2" "$BASE/api/auth/me")"
JAR3="$STATE/cookies-ops2-new.txt"
echo "ops2 login with the new password -> $(code -c "$JAR3" -X POST -H 'Content-Type: application/json' \
  -d "{\"username\":\"ops2\",\"password\":\"$SECOND\"}" "$BASE/api/auth/login")"

say "self password change for admin (old cookie dies, new one works)"
OLD_JAR="$STATE/cookies-old.txt"
cp "$JAR" "$OLD_JAR"
change=$(code -b "$JAR" -c "$JAR" -X POST -H 'Content-Type: application/json' \
  -d "{\"current_password\":\"$PASSWORD\",\"new_password\":\"scratch-smoke-third\"}" "$BASE/api/auth/password")
echo "password change -> $change"
echo "pre-change admin cookie -> $(code -b "$OLD_JAR" "$BASE/api/auth/me")"
echo "current admin cookie -> $(code -b "$JAR" "$BASE/api/auth/me")"

say "delete ops2 and ops3 (their logins must be refused afterwards)"
echo "delete ops2 -> $(code -b "$JAR" -X DELETE "$BASE/api/auth/accounts/ops2")"
echo "ops2 login after delete -> $(code -X POST -H 'Content-Type: application/json' \
  -d "{\"username\":\"ops2\",\"password\":\"$SECOND\"}" "$BASE/api/auth/login")"
echo "delete ops3 -> $(code -b "$JAR" -X DELETE "$BASE/api/auth/accounts/ops3")"
say "the last account cannot be deleted"
echo "delete admin -> $(code -b "$JAR" -X DELETE "$BASE/api/auth/accounts/admin") $(head -c 80 "$STATE/body.txt")"
echo "accounts left -> $(curl -s -b "$JAR" "$BASE/api/auth/accounts")"

say "logout"
echo "logout -> $(code -b "$JAR" -c "$JAR" -X POST "$BASE/api/auth/logout")"
echo "after logout /api/auth/me -> $(code -b "$JAR" "$BASE/api/auth/me")"

say "audit trail (actor / action / target / result)"
uv run python - "$STATE/admin-auth.sqlite3" <<'PY'
import sqlite3, sys
rows = sqlite3.connect(sys.argv[1]).execute(
    "SELECT actor, action, target, result, source_ip FROM audit ORDER BY id"
).fetchall()
for row in rows:
    print(" | ".join(str(value) for value in row))
print("rows:", len(rows))
PY

say "server access log (last 8 lines)"
tail -8 "$LOG"
