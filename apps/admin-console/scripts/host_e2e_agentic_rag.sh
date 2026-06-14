#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ADMIN_DIR="$ROOT_DIR/apps/admin-console"
LOG_DIR="$ROOT_DIR/docs/source_backfills"
STAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
LOG_FILE="${HOST_E2E_LOG_FILE:-$LOG_DIR/host-e2e-agentic-rag-$STAMP.txt}"
BASE_URL="${HOST_E2E_BASE_URL:-}"
PORT="${HOST_E2E_PORT:-}"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/mirothinker-uv-cache-status}"
DEFAULT_DATABASE_URL="postgresql://miroflow:miroflow@localhost:15432/miroflow_real"
DEFAULT_MILVUS_URI="$ROOT_DIR/apps/miroflow-agent/milvus.db"
FAILURES=0

mkdir -p "$LOG_DIR"

exec > >(tee "$LOG_FILE") 2>&1

record_failure() {
  FAILURES=$((FAILURES + 1))
  echo "failure[$FAILURES]=$1"
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

port_is_free() {
  python - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.5)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(1)
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

echo "# Host Agentic RAG E2E $STAMP"
echo "root=$ROOT_DIR"
echo "admin_dir=$ADMIN_DIR"
echo "log_file=$LOG_FILE"
echo

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
python - <<'PY'
import os
from urllib.parse import urlparse


def redacted_dsn(value: str) -> str:
    if not value:
        return "UNSET"
    parsed = urlparse(value.replace("postgresql+psycopg://", "postgresql://", 1))
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    db = parsed.path.lstrip("/")
    return f"{parsed.scheme}://***@{host}{port}/{db}"


for key in ("DATABASE_URL", "DATABASE_URL_TEST"):
    print(f"{key}={redacted_dsn(os.environ.get(key, ''))}")
for key in (
    "CHAT_MILVUS_URI",
    "MILVUS_URI",
    "MILVUS_USE_REAL_CLIENT",
    "CHAT_USE_RETRIEVAL_SERVICE",
):
    value = os.environ.get(key)
    if key in {"CHAT_MILVUS_URI", "MILVUS_URI", "CHAT_USE_RETRIEVAL_SERVICE"}:
        suffix = f"={value}" if value else ""
    else:
        suffix = f"={value}" if value else ""
    print(f"{key}={'SET' if value else 'UNSET'}{suffix}")
for key in ("SERPER_API_KEY", "API_KEY", "LOCAL_LLM_API_KEY"):
    print(f"{key}_present={bool(os.environ.get(key))}")
for key in ("http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","ALL_PROXY"):
    print(f"{key}_present={bool(os.environ.get(key))}")
PY

section "LLM profile and connectivity"
run_cmd admin_python - <<'PY'
import socket
from urllib.parse import urlparse

from openai import OpenAI
from src.data_agents.professor.llm_profiles import (
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)

s = resolve_professor_llm_settings(None, include_profile=True)
base_url = s.get("local_llm_base_url") or ""
model = s.get("local_llm_model") or ""
api_key = s.get("local_llm_api_key") or ""
parsed = urlparse(base_url)
port = parsed.port or (443 if parsed.scheme == "https" else 80 if parsed.scheme == "http" else None)
print("profile=", s.get("llm_profile"))
print("base_url_scheme=", parsed.scheme)
print("base_url_host=", parsed.hostname)
print("base_url_port=", port)
print("base_url_path=", parsed.path)
print("model=", model)
print("api_key_present=", bool(api_key))
if parsed.hostname and port:
    try:
        with socket.create_connection((parsed.hostname, port), timeout=5):
            print("tcp_probe=OK")
    except Exception as exc:
        print("tcp_probe=FAIL")
        print("tcp_error_type=", type(exc).__name__)
        print("tcp_error=", str(exc).splitlines()[0])
else:
    print("tcp_probe=SKIPPED")

client = OpenAI(base_url=base_url, api_key=api_key or "EMPTY", timeout=12.0)
try:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        temperature=0.0,
        max_tokens=8,
        extra_body=build_non_thinking_extra_body(model),
    )
    print("openai_probe=OK")
    print("openai_text=", (resp.choices[0].message.content or "")[:120].replace("\n", " "))
except Exception as exc:
    print("openai_probe=FAIL")
    print("openai_error_type=", type(exc).__name__)
    print("openai_error=", str(exc).splitlines()[0])
    cause = exc.__cause__
    depth = 0
    while cause is not None and depth < 5:
        print(f"cause_{depth}_type=", type(cause).__name__)
        print(f"cause_{depth}_repr=", repr(cause)[:500])
        cause = cause.__cause__
        depth += 1
    raise SystemExit(1)
PY

section "Postgres probe"
run_cmd admin_python - <<'PY'
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
            for table in ("professor", "company", "paper", "patent"):
                cur.execute(f"select count(*) from {table}")
                print(f"{table}_count=", cur.fetchone()[0])
            cur.execute(
                """
                SELECT p.professor_id, c.company_id, c.canonical_name, pcr.role_type, pcr.link_status
                  FROM professor p
                  JOIN professor_company_role pcr ON pcr.professor_id = p.professor_id
                  JOIN company c ON c.company_id = pcr.company_id
                 WHERE (p.canonical_name = '丁文伯' OR p.canonical_name_zh = '丁文伯')
                   AND pcr.link_status IN ('verified', 'candidate')
                   AND c.identity_status != 'inactive'
                 ORDER BY c.canonical_name ASC
                """
            )
            rows = cur.fetchall()
            print("ding_company_role_count=", len(rows))
            for row in rows[:5]:
                print(
                    "ding_company_role=",
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                )
    print("postgres_probe=OK")
except Exception as exc:
    print("postgres_probe=FAIL")
    print("error_type=", type(exc).__name__)
    print("error=", str(exc).splitlines()[0])
    raise SystemExit(1)
PY

section "Milvus probe"
run_cmd admin_python - <<'PY'
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
    collections = sorted(client.list_collections())
    print("milvus_probe=OK")
    print("uri=", uri)
    print("collections=", ",".join(collections))
    for name in ("professor_profiles", "company_profiles", "paper_chunks", "patent_profiles"):
        if name in collections:
            try:
                stats = client.get_collection_stats(name)
                print(f"{name}_stats=", stats)
            except Exception as exc:
                print(f"{name}_stats_error=", type(exc).__name__, str(exc).splitlines()[0])
except Exception as exc:
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
    print("error_type=", type(exc).__name__)
    print("error=", message.splitlines()[0])
    raise SystemExit(1)
PY

section "Classifier 100-case benchmark"
pushd "$ADMIN_DIR" >/dev/null || exit 1
run_cmd timeout 240s uv run pytest tests/test_classifier_benchmark.py -m requires_classifier_llm -v --tb=short
popd >/dev/null || exit 1

section "HTTP chat E2E"
SERVER_PID=""
HEALTH_READY=false
if [ -z "$BASE_URL" ]; then
  if [ -z "$PORT" ]; then
    PORT="$(choose_free_port)"
    echo "selected_free_port=$PORT"
  elif ! port_is_free "$PORT"; then
    PORT="$(choose_free_port)"
    echo "requested_port_occupied=true"
    echo "selected_free_port=$PORT"
  fi
  BASE_URL="http://127.0.0.1:$PORT"
  (
    cd "$ADMIN_DIR" || exit 1
    uv run uvicorn backend.main:app --host 127.0.0.1 --port "$PORT"
  ) &
  SERVER_PID=$!
  echo "started_uvicorn_pid=$SERVER_PID"
else
  echo "using_external_base_url=$BASE_URL"
fi

for _ in $(seq 1 45); do
  if [ -n "$SERVER_PID" ] && ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    echo "server_process_exited_before_health=true"
    wait "$SERVER_PID" >/dev/null 2>&1 || true
    record_failure "uvicorn_exited_before_health"
    break
  fi
  HEALTH_BODY="$(curl -fsS -m 2 "$BASE_URL/api/health" 2>/dev/null || true)"
  if health_ok "$HEALTH_BODY"; then
    echo "health=OK"
    echo "health_body=$HEALTH_BODY"
    HEALTH_READY=true
    break
  fi
  sleep 1
done

if [ "$HEALTH_READY" != true ]; then
  echo "health=FAIL"
  echo "health_body=${HEALTH_BODY:-}"
  record_failure "health_check_failed"
fi

COOKIE_FILE="$(mktemp)"
post_chat() {
  local label="$1"
  local query="$2"
  local expected_query_type="${3:-}"
  local min_citations="${4:-0}"
  local zero_citation_answer_pattern="${5:-}"
  echo
  echo "### $label"
  echo "query=$query"
  echo "expected_query_type=${expected_query_type:-ANY}"
  echo "min_citations=$min_citations"
  echo "zero_citation_answer_pattern=${zero_citation_answer_pattern:-ANY}"
  if [ "$HEALTH_READY" != true ]; then
    echo "skipped=true"
    echo "reason=health_check_not_ready"
    record_failure "chat_skipped:$label"
    return
  fi
  local body
  body="$(python - "$query" <<'PY'
import json
import sys

print(json.dumps({"query": sys.argv[1]}, ensure_ascii=False))
PY
)"
  local out
  out="$(mktemp)"
  local code
  code="$(curl -sS -m 30 -w "%{http_code}" -o "$out" -c "$COOKIE_FILE" -b "$COOKIE_FILE" \
    -H "Content-Type: application/json" \
    -X POST "$BASE_URL/api/chat" \
    -d "$body" || true)"
  echo "http_status=$code"
  if [ "$code" != "200" ]; then
    record_failure "chat_http_status:$label:$code"
  fi
  python - "$out" "$expected_query_type" "$min_citations" "$zero_citation_answer_pattern" <<'PY'
import json
import re
import sys

path = sys.argv[1]
expected_query_type = sys.argv[2]
min_citations = int(sys.argv[3])
zero_citation_answer_pattern = sys.argv[4]
text = open(path, encoding="utf-8").read()
print("raw=", text[:1000].replace("\n", " "))
try:
    data = json.loads(text)
except Exception as exc:
    print("json_parse=FAIL", type(exc).__name__, str(exc).splitlines()[0])
    raise SystemExit(1)
if not isinstance(data, dict):
    print("json_parse=FAIL non_object")
    raise SystemExit(1)
query_type = data.get("query_type")
citations = data.get("citations") or []
answer_text = str(data.get("answer_text") or "")
print("query_type=", query_type)
print("answer_style=", data.get("answer_style"))
print("citations_count=", len(citations))
print("evidence_count=", len(data.get("evidence") or []))
print("answer_prefix=", answer_text[:300].replace("\n", " "))
failed = False
if "answer_text" not in data or not answer_text.strip():
    print("chat_payload=FAIL missing_answer_text")
    failed = True
if expected_query_type and query_type != expected_query_type:
    print(
        "chat_payload=FAIL query_type_mismatch "
        f"expected={expected_query_type} actual={query_type}"
    )
    failed = True
if len(citations) < min_citations:
    print(
        "chat_payload=FAIL insufficient_citations "
        f"expected_min={min_citations} actual={len(citations)}"
    )
    failed = True
if len(citations) == 0 and zero_citation_answer_pattern:
    if not re.search(zero_citation_answer_pattern, answer_text):
        print(
            "chat_payload=FAIL zero_citation_answer_mismatch "
            f"pattern={zero_citation_answer_pattern}"
        )
        failed = True
if failed:
    raise SystemExit(1)
PY
  local parse_code=$?
  if [ "$parse_code" -ne 0 ]; then
    record_failure "chat_payload:$label"
  fi
  rm -f "$out"
}

post_chat "B-company" "深圳哪些公司做激光雷达" "B_company_topic_search" 1
post_chat "B-paper" "近两年具身智能方向的论文有哪些" "B_paper_topic_search" 1
post_chat "B-patent" "哪些专利和柔性触觉传感有关" "B_patent_topic_search" 1
post_chat "A-professor" "介绍清华的丁文伯" "A_prof_profile" 1
post_chat "C-followup-company" "他参与创立了哪些企业" "C_cross_domain_related" 0 "暂未收录|未找到|证据不足|没有.*证据"

rm -f "$COOKIE_FILE"
if [ -n "$SERVER_PID" ]; then
  kill "$SERVER_PID" >/dev/null 2>&1 || true
  wait "$SERVER_PID" >/dev/null 2>&1 || true
fi

section "Done"
echo "log_file=$LOG_FILE"
echo "failures=$FAILURES"
if [ "$FAILURES" -eq 0 ]; then
  echo "result=PASS"
  exit 0
fi
echo "result=FAIL"
exit 1
