#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ADMIN_DIR="$ROOT_DIR/apps/admin-console"
LOG_DIR="$ROOT_DIR/docs/source_backfills"
STAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
LOG_FILE="${HOST_ADMIN_UPLOAD_E2E_LOG_FILE:-$LOG_DIR/host-e2e-admin-upload-$STAMP.txt}"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/mirothinker-uv-cache-status}"
BASE_URL="${HOST_ADMIN_UPLOAD_E2E_BASE_URL:-}"
PORT="${HOST_ADMIN_UPLOAD_E2E_PORT:-}"
POLL_SECONDS="${HOST_ADMIN_UPLOAD_E2E_POLL_SECONDS:-300}"
MODE="${HOST_ADMIN_UPLOAD_E2E_MODE:-dry-run}"
COMPANY_XLSX="${HOST_EXCEL_COMPANY_XLSX:-$ROOT_DIR/docs/专辑项目导出1768807339.xlsx}"
PATENT_XLSX="${HOST_EXCEL_PATENT_XLSX:-$ROOT_DIR/docs/2025-12-05 专利.xlsx}"
DEFAULT_DATABASE_URL="postgresql://miroflow:miroflow@localhost:15432/miroflow_real"
DEFAULT_MILVUS_URI="$ROOT_DIR/apps/miroflow-agent/milvus.db"
WORK_DIR="$(mktemp -d /tmp/mirothinker-admin-upload-e2e.XXXXXX)"
FAILURES=0
GAPS=0
SERVER_PID=""
COMPANY_TASK_ID=""
PATENT_TASK_ID=""

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

admin_python() {
  (
    cd "$ADMIN_DIR" || exit 1
    PYTHONPATH="$ROOT_DIR/apps/miroflow-agent${PYTHONPATH:+:$PYTHONPATH}" uv run python "$@"
  )
}

choose_free_port() {
  python - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
}

health_ok() {
  python - "$1" <<'PY'
import json
import sys

try:
    data = json.loads(sys.argv[1])
except Exception:
    raise SystemExit(1)
if data != {"status": "ok"}:
    raise SystemExit(1)
PY
}

wait_for_health() {
  local deadline=$((SECONDS + 60))
  while [ "$SECONDS" -lt "$deadline" ]; do
    local body
    body="$(curl -fsS "$BASE_URL/api/health" 2>/dev/null || true)"
    if [ -n "$body" ] && health_ok "$body"; then
      echo "admin_health=OK"
      return 0
    fi
    if [ -n "$SERVER_PID" ] && ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "admin_server_exit=EARLY"
      return 1
    fi
    sleep 1
  done
  echo "admin_health=TIMEOUT"
  return 1
}

cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

task_json_value() {
  python - "$1" "$2" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)
value = data.get(key)
print("" if value is None else value)
PY
}

poll_task() {
  local domain="$1"
  local task_id="$2"
  local detail_file="$WORK_DIR/$domain-task-detail.json"
  local deadline=$((SECONDS + POLL_SECONDS))
  local status=""

  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -fsS "$BASE_URL/api/pipeline/runs/$task_id" -o "$detail_file"; then
      status="$(task_json_value "$detail_file" status)"
      local processed failed
      processed="$(task_json_value "$detail_file" items_processed)"
      failed="$(task_json_value "$detail_file" items_failed)"
      echo "poll domain=$domain task_id=$task_id status=$status items_processed=$processed items_failed=$failed"
      case "$status" in
        succeeded|partial|failed)
          break
          ;;
      esac
    else
      echo "poll domain=$domain task_id=$task_id status=DETAIL_FETCH_FAILED"
    fi
    sleep 2
  done

  echo "task_detail_file=$detail_file"
  cat "$detail_file" 2>/dev/null || true
  echo

  if [ "$status" = "partial" ] && [ "$MODE" = "dry-run" ] && [[ "$domain" != milvus-* ]]; then
    record_gap "dry_run_task_partial:$domain:$task_id"
    return 0
  fi

  if [ "$status" != "succeeded" ]; then
    record_failure "upload_task_not_succeeded:$domain:$task_id:$status"
    return 1
  fi
  return 0
}

upload_domain() {
  local domain="$1"
  local file_path="$2"
  local response_file="$WORK_DIR/$domain-upload-response.json"
  local upload_url="$BASE_URL/api/upload/$domain"
  if [ "$MODE" = "dry-run" ]; then
    upload_url="$upload_url?dry_run=true"
  fi

  section "Upload $domain"
  echo "upload_mode=$MODE"
  echo "upload_file=$file_path"
  if [ ! -f "$file_path" ]; then
    record_failure "upload_file_missing:$domain:$file_path"
    return 1
  fi

  if ! curl -fsS \
    -X POST \
    -F "file=@${file_path};filename=$(basename "$file_path")" \
    "$upload_url" \
    -o "$response_file"; then
    record_failure "upload_request_failed:$domain"
    cat "$response_file" 2>/dev/null || true
    return 1
  fi

  echo "upload_response_file=$response_file"
  cat "$response_file"
  echo

  local task_id
  task_id="$(task_json_value "$response_file" task_id)"
  if [ -z "$task_id" ]; then
    record_failure "upload_response_missing_task_id:$domain"
    return 1
  fi
  echo "task_id=$task_id"
  if [ "$domain" = "company" ]; then
    COMPANY_TASK_ID="$task_id"
  elif [ "$domain" = "patent" ]; then
    PATENT_TASK_ID="$task_id"
  fi
  poll_task "$domain" "$task_id"
}

trigger_milvus_backfill_dry_run() {
  local domain="$1"
  local parent_task_id="$2"
  local response_file="$WORK_DIR/$domain-milvus-backfill-response.json"

  section "Trigger Milvus backfill dry-run for $domain"
  if [ -z "$parent_task_id" ]; then
    record_failure "missing_parent_task_id_for_milvus_backfill:$domain"
    return 1
  fi

  if ! curl -fsS \
    -X POST \
    "$BASE_URL/api/pipeline/runs/$parent_task_id/milvus-backfill?dry_run=true" \
    -o "$response_file"; then
    record_failure "milvus_backfill_trigger_failed:$domain:$parent_task_id"
    cat "$response_file" 2>/dev/null || true
    return 1
  fi

  echo "milvus_backfill_response_file=$response_file"
  cat "$response_file"
  echo

  local task_id
  task_id="$(task_json_value "$response_file" task_id)"
  if [ -z "$task_id" ]; then
    record_failure "milvus_backfill_response_missing_task_id:$domain"
    return 1
  fi
  echo "milvus_backfill_task_id=$task_id"
  poll_task "milvus-$domain" "$task_id"
}

verify_dry_run_pipeline_issues() {
  section "Dry-run data quality issue details"
  if [ "$MODE" != "dry-run" ]; then
    echo "dry_run_issue_check=SKIPPED mode=$MODE"
    return 0
  fi

  run_cmd admin_python - "$COMPANY_TASK_ID" "$PATENT_TASK_ID" <<'PY'
import sys
import psycopg
import os

company_task_id, patent_task_id = sys.argv[1], sys.argv[2]
dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
if not dsn:
    print("dry_run_issue_check=FAIL")
    print("reason=DATABASE_URL and DATABASE_URL_TEST are unset")
    raise SystemExit(1)

task_ids = [task_id for task_id in (company_task_id, patent_task_id) if task_id]
missing_issue_details = []
with psycopg.connect(dsn, connect_timeout=5) as conn:
    with conn.cursor() as cur:
        for task_id in task_ids:
            cur.execute(
                """
                SELECT run_scope->>'domain' AS domain,
                       run_scope->'result_summary'->'data_quality_issues' AS issues
                  FROM pipeline_run
                 WHERE run_id = %s
                """,
                (task_id,),
            )
            row = cur.fetchone()
            if row is None:
                missing_issue_details.append(f"task_missing:{task_id}")
                continue
            domain, issues = row
            issues = issues or []
            print(
                "dry_run_result_summary_issues=",
                domain,
                "task_id=",
                task_id,
                "issue_count=",
                len(issues),
                "issues=",
                issues,
            )
            for issue in issues:
                if (
                    issue.get("issue_type") == "missing_company_name"
                    and not issue.get("recommended_action")
                ):
                    missing_issue_details.append(
                        f"recommended_action_missing_in_summary:{domain}:{task_id}:{issue.get('issue_type')}"
                    )
                cur.execute(
                    """
                    SELECT issue_id::text, severity, description,
                           evidence_snapshot, reported_at
                      FROM pipeline_issue
                     WHERE reported_by = 'admin_upload_dry_run'
                       AND institution = %s
                       AND evidence_snapshot->>'issue_type' = %s
                       AND evidence_snapshot->>'task_id' = %s
                       AND resolved = false
                     ORDER BY reported_at DESC
                     LIMIT 5
                    """,
                    (
                        f"admin-upload:{domain}:{task_id}",
                        issue.get("issue_type"),
                        task_id,
                    ),
                )
                rows = cur.fetchall()
                print(
                    "dry_run_pipeline_issue=",
                    domain,
                    "task_id=",
                    task_id,
                    "issue_type=",
                    issue.get("issue_type"),
                    "rows=",
                    rows,
                )
                if not rows:
                    missing_issue_details.append(
                        f"pipeline_issue_missing:{domain}:{task_id}:{issue.get('issue_type')}"
                    )
                    continue
                for _issue_id, _severity, _description, evidence, _reported_at in rows:
                    if (
                        issue.get("issue_type") == "missing_company_name"
                        and not (evidence or {}).get("recommended_action")
                    ):
                        missing_issue_details.append(
                            f"recommended_action_missing_in_pipeline_issue:{domain}:{task_id}:{issue.get('issue_type')}"
                        )

if missing_issue_details:
    print("dry_run_issue_check=FAIL")
    print("missing_issue_details=", ",".join(missing_issue_details))
    raise SystemExit(1)

print("dry_run_issue_check=READY")
PY
}

verify_company_source_row_preview() {
  section "Company issue source-row preview"
  if [ "$MODE" != "dry-run" ]; then
    echo "source_row_preview_check=SKIPPED mode=$MODE"
    return 0
  fi
  if [ -z "$COMPANY_TASK_ID" ]; then
    record_failure "source_row_preview_missing_company_task_id"
    return 1
  fi

  local issues_file="$WORK_DIR/company-pipeline-issues.json"
  local preview_file="$WORK_DIR/company-source-row-preview.json"
  local issue_id
  local issue_rows_file="$WORK_DIR/company-pipeline-issue-rows.txt"

  if ! curl -fsS \
    "$BASE_URL/api/pipeline-issues?reported_by=admin_upload_dry_run&task_id=$COMPANY_TASK_ID&domain=company&issue_type=missing_company_name&page_size=5" \
    -o "$issues_file"; then
    record_failure "source_row_preview_issue_list_failed:$COMPANY_TASK_ID"
    return 1
  fi

  issue_id="$(python - "$issues_file" "$issue_rows_file" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
rows_path = Path(sys.argv[2])
items = payload.get("items") or []
if not items:
    print("")
    raise SystemExit(0)
issue = items[0]
source_rows = issue.get("evidence_snapshot", {}).get("source_rows") or []
rows_path.write_text(",".join(str(row) for row in source_rows), encoding="utf-8")
print(issue.get("issue_id") or "")
PY
)"
  if [ -z "$issue_id" ]; then
    echo "source_row_preview_check=SKIPPED no_missing_company_name_issue"
    return 0
  fi
  echo "source_row_preview_issue_id=$issue_id"

  if ! curl -fsS "$BASE_URL/api/pipeline-issues/$issue_id/source-rows" \
    -o "$preview_file"; then
    record_failure "source_row_preview_fetch_failed:$issue_id"
    return 1
  fi

  run_cmd python - "$preview_file" "$issue_rows_file" "$COMPANY_TASK_ID" <<'PY'
import json
import sys
from pathlib import Path

preview = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_rows = [
    int(item)
    for item in Path(sys.argv[2]).read_text(encoding="utf-8").split(",")
    if item
]
expected_task_id = sys.argv[3]
actual_rows = [row.get("row_number") for row in preview.get("rows") or []]
print("source_row_preview_task_id=", preview.get("task_id"))
print("source_row_preview_sheet=", preview.get("sheet_name"))
print("source_row_preview_header_row=", preview.get("header_row_number"))
print("source_row_preview_rows=", actual_rows)
print("source_row_preview_warning=", preview.get("warning"))
failed = False
if preview.get("task_id") != expected_task_id:
    print("source_row_preview_check=FAIL task_id_mismatch")
    failed = True
if actual_rows != expected_rows[:50]:
    print("source_row_preview_check=FAIL source_rows_mismatch")
    failed = True
for row in preview.get("rows") or []:
    cells = row.get("cells") or []
    if not cells:
        print("source_row_preview_check=FAIL empty_cells")
        failed = True
if failed:
    raise SystemExit(1)
print("source_row_preview_check=READY")
PY
}

db_snapshot() {
  local label="$1"
  section "$label"
  run_cmd admin_python - <<'PY'
import os
from urllib.parse import urlparse

import psycopg


def redacted_dsn(value: str) -> str:
    if not value:
        return "UNSET"
    parsed = urlparse(value.replace("postgresql+psycopg://", "postgresql://", 1))
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    db = parsed.path.lstrip("/")
    return f"{parsed.scheme}://***@{host}{port}/{db}"


dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
print("DATABASE_URL=", redacted_dsn(os.environ.get("DATABASE_URL", "")))
print("DATABASE_URL_TEST=", redacted_dsn(os.environ.get("DATABASE_URL_TEST", "")))
if not dsn:
    print("postgres_probe=FAIL")
    print("reason=DATABASE_URL and DATABASE_URL_TEST are unset")
    raise SystemExit(1)

with psycopg.connect(dsn, connect_timeout=5) as conn:
    with conn.cursor() as cur:
        cur.execute("select current_database()")
        print("database=", cur.fetchone()[0])
        for table in (
            "company",
            "company_snapshot",
            "patent",
            "company_patent_link",
            "pipeline_run",
            "source_page",
        ):
            cur.execute(f"select count(*) from {table}")
            print(f"{table}_count=", cur.fetchone()[0])
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
            SELECT run_id, run_kind, status, run_scope->>'domain' AS domain,
                   triggered_by, items_processed, items_failed, started_at, finished_at
              FROM pipeline_run
             WHERE triggered_by = 'admin-console'
             ORDER BY started_at DESC
             LIMIT 8
            """
        )
        for row in cur.fetchall():
            print("recent_admin_pipeline_run=", row)
PY
}

echo "# Host Admin Upload E2E $STAMP"
echo "root=$ROOT_DIR"
echo "admin_dir=$ADMIN_DIR"
echo "log_file=$LOG_FILE"
echo "work_dir=$WORK_DIR"
echo "company_xlsx=$COMPANY_XLSX"
echo "patent_xlsx=$PATENT_XLSX"

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export UV_CACHE_DIR
export MILVUS_USE_REAL_CLIENT="${MILVUS_USE_REAL_CLIENT:-1}"
export CHAT_USE_RETRIEVAL_SERVICE="${CHAT_USE_RETRIEVAL_SERVICE:-on}"

DATABASE_URL_DEFAULTED=false
if [ -z "${DATABASE_URL:-}" ] && [ -z "${DATABASE_URL_TEST:-}" ]; then
  export DATABASE_URL="$DEFAULT_DATABASE_URL"
  DATABASE_URL_DEFAULTED=true
fi

CHAT_MILVUS_URI_DEFAULTED=false
if [ -z "${CHAT_MILVUS_URI:-}" ] && [ -z "${MILVUS_URI:-}" ]; then
  export CHAT_MILVUS_URI="$DEFAULT_MILVUS_URI"
  CHAT_MILVUS_URI_DEFAULTED=true
fi

section "Environment"
echo "DATABASE_URL_DEFAULTED=$DATABASE_URL_DEFAULTED"
echo "CHAT_MILVUS_URI_DEFAULTED=$CHAT_MILVUS_URI_DEFAULTED"
echo "DEFAULT_MILVUS_URI_EXISTS=$([ -f "$DEFAULT_MILVUS_URI" ] && echo true || echo false)"
echo "POLL_SECONDS=$POLL_SECONDS"
echo "HOST_ADMIN_UPLOAD_E2E_MODE=$MODE"

case "$MODE" in
  apply|dry-run)
    ;;
  *)
    record_failure "invalid_host_admin_upload_e2e_mode:$MODE"
    ;;
esac

if [ -z "$BASE_URL" ]; then
  if [ -z "$PORT" ]; then
    PORT="$(choose_free_port)"
  fi
  BASE_URL="http://127.0.0.1:$PORT"
  section "Start admin server"
  echo "base_url=$BASE_URL"
  (
    cd "$ADMIN_DIR" || exit 1
    PYTHONPATH="$ROOT_DIR/apps/miroflow-agent${PYTHONPATH:+:$PYTHONPATH}" \
      uv run uvicorn backend.main:app --host 127.0.0.1 --port "$PORT" --log-level info
  ) &
  SERVER_PID=$!
  echo "server_pid=$SERVER_PID"
else
  section "Use existing admin server"
  echo "base_url=$BASE_URL"
fi

if ! wait_for_health; then
  record_failure "admin_health_failed:$BASE_URL"
fi

db_snapshot "Before upload DB snapshot"
upload_domain "company" "$COMPANY_XLSX"
upload_domain "patent" "$PATENT_XLSX"
verify_dry_run_pipeline_issues
verify_company_source_row_preview
trigger_milvus_backfill_dry_run "company" "$COMPANY_TASK_ID"
trigger_milvus_backfill_dry_run "patent" "$PATENT_TASK_ID"

section "Recent admin upload API runs"
curl -fsS "$BASE_URL/api/pipeline/runs?triggered_by=admin-console&limit=8" || record_failure "list_pipeline_runs_failed"
echo

db_snapshot "After upload DB snapshot"

section "Result"
echo "failures=$FAILURES"
echo "gaps=$GAPS"
echo "log_file=$LOG_FILE"
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
