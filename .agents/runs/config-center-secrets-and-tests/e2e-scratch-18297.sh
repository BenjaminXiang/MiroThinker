#!/usr/bin/env bash
# P13 E2E: config center secrets + connectivity tests on a scratch port.
#
# Scope discipline:
#   * scratch config dir (/tmp/p13-config-center-scratch) and scratch port 18297;
#   * the live 18188 service is never touched or restarted;
#   * provider env vars are unset for this process only (the host shell keeps them);
#   * outbound calls to real endpoints are budgeted and counted: the mock server on
#     18298 absorbs every test except the single embedding probe in section 8.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SCRATCH="/tmp/p13-config-center-scratch"
PORT="${PORT:-18297}"
MOCK_PORT="${MOCK_PORT:-18298}"
BASE="http://127.0.0.1:${PORT}"
MOCK="http://127.0.0.1:${MOCK_PORT}"
FAKE_KEY="sk-fake-e2e-0000-1111-beef"

rm -rf "$SCRATCH"
mkdir -p "$SCRATCH/managed"
chmod 700 "$SCRATCH/managed"

say() { printf '\n=== %s ===\n' "$1"; }
code() { curl -s -o /tmp/p13-out.json -w '%{http_code}' "$@"; }
show() { python3 -c "import json;d=json.load(open('/tmp/p13-out.json'));print(json.dumps(d,ensure_ascii=False,indent=2)[:1500])"; }
field_state() { python3 - "$1" <<'PY'
import json, sys
body = json.load(open('/tmp/p13-out.json'))
for entry in body['secrets']:
    if entry['field'] == sys.argv[1]:
        print(f"   {entry['field']}: configured={entry['configured']} mask={entry['mask']} "
              f"origin={entry['origin']} adopted={entry['applied_to_process_env']}")
PY
}

cleanup() {
  [[ -n "${SERVER_PID:-}" ]] && { kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; }
  [[ -n "${MOCK_PID:-}" ]] && { kill "$MOCK_PID" 2>/dev/null; wait "$MOCK_PID" 2>/dev/null; }
}
trap cleanup EXIT

start_mock() {
  python3 - "$MOCK_PORT" > "${SCRATCH}/mock.log" 2>&1 <<'PY' &
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get('Content-Length') or 0)
        self.rfile.read(length)
        # /reject answers 401 so the "reachable but credential rejected" path is
        # exercised deterministically; everything else answers 200.
        status = 401 if self.path.startswith('/reject') else 200
        body = b'{"ok": true}' if status == 200 else b'{"error": "rejected"}'
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        # One line per served request: the E2E counts these as evidence that a
        # test made exactly one call.
        print(f'MOCK-CALL path={self.path} status={status} auth={"yes" if self.headers.get("Authorization") else "no"}',
              flush=True)

    def log_message(self, *args):  # keep the default request log quiet
        return

ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
PY
  MOCK_PID=$!
  for _ in $(seq 1 40); do
    if curl -s -o /dev/null "${MOCK}/reject" -X POST -d '{}'; then return 0; fi
    sleep 0.25
  done
  echo "mock server did not start"; exit 1
}

start_server() {
  cd "$REPO/apps/admin-console" || exit 1
  env -u BOCHA_API_KEY -u SERPER_API_KEY -u LOCAL_LLM_API_KEY -u EMBEDDING_API_KEY \
      -u CANONICAL_V2_RERANK_API_KEY \
      CANONICAL_V2_MANAGED_SETTINGS="${SCRATCH}/managed/settings.json" \
      CANONICAL_V2_MANAGED_SECRETS="${SCRATCH}/managed/secrets.json" \
      uv run uvicorn backend.main:app --host 127.0.0.1 --port "$PORT" \
      > "${SCRATCH}/server.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 60); do
    if curl -sf "${BASE}/api/health" >/dev/null 2>&1; then return 0; fi
    sleep 0.5
  done
  echo "server did not start"; tail -20 "${SCRATCH}/server.log"; exit 1
}

say "0. start local mock transport (18298) + scratch admin server on ${PORT}"
start_mock
start_server
echo "admin pid=${SERVER_PID}  mock pid=${MOCK_PID}"
echo "health: $(curl -s "${BASE}/api/health")"

say "1. page and W1 surfaces still answer (no regression)"
echo "GET /admin         -> $(code "${BASE}/admin")"
echo "GET /config        -> $(code "${BASE}/api/canonical-v2/admin/config")"
echo "GET /system-status -> $(code "${BASE}/api/canonical-v2/admin/system-status")"
echo "POST providers hc  -> $(code -X POST "${BASE}/api/canonical-v2/admin/providers/health-check")"

say "2. secrets before any write (read-only view, masks only)"
echo "GET /secrets -> $(code "${BASE}/api/canonical-v2/admin/secrets")"
field_state bocha.api_key
field_state rerank.api_key
echo "plaintext in body? $(grep -c "$FAKE_KEY" /tmp/p13-out.json || true)"

say "3. set a fake key from the page (PATCH) — never echoed"
echo "PATCH /secrets -> $(code -X PATCH -H 'Content-Type: application/json' -H 'X-Remote-User: e2e-operator' \
  -d "{\"values\": {\"bocha.api_key\": \"${FAKE_KEY}\", \"rerank.api_key\": \"${FAKE_KEY}\"}}" \
  "${BASE}/api/canonical-v2/admin/secrets")"
field_state bocha.api_key
field_state rerank.api_key
echo "plaintext in response? $(grep -c "$FAKE_KEY" /tmp/p13-out.json || true)"
echo "file mode: $(stat -c '%a' "${SCRATCH}/managed/secrets.json")  (0600 expected)"
echo "value present in the managed file (the carrier)? $(grep -c "$FAKE_KEY" "${SCRATCH}/managed/secrets.json" || true)"
echo "plaintext in audit? $(grep -c "$FAKE_KEY" "${SCRATCH}/managed/secrets-audit.jsonl" || true)"
echo "audit line: $(head -1 "${SCRATCH}/managed/secrets-audit.jsonl")"

say "4. masked echo after write"
echo "GET /secrets -> $(code "${BASE}/api/canonical-v2/admin/secrets")"
field_state bocha.api_key
field_state rerank.api_key
python3 -c "import json;d=json.load(open('/tmp/p13-out.json'));print('   restart_required:',d['restart_required'])"

say "5. connectivity test BEFORE saving, with unsaved endpoint + key (local mock, 1 call)"
echo "POST /connections/test (rerank -> mock, unsaved values) -> $(code -X POST -H 'Content-Type: application/json' \
  -d "{\"connection\": \"rerank\", \"api_key\": \"${FAKE_KEY}\", \"base_url\": \"${MOCK}\", \"model\": \"qwen3-reranker-8b\"}" \
  "${BASE}/api/canonical-v2/admin/connections/test")"
show
echo "plaintext in response? $(grep -c "$FAKE_KEY" /tmp/p13-out.json || true)"
echo "mock calls served: $(grep -c 'MOCK-CALL' "${SCRATCH}/mock.log" || true) (includes the 1 readiness probe)"; grep 'MOCK-CALL' "${SCRATCH}/mock.log" | tail -3

say "6. rate limit: an immediate second test is rejected without another call"
echo "POST /connections/test (again) -> $(code -X POST -H 'Content-Type: application/json' \
  -d "{\"connection\": \"rerank\", \"base_url\": \"${MOCK}\"}" "${BASE}/api/canonical-v2/admin/connections/test")"
show

say "7. failure path: mock answers 401 → 'endpoint reachable, credential rejected'"
sleep 1.2
echo "POST /connections/test (rerank -> mock/reject) -> $(code -X POST -H 'Content-Type: application/json' \
  -d "{\"connection\": \"rerank\", \"base_url\": \"${MOCK}/reject\"}" "${BASE}/api/canonical-v2/admin/connections/test")"
show

say "8. real-endpoint probe: exactly ONE call, embedding 100.64.0.27:18005"
sleep 1.2
echo "POST /connections/test (embedding, real endpoint) -> $(code -X POST -H 'Content-Type: application/json' \
  -d '{"connection": "embedding", "base_url": "http://100.64.0.27:18005/v1"}' \
  "${BASE}/api/canonical-v2/admin/connections/test")"
show

say "9. clear, then set again"
echo "PATCH clear -> $(code -X PATCH -H 'Content-Type: application/json' \
  -d '{"values": {"bocha.api_key": null}}' "${BASE}/api/canonical-v2/admin/secrets")"
field_state bocha.api_key
echo "PATCH set again -> $(code -X PATCH -H 'Content-Type: application/json' \
  -d "{\"values\": {\"bocha.api_key\": \"${FAKE_KEY}\"}}" "${BASE}/api/canonical-v2/admin/secrets")"
field_state bocha.api_key

say "10. restart the scratch service: adoption happens at startup, not hot"
echo "--- before restart (the running process has not read the new value) ---"
echo "GET /secrets -> $(code "${BASE}/api/canonical-v2/admin/secrets")"
field_state bocha.api_key
kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null
start_server
echo "--- after restart (new pid=${SERVER_PID}) ---"
echo "GET /secrets -> $(code "${BASE}/api/canonical-v2/admin/secrets")"
field_state bocha.api_key

say "11. plaintext leakage sweep (responses, logs, audit, page)"
echo "sentinel in server log : $(grep -c "$FAKE_KEY" "${SCRATCH}/server.log" || true)"
echo "sentinel in audit file : $(grep -c "$FAKE_KEY" "${SCRATCH}/managed/secrets-audit.jsonl" || true)"
echo "sentinel in /admin html: $(curl -s "${BASE}/admin" | grep -c "$FAKE_KEY" || true)"
echo "sentinel in /secrets   : $(curl -s "${BASE}/api/canonical-v2/admin/secrets" | grep -c "$FAKE_KEY" || true)"
echo "sentinel in /config    : $(curl -s "${BASE}/api/canonical-v2/admin/config" | grep -c "$FAKE_KEY" || true)"

say "12. a new switch written from the page + the read-only policy"
echo "PATCH /config serving.{web_topical_floor,rerank_timeout_seconds} -> $(code -X PATCH -H 'Content-Type: application/json' \
  -d '{"serving": {"web_topical_floor": false, "rerank_timeout_seconds": 2.5}}' "${BASE}/api/canonical-v2/admin/config")"
python3 -c "import json;print('   changed:',json.load(open('/tmp/p13-out.json'))['changed'])"
echo "PATCH /config serving.full_verify (display-only) -> $(code -X PATCH -H 'Content-Type: application/json' \
  -d '{"serving": {"full_verify": true}}' "${BASE}/api/canonical-v2/admin/config")"
show
echo "PATCH /config serving.not_a_field -> $(code -X PATCH -H 'Content-Type: application/json' \
  -d '{"serving": {"not_a_field": 1}}' "${BASE}/api/canonical-v2/admin/config")"
show
sleep 1.2
echo "POST /connections/test (llm without endpoint) -> $(code -X POST -H 'Content-Type: application/json' \
  -d '{"connection": "llm"}' "${BASE}/api/canonical-v2/admin/connections/test")"
show

say "13. restart adopts file-owned switches (env untouched, env still wins)"
kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null
start_server
echo "restarted (new pid=${SERVER_PID})"
echo "settings file serving section:"
python3 -c "import json;print(json.dumps(json.load(open('${SCRATCH}/managed/settings.json'))['serving'],ensure_ascii=False,indent=2))"
echo "env override still wins over the file for a pinned var (CANONICAL_V2_RERANK_TIMEOUT_SECONDS=9.0):"
kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null
cd "$REPO/apps/admin-console" || exit 1
env -u BOCHA_API_KEY CANONICAL_V2_RERANK_TIMEOUT_SECONDS=9.0 \
    CANONICAL_V2_MANAGED_SETTINGS="${SCRATCH}/managed/settings.json" \
    CANONICAL_V2_MANAGED_SECRETS="${SCRATCH}/managed/secrets.json" \
    uv run python -c "
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore, default_settings_path
from src.data_agents.canonical_v2.managed_runtime import apply_managed_runtime_config, applied_env_names
import os
receipt = apply_managed_runtime_config()
print('   settings applied:', receipt['settings_applied'])
print('   settings skipped (env wins):', receipt['settings_skipped_env'])
print('   adopted env var:', os.environ.get('CANONICAL_V2_MANAGED_ENV_APPLIED'))
print('   web floor ->', os.environ.get('CANONICAL_V2_WEB_TOPICAL_FLOOR'), '| rerank timeout ->', os.environ.get('CANONICAL_V2_RERANK_TIMEOUT_SECONDS'))
"
echo
echo "E2E done."
