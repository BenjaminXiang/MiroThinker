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
