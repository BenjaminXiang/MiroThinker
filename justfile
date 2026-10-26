default:
    just --list

# lint monorepo
[group('precommit')]
lint:
    uv tool run ruff@0.8.0 check --fix .

# sort imports
[group('precommit')]
sort-imports:
    uv tool run ruff@0.8.0 check --select I --fix .

# format monorepo
[group('precommit')]
format:
    uv tool run ruff@0.8.0 format .

# check license
[group('precommit')]
check-license:
    uv run reuse lint

# insert license for contributor
insert-license:
    # https://reuse.readthedocs.io/en/stable/scripts.html#add-headers-to-staged-files-based-on-git-settings
    git diff --name-only --cached | xargs -I {} reuse annotate -c "$(git config --get user.name) <$(git config --get user.email)>" "{}"

# format markdown files
[group('precommit')]
format-md:
    find . -name "*.md" -type f | xargs uv tool run mdformat@0.7.17

# run precommit before PR
[group('precommit')]
precommit: lint sort-imports format-md format

# Build admin-console React SPA into frontend/dist (served by the admin backend).
frontend-fresh:
    cd apps/admin-console/frontend && npm run build

# Start current admin-console backend/API. Requires DATABASE_URL or DATABASE_URL_TEST.
# Port 18088 is retired; use 18188 for the Phase B backend.
admin-backend:
    cd apps/admin-console && uv run --no-sync uvicorn backend.main:app --host 0.0.0.0 --port 18188

# Start admin-console Vite dev server with HMR on port 5180.
# Proxies /api to VITE_API_PROXY_TARGET, default http://localhost:18188.
# Use this only when actively editing React code; otherwise rely on backend-served dist.
frontend-dev:
    cd apps/admin-console/frontend && VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-http://localhost:18188}" npm run dev -- --host 0.0.0.0 --port 5180

# golden-set regression gate against a live chat endpoint (27 turns / 19 conversations)
[group('verify')]
eval-gate base="https://gxzx-coze-api.idea.edu.cn" mode="full" baseline="apps/admin-console/scripts/eval-baselines/baseline-full.json":
    #!/usr/bin/env bash
    set -euo pipefail
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY 2>/dev/null || true
    export no_proxy="localhost,127.0.0.1,::1,gxzx-coze-api.idea.edu.cn"
    out="/tmp/eval-gate-$(date +%Y%m%d-%H%M%S).json"
    uv run --with httpx --with pyyaml python apps/admin-console/scripts/eval_full_testset.py \
        --base "{{base}}" --mode "{{mode}}" --out "$out" \
        --baseline "{{baseline}}" --fail-on-regression --label "just-eval-gate"
