#!/usr/bin/env bash
# W2 smoke: real HTTP, scratch port 18291, stub tasks only (no collection, no quota).
# Usage: bash .agents/runs/admin-jobs-console-w2/scratch-18291-smoke.sh
set -u

WT="/home/longxiang/MiroThinker/.worktrees/admin-jobs-console"
OUT="$WT/.agents/runs/admin-jobs-console-w2"
SCRATCH="/var/tmp/w2-jobs-smoke-18291"
API="http://127.0.0.1:18291/api/canonical-v2/admin/jobs"
SETTINGS="$SCRATCH/settings.json"

say() { printf '\n== %s ==\n' "$1"; }
jq_or_cat() { python3 -c "import json,sys;print(json.dumps(json.load(sys.stdin),ensure_ascii=False,indent=2))" 2>/dev/null || cat; }

say "health"
curl -s "http://127.0.0.1:18291/api/health" -o "$OUT/scratch-18291-health.json" -w 'status=%{http_code}\n'

say "page /jobs"
curl -s "http://127.0.0.1:18291/jobs" -o "$OUT/scratch-18291-page-jobs.html" -w 'status=%{http_code}\n'
grep -c "任务运维" "$OUT/scratch-18291-page-jobs.html"

say "list tasks (before any run)"
curl -s "$API" -o "$OUT/scratch-18291-list-before.json" -w 'status=%{http_code}\n'

say "trigger stub-collect-slow"
curl -s -X POST "$API/stub-collect-slow/run" -H 'Content-Type: application/json' \
  -H 'X-Remote-User: smoke-operator' -d '{}' -o "$OUT/scratch-18291-trigger-slow.json" -w 'status=%{http_code}\n'
SLOW_RUN=$(python3 -c "import json;print(json.load(open('$OUT/scratch-18291-trigger-slow.json'))['run_id'])")
echo "run_id=$SLOW_RUN"

say "duplicate trigger while running (expect 409 job_already_running)"
curl -s -X POST "$API/stub-collect-slow/run" -H 'Content-Type: application/json' -d '{}' \
  -o "$OUT/scratch-18291-locked.json" -w 'status=%{http_code}\n'
cat "$OUT/scratch-18291-locked.json"; echo

say "history while running"
curl -s "$API/stub-collect-slow/runs" -o "$OUT/scratch-18291-history-while-running.json" -w 'status=%{http_code}\n'

say "wait for completion, then history"
sleep 5
curl -s "$API/stub-collect-slow/runs" -o "$OUT/scratch-18291-history-slow.json" -w 'status=%{http_code}\n'
python3 - "$OUT/scratch-18291-history-slow.json" <<'PY'
import json, sys
runs = json.load(open(sys.argv[1]))["runs"]
top = runs[0]
print("status=%s duration_ms=%s exit_code=%s operator=%s trigger=%s" % (
    top["status"], top["duration_ms"], top["exit_code"], top["operator"], top["trigger_source"]))
PY

say "two failing runs -> breaker open (expect 409 on the third)"
for i in 1 2; do
  curl -s -X POST "$API/stub-collect-fail/run" -H 'Content-Type: application/json' -d '{}' \
    -o "$OUT/scratch-18291-fail-trigger-$i.json" -w "trigger$i status=%{http_code}\n"
  sleep 1.5
done
curl -s -X POST "$API/stub-collect-fail/run" -H 'Content-Type: application/json' -d '{}' \
  -o "$OUT/scratch-18291-breaker.json" -w 'status=%{http_code}\n'
cat "$OUT/scratch-18291-breaker.json"; echo
FAIL_RUN=$(python3 -c "import json;print(json.load(open('$OUT/scratch-18291-fail-trigger-1.json'))['run_id'])")

say "list after failures (red dot + breaker)"
curl -s "$API" -o "$OUT/scratch-18291-list-after-failures.json" -w 'status=%{http_code}\n'
python3 - "$OUT/scratch-18291-list-after-failures.json" <<'PY'
import json, sys
tasks = {t["task_id"]: t for t in json.load(open(sys.argv[1]))["tasks"]}
task = tasks["stub-collect-fail"]
print("failure_flag=%s breaker_open=%s consecutive_failures=%s last_status=%s" % (
    task["failure_flag"], task["breaker_open"], task["consecutive_failures"], task["last_run"]["status"]))
print("real ops task available:", tasks["ops-milvus-backfill"]["available"],
      tasks["ops-milvus-backfill"]["unavailable_reason"])
PY

say "failure sample (run detail)"
curl -s "$API/runs/$FAIL_RUN" -o "$OUT/scratch-18291-run-detail-failed.json" -w 'status=%{http_code}\n'
python3 - "$OUT/scratch-18291-run-detail-failed.json" <<'PY'
import json, sys
row = json.load(open(sys.argv[1]))
print("status=%s exit_code=%s" % (row["status"], row["exit_code"]))
print("command=", " ".join(row["command"]))
print("stderr_excerpt=", row["stderr_excerpt"].strip().replace("\n", " | "))
PY

say "reset breaker"
curl -s -X POST "$API/stub-collect-fail/reset" -H 'X-Remote-User: smoke-operator' \
  -o "$OUT/scratch-18291-reset.json" -w 'status=%{http_code}\n'
cat "$OUT/scratch-18291-reset.json"; echo

say "switch off -> recorded skip"
python3 - "$SETTINGS" <<'PY'
import json, sys
json.dump({"schema_version": 1, "collection": {"enabled": {"company": False}}}, open(sys.argv[1], "w"))
PY
curl -s -X POST "$API/stub-collect-ok/run" -H 'Content-Type: application/json' -d '{}' \
  -o "$OUT/scratch-18291-skip-switch-off.json" -w 'status=%{http_code}\n'
cat "$OUT/scratch-18291-skip-switch-off.json"; echo

say "quota 0 -> recorded skip"
python3 - "$SETTINGS" <<'PY'
import json, sys
json.dump({"schema_version": 1, "collection": {"enabled": {"company": True}, "max_web_searches_per_run": 0}},
          open(sys.argv[1], "w"))
PY
curl -s -X POST "$API/stub-collect-ok/run" -H 'Content-Type: application/json' -d '{}' \
  -o "$OUT/scratch-18291-skip-quota.json" -w 'status=%{http_code}\n'
cat "$OUT/scratch-18291-skip-quota.json"; echo

say "restore settings -> successful stub run with item count"
python3 - "$SETTINGS" <<'PY'
import json, sys
json.dump({"schema_version": 1, "collection": {"enabled": {"company": True}, "max_web_searches_per_run": 5}},
          open(sys.argv[1], "w"))
PY
curl -s -X POST "$API/stub-collect-ok/run" -H 'Content-Type: application/json' -d '{}' \
  -o "$OUT/scratch-18291-trigger-ok.json" -w 'status=%{http_code}\n'
sleep 2
curl -s "$API/stub-collect-ok/runs" -o "$OUT/scratch-18291-history-ok.json" -w 'status=%{http_code}\n'
python3 - "$OUT/scratch-18291-history-ok.json" <<'PY'
import json, sys
top = json.load(open(sys.argv[1]))["runs"][0]
print("status=%s items_processed=%s duration_ms=%s" % (top["status"], top["items_processed"], top["duration_ms"]))
PY

say "PG degradation (stub + real ops task)"
curl -s -X POST "$API/stub-collect-pg/run" -H 'Content-Type: application/json' -d '{}' \
  -o "$OUT/scratch-18291-pg-stub.json" -w 'status=%{http_code}\n'
curl -s -X POST "$API/ops-milvus-backfill/run" -H 'Content-Type: application/json' \
  -d '{"params": {"domain": "professor"}}' -o "$OUT/scratch-18291-pg-milvus.json" -w 'status=%{http_code}\n'
curl -s -X POST "$API/ops-retrieval-validation/run" -H 'Content-Type: application/json' -d '{}' \
  -o "$OUT/scratch-18291-pg-e2e.json" -w 'status=%{http_code}\n'
cat "$OUT/scratch-18291-pg-stub.json" "$OUT/scratch-18291-pg-milvus.json"; echo

say "parameter whitelist on the real ops task (injection attempt -> 422)"
curl -s -X POST "$API/ops-milvus-backfill-dry-run/run" -H 'Content-Type: application/json' \
  -d '{"params": {"domain": "paper; rm -rf /"}}' -o "$OUT/scratch-18291-injection.json" -w 'status=%{http_code}\n'
cat "$OUT/scratch-18291-injection.json"; echo

say "unknown task (expect 404)"
curl -s -X POST "$API/not-a-task/run" -H 'Content-Type: application/json' -d '{}' \
  -o "$OUT/scratch-18291-unknown.json" -w 'status=%{http_code}\n'

say "final list + history page"
curl -s "$API" -o "$OUT/scratch-18291-list-final.json" -w 'status=%{http_code}\n'
curl -s "$API/stub-collect-ok/runs?status=skipped" -o "$OUT/scratch-18291-history-skipped.json" -w 'status=%{http_code}\n'
python3 - "$OUT/scratch-18291-list-final.json" <<'PY'
import json, sys
tasks = {t["task_id"]: t for t in json.load(open(sys.argv[1]))["tasks"]}
print("declared tasks:", len(tasks))
for task_id in ("stub-collect-ok", "stub-collect-fail", "ops-milvus-backfill"):
    task = tasks[task_id]
    print(" ", task_id, "available=%s" % task["available"], "failure_flag=%s" % task["failure_flag"],
          "breaker_open=%s" % task["breaker_open"], "next_run_at=%s" % bool(task["next_run_at"]))
PY

say "done"
