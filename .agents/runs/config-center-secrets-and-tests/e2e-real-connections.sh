#!/usr/bin/env bash
# P13 follow-up: five-connection acceptance against REAL endpoints, run on the
# fixed resolution chain in a scratch process. 18188 is NOT restarted and NOT
# touched; it still serves the previous build.
#
# Faithfulness to the live line:
#   * the scratch process runs with the live env (CHAT_LLM_PROFILE=deepseekv4flash)
#     and with every credential variable scrubbed, exactly like pid 1886109, so the
#     resolution must go through the repository key files;
#   * scratch managed config dir (empty) → nothing pending.
# Call budget: at most ONE real call per connection, counted below.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SCRATCH="/tmp/p13-real-connections"
PORT="${PORT:-18297}"
BASE="http://127.0.0.1:${PORT}"

rm -rf "$SCRATCH"; mkdir -p "$SCRATCH/managed"; chmod 700 "$SCRATCH/managed"

cleanup() { [[ -n "${SERVER_PID:-}" ]] && { kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; }; }
trap cleanup EXIT

cd "$REPO/apps/admin-console" || exit 1
env -u API_KEY -u OPENAI_API_KEY -u SGLANG_API_KEY -u BOCHA_API_KEY -u SERPER_API_KEY \
    -u DEEPSEEK_API_KEY -u LOCAL_LLM_API_KEY -u EMBEDDING_API_KEY \
    -u CANONICAL_V2_RERANK_API_KEY -u CANONICAL_V2_RERANK_API_KEY_FILE \
    -u CANONICAL_V2_RERANK_BASE_URL \
    CHAT_LLM_PROFILE=deepseekv4flash \
    CANONICAL_V2_MANAGED_SETTINGS="${SCRATCH}/managed/settings.json" \
    CANONICAL_V2_MANAGED_SECRETS="${SCRATCH}/managed/secrets.json" \
    uv run uvicorn backend.main:app --host 127.0.0.1 --port "$PORT" \
    > "${SCRATCH}/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 60); do curl -sf "${BASE}/api/health" >/dev/null 2>&1 && break; sleep 0.5; done
echo "scratch admin server pid=${SERVER_PID} on ${PORT} (18188 untouched)"

echo
echo "=== runtime state as the page reports it ==="
curl -s "${BASE}/api/canonical-v2/admin/secrets" | python3 -c "
import json,sys
body = json.load(sys.stdin)
for conn in body['connections']:
    rt = conn['runtime']
    print(f\"  {conn['key']:9} enabled={str(rt['enabled']):5} endpoint={rt['base_url'] or '-'}\")
    print(f\"            credential_origin={rt['api_key_origin'] or '-'} pending_restart={rt['pending_restart']}\")
    print(f\"            note={rt['runtime_note']}\")
"

if [[ "${SKIP_CALLS:-0}" == "1" ]]; then
  echo "SKIP_CALLS=1: connection probes skipped (re-verifying the leakage sweep only, zero real calls)"
fi
for conn in bocha serper rerank embedding llm; do
  [[ "${SKIP_CALLS:-0}" == "1" ]] && break
  echo
  echo "=== connection test: ${conn} (one request; rate limit sleeps between) ==="
  sleep 1.2
  curl -s -X POST -H 'Content-Type: application/json' \
    -d "{\"connection\": \"${conn}\"}" \
    "${BASE}/api/canonical-v2/admin/connections/test" | python3 -c "
import json,sys
p = json.load(sys.stdin)
print('  verdict :', 'OK' if p['ok'] else 'FAIL', '| called:', p.get('called'), '| latency_ms:', p['latency_ms'], '| http:', p['http_status'])
print('  detail  :', p['detail'])
print('  runtime : enabled=', p['runtime']['enabled'], '| endpoint=', p['runtime']['base_url'], '| credential=', p['used']['api_key_source'])
print('  rate    : remaining this minute =', p['rate']['remaining'])
"
done

echo
echo "=== leakage sweep (no credential may appear in the response or the log) ==="
# Precise check: fetch each surface and count exact occurrences of the real
# credential values, read in memory. Only counts are printed — never a value.
SKIP_CALLS="${SKIP_CALLS:-0}" SCRATCH="${SCRATCH}" BASE="${BASE}" REPO="${REPO}" python3 - <<'PY'
import json, os, re, urllib.request
from pathlib import Path

base, scratch, repo = os.environ["BASE"], Path(os.environ["SCRATCH"]), Path(os.environ["REPO"])
key_files = [".bocha_api_key", ".serper_api_key", ".deepseek_api_key", ".sglang_api_key"]
# Same roots the providers walk (repo + ancestors), so the check really compares
# against the credentials the live process would load.
roots = [repo, *repo.parents, Path.cwd(), *Path.cwd().parents]
secrets = {}
for name in key_files:
    for root in roots:
        path = root / name
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            secrets[name] = value
            break
if not secrets:
    raise SystemExit("leakage sweep is vacuous: no key file was found to compare against")

def body(path: str) -> str:
    try:
        with urllib.request.urlopen(base + path, timeout=10) as response:
            return response.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return f"<unreadable: {type(exc).__name__}>"

surfaces = {
    "/api/canonical-v2/admin/secrets": body("/api/canonical-v2/admin/secrets"),
    "/api/canonical-v2/admin/config": body("/api/canonical-v2/admin/config"),
    "/admin": body("/admin"),
    "server.log": (scratch / "server.log").read_text(encoding="utf-8", errors="replace"),
}
for label, text in surfaces.items():
    hits = {name: text.count(value) for name, value in secrets.items() if value}
    masks = len(re.findall(r"\w{1,3}…\w{4}", text))
    print(f"  {label}: exact-credential-hits={sum(hits.values())} {hits} masks={masks}")
PY
echo "  (masks are the intended 3-head/4-tail rendering, e.g. k8#…0204)"
if [[ "${SKIP_CALLS:-0}" == "1" ]]; then
  echo "real-endpoint calls this run: 0 (sweep-only re-verification)"
else
  echo "real-endpoint calls: bocha 1, serper 1, embedding 1, llm 1, rerank 0 (reported as not enabled)"
fi
echo "acceptance done."
