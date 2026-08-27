#!/usr/bin/env bash
# canonical_v2 PG 门控回归的一键例行入口（"每周按一次的按钮"）。
#
# 做三件事：
#   1. 确保带 disposable marker 的基座测试库存在（幂等）；
#   2. 导出四个 CANONICAL_V2_TEST_* 门控变量；
#   3. 跑两个真库门控套件 + 排序回归（无需真库）。
# 前置：pgvector 容器在 127.0.0.1:55458 可达（canonical-v2-s12c-pg-20260726-r8）。
set -Eeuo pipefail

APP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
BASE_DB="${CANONICAL_V2_PG_REGRESSION_BASE_DB:-miroflow_candidate_v2_pgtest_r1}"
GATE_ROOT="${CANONICAL_V2_PG_REGRESSION_GATE_ROOT:-$APP_ROOT/../../.agents/runs/rebuild-canonical-v2-knowledge-platform}"
PORT="${CANONICAL_V2_PG_REGRESSION_PORT:-55458}"

echo "== 1/3 基座库（$BASE_DB@$PORT） =="
uv run --project "$APP_ROOT" python - "$BASE_DB" "$PORT" <<'PY'
import sys

import psycopg

name, port = sys.argv[1], sys.argv[2]
marker = f"miroflow:destructive-target:v1:disposable:{name}"
admin = psycopg.connect(
    f"postgresql://miroflow@127.0.0.1:{port}/postgres", autocommit=True
)
row = admin.execute(
    "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = %s",
    (name,),
).fetchone()
if row is None:
    admin.execute(f'CREATE DATABASE "{name}"')
    admin.execute(f"COMMENT ON DATABASE \"{name}\" IS '{marker}'")
    print(f"created base test database {name} with marker")
else:
    admin.execute(f"COMMENT ON DATABASE \"{name}\" IS '{marker}'")
    print(f"base test database {name} ready (marker refreshed)")
PY

echo "== 2/3 门控变量 =="
export CANONICAL_V2_TEST_DATABASE_URL="postgresql+psycopg://miroflow@127.0.0.1:$PORT/$BASE_DB"
export CANONICAL_V2_TEST_EXPECTED_DATABASE="$BASE_DB"
export CANONICAL_V2_TEST_TARGET_KIND=disposable
export CANONICAL_V2_TEST_BACKUP_GATE_ROOT="$GATE_ROOT"
echo "  gate root: $GATE_ROOT"

echo "== 3/3 套件 =="
cd "$APP_ROOT"
uv run pytest \
  tests/canonical_v2/test_canonical_identity_postgres.py \
  tests/canonical_v2/test_domain_projection_postgres.py \
  tests/canonical_v2/test_domain_inclusion_assertion_order.py \
  -q
