#!/usr/bin/env bash
# Verify web-search providers are reachable through the corporate proxy.
# Per docs/plans/2026-04-18-002-real-data-e2e-and-db-separation.md §3.3.
#
# Providers probed (must reach the external API):
#   - serper (serper.dev)
#   - google search (googleapis/custom)
#   - sogou (sogou.com)
#
# Prereqs: http_proxy/https_proxy set to 100.64.0.14:7890.
# Usage:   bash run_real_e2e_web_search.sh
set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

echo "=== proxy env ==="
env | grep -iE '^(http|https|all)_proxy|^HTTPS|^HTTP|^ALL_PROXY' || echo "no proxy env set"

echo
echo "=== 1. TCP reachability (proxy host) ==="
if (echo > /dev/tcp/100.64.0.14/7890) 2>/dev/null; then
  echo "proxy 100.64.0.14:7890 reachable"
else
  echo "ERROR: cannot reach 100.64.0.14:7890; set HTTP_PROXY first"
  exit 2
fi

echo
echo "=== 2. Google (https://www.google.com) via proxy ==="
curl -s -o /dev/null -w "google: %{http_code} %{time_total}s\n" https://www.google.com || echo "google: unreachable"

echo
echo "=== 3. Baidu (https://www.baidu.com) via proxy (fallback / CN-reachable) ==="
curl -s -o /dev/null -w "baidu: %{http_code} %{time_total}s\n" https://www.baidu.com || echo "baidu: unreachable"

echo
echo "=== 4. Sogou search endpoint ==="
curl -s -o /dev/null -w "sogou: %{http_code} %{time_total}s\n" "https://www.sogou.com/web?query=shenzhen+yunjing" || echo "sogou: unreachable"

echo
echo "=== 5. serper.dev (requires SERPER_API_KEY) ==="
if [ -n "${SERPER_API_KEY:-}" ]; then
  curl -s -X POST "https://google.serper.dev/search" \
    -H "X-API-KEY: ${SERPER_API_KEY}" -H "Content-Type: application/json" \
    -d '{"q":"深圳 云鲸智能"}' -o /tmp/serper_response.json \
    -w "serper: %{http_code} %{time_total}s\n"
  [ -s /tmp/serper_response.json ] && echo "serper response bytes: $(wc -c < /tmp/serper_response.json)"
else
  echo "serper: SERPER_API_KEY not set; skipping"
fi

echo
echo "=== done ==="
