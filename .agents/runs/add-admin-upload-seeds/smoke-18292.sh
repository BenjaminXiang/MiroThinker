#!/usr/bin/env bash
# W3 real-interaction smoke: port 18292 (18188 is never touched), scratch Postgres on 18293,
# scratch storage, a 3-row synthetic workbook. No production data, no full crawl, no enrichment run.
#
# Usage: bash .agents/runs/add-admin-upload-seeds/smoke-18292.sh
set -u

WT="/home/longxiang/MiroThinker/.worktrees/admin-upload-seeds"
OUT="$WT/.agents/runs/add-admin-upload-seeds"
SCRATCH="/var/tmp/w3-smoke-18292"
API="http://127.0.0.1:18292/api/canonical-v2/admin"
XLSX="$SCRATCH/w3-company-sample.xlsx"
PATENT_XLSX="$SCRATCH/w3-patent-sample.xlsx"
PG_DSN="postgresql://miroflow:w3scratch@127.0.0.1:18293/miroflow_w3"
say() { printf '\n== %s ==\n' "$1"; }
jq_cat() { python3 -c "import json,sys;print(json.dumps(json.load(sys.stdin),ensure_ascii=False,indent=2))" 2>/dev/null || cat; }

say "health + pages"
curl -s "http://127.0.0.1:18292/api/health" -o "$OUT/scratch-18292-health.json" -w 'health status=%{http_code}\n'
for page in upload seeds jobs browse logs admin; do
  curl -s "http://127.0.0.1:18292/$page" -o "$OUT/scratch-18292-page-$page.html" -w "$page status=%{http_code}\n"
done

say "upload ledger before"
curl -s "$API/uploads" -o "$OUT/scratch-18292-uploads-before.json" -w 'status=%{http_code}\n'

say "company upload (commit)"
curl -s -X POST "$API/uploads/company" -H 'X-Remote-User: w3-smoke' -F "file=@$XLSX" \
  -o "$OUT/scratch-18292-upload-commit.json" -w 'status=%{http_code}\n'
jq_cat < "$OUT/scratch-18292-upload-commit.json"
UPLOAD_ID=$(python3 -c "import json;print(json.load(open('$OUT/scratch-18292-upload-commit.json'))['upload']['upload_id'])")
RUN_ID=$(python3 -c "import json;print(json.load(open('$OUT/scratch-18292-upload-commit.json'))['upload']['run_id'])")
echo "upload_id=$UPLOAD_ID run_id=$RUN_ID"

say "duplicate upload of the same bytes (expect 409 duplicate_upload)"
curl -s -X POST "$API/uploads/company" -H 'X-Remote-User: w3-smoke' -F "file=@$XLSX" \
  -o "$OUT/scratch-18292-upload-duplicate.json" -w 'status=%{http_code}\n'
jq_cat < "$OUT/scratch-18292-upload-duplicate.json"

say "wait for the import run"
for _ in $(seq 1 60); do
  sleep 3
  curl -s "$API/uploads/$UPLOAD_ID" -o "$OUT/scratch-18292-upload-detail.json"
  STATE=$(python3 -c "
import json
d=json.load(open('$OUT/scratch-18292-upload-detail.json'))
run=d.get('run') or {}
print(run.get('status'), d['upload']['status'])
" 2>/dev/null)
  echo "  upload=$UPLOAD_ID status: $STATE"
  case "$STATE" in
    succeeded\ *|failed\ *|skipped\ *) break ;;
  esac
done
jq_cat < "$OUT/scratch-18292-upload-detail.json"
curl -s "$API/jobs/runs/$RUN_ID" -o "$OUT/scratch-18292-run-detail.json" -w 'run detail status=%{http_code}\n'

say "domain store after the import (scratch Postgres)"
uv run --no-sync --project "$WT/apps/miroflow-agent" python - <<PY 2>/dev/null | tee "$OUT/scratch-18292-domain-delta.txt"
import os, psycopg
from psycopg.rows import dict_row
with psycopg.connect(os.environ["PG_DSN"], row_factory=dict_row) as conn:
    for table, column in (("company", "name"), ("import_batch", "batch_id"), ("company_enrichment_batch", "batch_id")):
        row = conn.execute(f"select count(*) as total from {table}").fetchone()
        print(f"{table}: {row['total']}")
    rows = conn.execute("select name from company order by name").fetchall()
    for row in rows:
        print("  company:", row["name"])
PY

say "batch progress on the upload detail"
python3 -c "
import json,sys
payload = json.load(open('$OUT/scratch-18292-upload-detail.json'))
print('batch:', json.dumps(payload.get('batch'), ensure_ascii=False))
"

say "patent dry-run upload (no writes, no quota)"
curl -s -X POST "$API/uploads/patent?dry_run=true" -H 'X-Remote-User: w3-smoke' -F "file=@$PATENT_XLSX" \
  -o "$OUT/scratch-18292-upload-dryrun.json" -w 'status=%{http_code}\n'
DRY_UPLOAD=$(python3 -c "import json;print(json.load(open('$OUT/scratch-18292-upload-dryrun.json'))['upload']['upload_id'])")
for _ in $(seq 1 20); do
  sleep 2
  curl -s "$API/uploads/$DRY_UPLOAD" -o "$OUT/scratch-18292-upload-dryrun-detail.json"
  DSTATE=$(python3 -c "import json;print(json.load(open('$OUT/scratch-18292-upload-dryrun-detail.json'))['upload']['status'])")
  case "$DSTATE" in succeeded|failed|skipped) break ;; esac
done
echo "dry-run upload status=$DSTATE"
python3 -c "
import json
d = json.load(open('$OUT/scratch-18292-upload-dryrun-detail.json'))
print('dry-run summary:', json.dumps(d['upload']['summary'], ensure_ascii=False)[:500])
print('dry-run batch rows: dry_run=%s items_processed=%s' % (d['upload']['dry_run'], (d.get('run') or {}).get('items_processed')))
"

say "seed CRUD"
curl -s -X POST "$API/seeds" -H 'Content-Type: application/json' -H 'X-Remote-User: w3-smoke' \
  -d '{"school":"W3 冒烟大学","department":"计算机学院","seed_url":"https://w3-smoke.invalid/roster"}' \
  -o "$OUT/scratch-18292-seed-create.json" -w 'create status=%{http_code}\n'
SEED_ID=$(python3 -c "import json;print(json.load(open('$OUT/scratch-18292-seed-create.json'))['id'])")
echo "seed_id=$SEED_ID"
curl -s "$API/seeds" -o "$OUT/scratch-18292-seed-list.json" -w 'list status=%{http_code}\n'
curl -s -X PUT "$API/seeds/$SEED_ID" -H 'Content-Type: application/json' \
  -d '{"school":"W3 冒烟大学（改）","department":"计算机学院","seed_url":"https://w3-smoke.invalid/roster"}' \
  -o "$OUT/scratch-18292-seed-update.json" -w 'update status=%{http_code}\n'

say "seed preview trigger through the gate"
curl -s -X POST "$API/seeds/$SEED_ID/trigger" -H 'Content-Type: application/json' \
  -H 'X-Remote-User: w3-smoke' -d '{"mode":"preview"}' \
  -o "$OUT/scratch-18292-seed-trigger.json" -w 'trigger status=%{http_code}\n'
jq_cat < "$OUT/scratch-18292-seed-trigger.json"
SEED_RUN=$(python3 -c "import json;print(json.load(open('$OUT/scratch-18292-seed-trigger.json')).get('run_id',''))" 2>/dev/null)

say "sample trigger without a limit (expect 422)"
curl -s -X POST "$API/seeds/$SEED_ID/trigger" -H 'Content-Type: application/json' \
  -d '{"mode":"sample"}' -o "$OUT/scratch-18292-seed-sample-nolimit.json" -w 'status=%{http_code}\n'

say "wait for the seed refresh run, then poll its history"
sleep 12
curl -s "$API/seeds/$SEED_ID/runs" -o "$OUT/scratch-18292-seed-runs.json" -w 'runs status=%{http_code}\n'
jq_cat < "$OUT/scratch-18292-seed-runs.json"
curl -s "$API/jobs/runs/$SEED_RUN" -o "$OUT/scratch-18292-seed-run-detail.json" -w 'seed run detail status=%{http_code}\n'

say "delete the smoke seed"
curl -s -X DELETE "$API/seeds/$SEED_ID" -o "$OUT/scratch-18292-seed-delete.json" -w 'delete status=%{http_code}\n'
curl -s "$API/seeds/$SEED_ID" -o "$OUT/scratch-18292-seed-after-delete.json" -w 'get after delete status=%{http_code}\n'

say "upload ledger after"
curl -s "$API/uploads" -o "$OUT/scratch-18292-uploads-after.json" -w 'status=%{http_code}\n'
python3 - "$OUT/scratch-18292-uploads-after.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
print("total:", payload["total"])
for item in payload["uploads"]:
    print(f"  {item['upload_id'][:8]} {item['domain']:9} {item['status']:10} dry_run={item['dry_run']} {item['filename']}")
PY

say "quota counters recorded on the runs"
python3 - "$OUT/scratch-18292-run-detail.json" "$OUT/scratch-18292-seed-run-detail.json" <<'PY'
import json, sys
for path in sys.argv[1:]:
    try:
        payload = json.load(open(path))
    except Exception as exc:
        print(f"{path}: {exc}")
        continue
    summary = payload.get("summary") or {}
    print(f"{path.split('/')[-1]}: status={payload.get('status')} quota={summary.get('quota')} "
          f"job_summary={summary.get('job_summary')}")
    if payload.get("stderr_excerpt"):
        print("  stderr tail:", payload["stderr_excerpt"][-200:].replace("\n", " | "))
PY
