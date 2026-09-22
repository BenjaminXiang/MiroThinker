#!/usr/bin/env bash
# Operator-surface identity check: what the config page reports and what its
# connection test actually probes. Built 2026-09-22 for the fembed cutover, where
# three console consumers read CANONICAL_V2_SERVING_PACK and silently fall back to
# the literal Qwen/Qwen3-Embedding-8B when it is unset.
#
#   bash page-identity-check.sh <base-url> <admin-password-file>
#   bash page-identity-check.sh http://127.0.0.1:18188 /var/tmp/mirothinker-canonical-v2-s12f/admin-password-reset-2026-09-22.txt
#
# Expect after the fembed cutover (and on the pre-cutover scratch instance):
#   chat_profile    = deepseekv4flash
#   frozen model    = qwen3.7-text-embedding-flash
#   connection test = ok, 1024 dimensions
# The password is read from the file and never printed.
set -uo pipefail

BASE="${1:?usage: page-identity-check.sh <base-url> <admin-password-file>}"
PWF="${2:?usage: page-identity-check.sh <base-url> <admin-password-file>}"
CJ=$(mktemp); trap 'rm -f "$CJ"' EXIT
[[ -r "$PWF" ]] || { echo "password file not readable: $PWF" >&2; exit 2; }
PASS=$(cat "$PWF")

code=$(curl -s -c "$CJ" -o /tmp/page-check-login.json -w '%{http_code}' \
  -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"$PASS\"}")
echo "login=$code"
[[ "$code" == "200" ]] || { echo "login failed; body: $(head -c 200 /tmp/page-check-login.json)" >&2; exit 1; }

curl -s -b "$CJ" -o /tmp/page-check-presets.json -w 'presets=%{http_code}\n' \
  "$BASE/api/canonical-v2/admin/connections/presets"
python3 - <<'PY'
import json
d = json.load(open('/tmp/page-check-presets.json'))
ef = d.get('embedding_frozen') or {}
print('  chat_profile    =', d.get('chat_profile'))
print('  frozen model    =', ef.get('model'))
print('  frozen base_url =', ef.get('base_url'))
print('  origin          =', ef.get('endpoint_origin'))
PY

curl -s -b "$CJ" -o /tmp/page-check-conntest.json -w 'conn_test=%{http_code}\n' \
  -X POST "$BASE/api/canonical-v2/admin/connections/test" \
  -H 'Content-Type: application/json' -d '{"connection":"embedding"}'
python3 - <<'PY'
import json
raw = open('/tmp/page-check-conntest.json', encoding='utf-8').read()
try:
    d = json.loads(raw)
except Exception:
    print('  (non-JSON body)', raw[:300]); raise SystemExit
def walk(o, p=''):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ('dimensions', 'dimension', 'model', 'ok', 'status', 'error', 'error_detail', 'latency_ms', 'detail'):
                print(f'  {p}{k} = {json.dumps(v, ensure_ascii=False)[:160]}')
            walk(v, p + k + '.')
walk(d)
PY
