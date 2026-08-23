#!/usr/bin/env bash
# 部署后验收并回报：结果推回私有仓库，源侧核验（需 gh auth 或 git 凭据）
set -Eeuo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
REPORT=/tmp/deploy-report.json
{
  echo '{'
  echo '"host": "'"$(hostname)"'", "time": "'"$(date -u +%FT%TZ)"'",'
  echo '"healthz": '"$(curl -s -m 5 http://127.0.0.1:18201/healthz || echo null)"','
  echo '"inventory": '"$(curl -s -m 10 http://127.0.0.1:18201/api/inventory || echo null)"','
  echo '"scenario_ubtech_patents": '"$(curl -s -m 90 'http://127.0.0.1:18201/api/company/深圳市优必选科技股份有限公司' | head -c 300)"','
  echo '"tests": '"$(LIGHT_LANE_TEST_BASE=http://127.0.0.1:18201 .venv/bin/python -m pytest test_light_lane_api.py -q 2>&1 | tail -1 | sed 's/^/"/; s/$/"/')"'
  echo '}'
} > "$REPORT" 2>/dev/null || true
cat "$REPORT"
echo "—— 正在推回私有仓库 ——"
if command -v gh >/dev/null; then
  gh api repos/BenjaminXiang/mirothinker-migrate/contents/deploy-report.json \
    -X PUT -f message="deploy report $(date -u +%FT%TZ)" \
    -f content="$(base64 -w0 "$REPORT")" >/dev/null && echo "已推送：仓库根目录 deploy-report.json"
else
  echo "gh 不可用；请手动把 /tmp/deploy-report.json 内容发给源侧"
fi
