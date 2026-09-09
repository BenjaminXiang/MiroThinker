#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
AGENT_DIR="$ROOT_DIR/apps/miroflow-agent"
LOG_DIR="$ROOT_DIR/docs/source_backfills"
STAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
LOG_FILE="${HOST_EXCEL_E2E_LOG_FILE:-$LOG_DIR/host-e2e-excel-ingest-$STAMP.txt}"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/mirothinker-uv-cache-status}"
COMPANY_XLSX="${HOST_EXCEL_COMPANY_XLSX:-$ROOT_DIR/docs/专辑项目导出1768807339.xlsx}"
PATENT_XLSX="${HOST_EXCEL_PATENT_XLSX:-$ROOT_DIR/docs/2025-12-05 专利.xlsx}"
DEFAULT_DATABASE_URL="postgresql://miroflow:miroflow@localhost:15432/miroflow_real"
DEFAULT_MILVUS_URI="$ROOT_DIR/apps/miroflow-agent/milvus.db"
WORK_DIR="$(mktemp -d /tmp/mirothinker-excel-e2e.XXXXXX)"
FAILURES=0
GAPS=0

mkdir -p "$LOG_DIR"

exec > >(tee "$LOG_FILE") 2>&1

record_failure() {
  FAILURES=$((FAILURES + 1))
  echo "failure[$FAILURES]=$1"
}

record_gap() {
  GAPS=$((GAPS + 1))
  echo "gap[$GAPS]=$1"
}

section() {
  echo
  echo "## $1"
}

run_cmd() {
  echo
  echo "+ $*"
  "$@"
  local code=$?
  echo "exit_code=$code"
  if [ "$code" -ne 0 ]; then
    record_failure "command_failed:$*"
  fi
  return "$code"
}

run_gap_cmd() {
  echo
  echo "+ $*"
  "$@"
  local code=$?
  echo "exit_code=$code"
  if [ "$code" -ne 0 ]; then
    record_gap "command_gap:$*"
  fi
  return "$code"
}

agent_python() {
  (
    cd "$AGENT_DIR" || exit 1
    uv run python "$@"
  )
}

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

echo "# Host Excel Ingest Validation $STAMP"
echo "root=$ROOT_DIR"
echo "agent_dir=$AGENT_DIR"
echo "company_xlsx=$COMPANY_XLSX"
echo "patent_xlsx=$PATENT_XLSX"
echo "log_file=$LOG_FILE"

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export UV_CACHE_DIR

DATABASE_URL_DEFAULTED=false
if [ -z "${DATABASE_URL:-}" ] && [ -z "${DATABASE_URL_TEST:-}" ]; then
  export DATABASE_URL="$DEFAULT_DATABASE_URL"
  DATABASE_URL_DEFAULTED=true
fi
if [ -z "${CHAT_MILVUS_URI:-}" ] && [ -z "${MILVUS_URI:-}" ]; then
  export CHAT_MILVUS_URI="$DEFAULT_MILVUS_URI"
fi

section "Environment"
python - "$COMPANY_XLSX" "$PATENT_XLSX" <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import urlparse


def redacted_dsn(value: str) -> str:
    if not value:
        return "UNSET"
    parsed = urlparse(value.replace("postgresql+psycopg://", "postgresql://", 1))
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    db = parsed.path.lstrip("/")
    return f"{parsed.scheme}://***@{host}{port}/{db}"


company_xlsx = Path(sys.argv[1])
patent_xlsx = Path(sys.argv[2])
print(f"company_xlsx_exists={company_xlsx.is_file()}")
print(f"patent_xlsx_exists={patent_xlsx.is_file()}")
print(f"DATABASE_URL={redacted_dsn(os.environ.get('DATABASE_URL', ''))}")
print(f"DATABASE_URL_TEST={redacted_dsn(os.environ.get('DATABASE_URL_TEST', ''))}")
print(f"CHAT_MILVUS_URI={os.environ.get('CHAT_MILVUS_URI') or 'UNSET'}")
print(f"MILVUS_URI={os.environ.get('MILVUS_URI') or 'UNSET'}")
PY

if [ ! -f "$COMPANY_XLSX" ]; then
  record_failure "company_xlsx_missing"
fi
if [ ! -f "$PATENT_XLSX" ]; then
  record_failure "patent_xlsx_missing"
fi

section "Admin upload capability inventory"
ADMIN_CAPABILITY_OUTPUT="$(python - <<'PY'
from pathlib import Path

upload_py = Path("apps/admin-console/backend/api/upload.py").read_text(encoding="utf-8")
frontend = Path("apps/admin-console/frontend/src/pages/DomainList.tsx").read_text(encoding="utf-8")
checks = {
    "frontend_company_patent_upload_button": 'domain === "company" || domain === "patent"' in frontend,
    "frontend_upload_dry_run_mode": "uploadDryRun" in frontend and "dryRun" in frontend,
    "backend_accepts_company_patent_domain": 'UploadDomain = Literal["company", "patent", "professor", "paper"]' in upload_py,
    "backend_accepts_upload_dry_run": "dry_run" in upload_py and "_run_company_upload_dry_run" in upload_py,
    "backend_executes_professor_pipeline": 'domain == "professor"' in upload_py and 'run_professor_pipeline_v3' in upload_py,
    "backend_executes_company_pipeline": 'domain == "company"' in upload_py and 'import_company_xlsx_to_postgres' in upload_py,
    "backend_executes_patent_pipeline": 'domain == "patent"' in upload_py and 'upsert_patent' in upload_py,
    "backend_persists_upload_result_summary": 'result_summary' in upload_py and 'run_scope' in upload_py,
}
for key, value in checks.items():
    print(f"{key}= {value}")
status = "READY" if all(checks.values()) else "GAP"
print(f"admin_upload_company_patent_status={status}")
PY
)"
echo "$ADMIN_CAPABILITY_OUTPUT"
if ! grep -q "admin_upload_company_patent_status=READY" <<<"$ADMIN_CAPABILITY_OUTPUT"; then
  record_gap "admin_upload_company_patent_not_ready"
fi

section "Company xlsx parser dry-run"
if [ -f "$COMPANY_XLSX" ]; then
  (
    cd "$AGENT_DIR" || exit 1
    run_cmd uv run python scripts/run_company_import_e2e.py \
      --input "$COMPANY_XLSX" \
      --output - \
      --preview-jsonl "$WORK_DIR/company-preview.jsonl"
  )
fi

section "Patent xlsx parser dry-run"
if [ -f "$PATENT_XLSX" ]; then
  (
    cd "$AGENT_DIR" || exit 1
    run_cmd uv run python scripts/run_patent_import_e2e.py \
      --input "$PATENT_XLSX" \
      --output -
  )
fi

section "Company release artifact dry-run"
if [ -f "$COMPANY_XLSX" ]; then
  (
    cd "$AGENT_DIR" || exit 1
    run_cmd uv run python scripts/run_company_release_e2e.py \
      --input "$COMPANY_XLSX" \
      --company-output "$WORK_DIR/company-records.jsonl" \
      --released-output "$WORK_DIR/company-released.jsonl" \
      --report-output -
  )
fi

section "Patent release/link artifact dry-run"
if [ -f "$PATENT_XLSX" ] && [ -f "$COMPANY_XLSX" ]; then
  (
    cd "$AGENT_DIR" || exit 1
    run_cmd uv run python scripts/run_patent_release_e2e.py \
      --patent-input "$PATENT_XLSX" \
      --company-input "$COMPANY_XLSX" \
      --skip-postgres \
      --skip-llm \
      --patent-output "$WORK_DIR/patent-records.jsonl" \
      --released-output "$WORK_DIR/patent-released.jsonl" \
      --report-output -
  )
fi

section "Current Postgres collection/link state"
run_cmd agent_python - <<'PY'
import os
import psycopg

dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
if not dsn:
    print("postgres_probe=FAIL")
    print("reason=DATABASE_URL and DATABASE_URL_TEST are unset")
    raise SystemExit(1)

try:
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database()")
            print("database=", cur.fetchone()[0])
            for table in (
                "company",
                "company_snapshot",
                "patent",
                "company_patent_link",
                "professor_company_role",
                "pipeline_run",
                "source_page",
                "pipeline_issue",
            ):
                cur.execute(f"select count(*) from {table}")
                print(f"{table}_count=", cur.fetchone()[0])
            cur.execute(
                """
                SELECT run_kind, status, triggered_by, count(*)::int
                  FROM pipeline_run
                 WHERE started_at >= now() - interval '14 days'
                 GROUP BY run_kind, status, triggered_by
                 ORDER BY count(*) DESC, run_kind, status, triggered_by
                 LIMIT 20
                """
            )
            for row in cur.fetchall():
                print("recent_pipeline_run=", row)
            cur.execute(
                """
                SELECT count(*)::int
                  FROM source_page
                 WHERE url LIKE 'admin-upload://%'
                """
            )
            print("admin_upload_source_page_count=", cur.fetchone()[0])
            cur.execute(
                """
                SELECT count(*)::int
                  FROM company c
                  JOIN company_snapshot cs ON cs.company_id = c.company_id
                 WHERE c.identity_status != 'inactive'
                   AND (
                     NULLIF(BTRIM(cs.industry), '') IS NULL
                     OR NULLIF(BTRIM(cs.description), '') IS NULL
                   )
                """
            )
            print("company_snapshot_core_field_gap_count=", cur.fetchone()[0])
            cur.execute(
                """
                SELECT count(*)::int
                  FROM patent
                 WHERE COALESCE(status, '') != 'inactive'
                   AND (
                     NULLIF(BTRIM(title_clean), '') IS NULL
                     OR NULLIF(BTRIM(abstract_clean), '') IS NULL
                   )
                """
            )
            print("patent_core_field_gap_count=", cur.fetchone()[0])
except Exception as exc:
    print("postgres_probe=FAIL")
    print("error_type=", type(exc).__name__)
    print("error=", str(exc).splitlines()[0])
    raise SystemExit(1)
PY

section "Current Milvus collection state"
run_cmd agent_python - <<'PY'
import os
from pathlib import Path

from pymilvus import MilvusClient

uri = os.environ.get("CHAT_MILVUS_URI") or os.environ.get("MILVUS_URI")
if not uri:
    print("milvus_probe=FAIL")
    print("reason=CHAT_MILVUS_URI and MILVUS_URI are unset")
    raise SystemExit(1)

try:
    client = MilvusClient(uri=uri)
except Exception as exc:  # noqa: BLE001
    message = str(exc)
    local_path = Path(uri)
    if local_path.exists() and (
        "opened by another program" in message
        or "Open local milvus failed" in message
    ):
        print("milvus_probe=SKIPPED_LOCKED")
        print("uri=", uri)
        print("reason=local Milvus-Lite file is already opened by another process")
        print("error_type=", type(exc).__name__)
        print("error=", message.splitlines()[0])
        raise SystemExit(0)
    print("milvus_probe=FAIL")
    print("uri=", uri)
    print("error_type=", type(exc).__name__)
    print("error=", message.splitlines()[0])
    raise SystemExit(1)

collections = sorted(client.list_collections())
print("milvus_probe=OK")
print("uri=", uri)
print("collections=", ",".join(collections))
for name in ("company_profiles", "patent_profiles", "paper_chunks", "professor_profiles"):
    if name in collections:
        print(f"{name}_stats=", client.get_collection_stats(name))
PY

section "Recent admin upload result summaries"
run_gap_cmd agent_python - <<'PY'
import os
import sys

import psycopg

dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
if not dsn:
    print("recent_admin_upload_summary=GAP")
    print("reason=DATABASE_URL and DATABASE_URL_TEST are unset")
    raise SystemExit(1)

with psycopg.connect(dsn, connect_timeout=5) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
                SELECT DISTINCT ON (run_scope->>'domain')
                       run_scope->>'domain' AS domain,
                       status,
                       items_processed,
                       items_failed,
                       jsonb_typeof(run_scope->'result_summary') AS summary_type,
                       run_scope->'result_summary' AS result_summary,
                       started_at,
                       finished_at
                  FROM pipeline_run
                 WHERE run_kind = 'import_xlsx'
                   AND triggered_by = 'admin-console'
                   AND run_scope->>'domain' IN ('company', 'patent')
                   AND COALESCE((run_scope->>'dry_run')::boolean, false) = false
                   AND started_at >= now() - interval '24 hours'
                 ORDER BY run_scope->>'domain', started_at DESC
            )
            SELECT domain, status, items_processed, items_failed, summary_type,
                   result_summary, started_at, finished_at
              FROM ranked
             ORDER BY domain
            """
        )
        rows = cur.fetchall()

domains = {row[0] for row in rows}
missing = sorted({"company", "patent"} - domains)
has_gap = False
for row in rows:
    domain, status, processed, failed, summary_type, summary, started_at, finished_at = row
    print(
        "recent_admin_upload_summary=",
        domain,
        status,
        "items_processed=",
        processed,
        "items_failed=",
        failed,
        "summary_type=",
        summary_type,
        "started_at=",
        started_at,
        "finished_at=",
        finished_at,
    )
    print("result_summary=", summary)
    if status != "succeeded" or failed not in (0, None) or summary_type != "object":
        has_gap = True

if missing:
    print("recent_admin_upload_summary_missing=", ",".join(missing))
    has_gap = True

if has_gap:
    print("recent_admin_upload_summary=GAP")
    raise SystemExit(1)

print("recent_admin_upload_summary=READY")
PY

section "Done"
echo "log_file=$LOG_FILE"
echo "failures=$FAILURES"
echo "gaps=$GAPS"
if [ "$FAILURES" -eq 0 ] && [ "$GAPS" -eq 0 ]; then
  echo "result=PASS"
  exit 0
fi
if [ "$FAILURES" -eq 0 ]; then
  echo "result=PASS_WITH_GAPS_REVIEW_REQUIRED"
  exit 0
fi
echo "result=FAIL"
exit 1
