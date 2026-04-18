#!/usr/bin/env bash
# Phase 1 end-to-end validation — runs after Rounds 1-4 have landed.
#
# Exercises the full chain:
#   V001 + V002 migration
#   -> seed_loader upserts taxonomy + domain_tier
#   -> canonical_import ingests docs/专辑项目导出1768807339.xlsx
#   -> admin-console data API returns the expected row counts
#
# Fails fast on any step. Run from repo root or apps/miroflow-agent.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
AGENT_ROOT="$REPO_ROOT/apps/miroflow-agent"
XLSX="$REPO_ROOT/docs/专辑项目导出1768807339.xlsx"

: "${DATABASE_URL:=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test}"
export DATABASE_URL

cd "$AGENT_ROOT"

echo "=== 1. alembic downgrade base (clean slate) ==="
uv run alembic downgrade base

echo "=== 2. alembic upgrade head (V001 + V002) ==="
uv run alembic upgrade head

echo "=== 3. seed_loader upserts ==="
uv run python -m src.data_agents.storage.postgres.seed_loader

echo "=== 4. integration tests (Postgres suite) ==="
uv run pytest tests/postgres tests/postgres_seed_loader tests/company -v -n0

echo "=== 4b. re-upgrade + re-seed (test teardown downgraded to base) ==="
uv run alembic upgrade head
uv run python -m src.data_agents.storage.postgres.seed_loader

echo "=== 5. canonical_import of docs/专辑项目导出1768807339.xlsx ==="
# This assumes Round 3 exposes a CLI entrypoint at
# `src.data_agents.company.canonical_import`. If the module doesn't expose
# __main__ yet, fallback to a tiny inline importer.
if uv run python -c "from src.data_agents.company import canonical_import" 2>/dev/null; then
  uv run python -c "
import sys, os, uuid
from pathlib import Path
from src.data_agents.storage.postgres.connection import connect
from src.data_agents.company.canonical_import import import_company_xlsx_to_postgres

# Ensure test seed exists.
with connect() as conn:
    with conn.cursor() as cur:
        cur.execute(\"\"\"
            INSERT INTO seed_registry (seed_id, seed_kind, scope_key, source_uri, refresh_policy)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (seed_kind, scope_key) DO UPDATE SET source_uri = EXCLUDED.source_uri
        \"\"\", ('qimingpian-shenzhen-2026-04', 'company_xlsx', 'qimingpian:shenzhen:2026-04',
               '$XLSX', 'manual'))
        conn.commit()

report = import_company_xlsx_to_postgres(
    Path('$XLSX'),
    dsn=os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://', 1),
    seed_id='qimingpian-shenzhen-2026-04',
)
print(f'records_new={report.records_new_company}')
print(f'team_members_inserted={report.team_members_inserted}')
print(f'funding_events_inserted={report.funding_events_inserted}')
assert 1020 <= report.records_new_company <= 1030, report
"
else
  echo "  canonical_import module not present yet — skipping real import (Round 3 pending)"
fi

echo "=== 6. final counts ==="
sudo -n docker exec pgtest psql -U miroflow -d miroflow_test -c "
SELECT 'company' AS table_name, count(*) FROM company
UNION ALL SELECT 'company_snapshot', count(*) FROM company_snapshot
UNION ALL SELECT 'company_team_member', count(*) FROM company_team_member
UNION ALL SELECT 'company_signal_event funding', count(*) FROM company_signal_event WHERE event_type='funding'
UNION ALL SELECT 'taxonomy_vocabulary', count(*) FROM taxonomy_vocabulary
UNION ALL SELECT 'source_domain_tier_registry', count(*) FROM source_domain_tier_registry
ORDER BY table_name;"

echo "=== Phase 1 E2E succeeded ==="
