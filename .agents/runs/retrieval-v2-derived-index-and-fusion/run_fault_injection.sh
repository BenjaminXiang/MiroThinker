#!/usr/bin/env bash
# Live fault injection for the rerank lane on 18188 (serial — one serving
# process only, embedded Milvus Lite cannot be opened twice).
#
#   run_fault_injection.sh <tag> <expected-mode>
#
#   tag             label written into the artifact names (e.g. stub / refused)
#   expected-mode   stub     -> endpoint answers with a malformed payload
#                   refused  -> endpoint refuses the connection
#
# The drop-in switch itself is done by switch_rerank.sh stub|off outside this
# script; this script only drives a real /api/chat/stream turn and records
# whether the answer path survived and whether the trace shows the fallback.
# Never echoes the credential.
set -euo pipefail

TAG="${1:?usage: run_fault_injection.sh <tag> <stub|refused>}"
MODE="${2:?usage: run_fault_injection.sh <tag> <stub|refused>}"
OUT="$HOME/MiroThinker/.agents/runs/retrieval-v2-derived-index-and-fusion"
STAMP="$(date '+%Y%m%d-%H%M%S')"
BODY="$OUT/fault-injection-$TAG-$STAMP.json"
TXT="$OUT/fault-injection-$TAG-$STAMP.txt"
JAR="$(mktemp /tmp/faultinj.XXXXXX.jar)"
QUERY="${FAULT_QUERY:-深圳有哪些做激光雷达的公司}"

{
  echo "tag=$TAG mode=$MODE stamp=$STAMP"
  echo "endpoint env (no secrets):"
  grep -E 'CANONICAL_V2_RERANK' <(tr '\0' '\n' < "/proc/$(systemctl --user show canonical-v2-backend.service -p MainPID --value)/environ") | sort || true
  echo "query=$QUERY"
  echo "---"
} >"$TXT"

curl -sS -N --max-time 240 -c "$JAR" -b "$JAR" \
  -X POST http://127.0.0.1:18188/api/chat/stream \
  -H 'Content-Type: application/json' \
  -d "{\"query\":\"$QUERY\"}" >"$BODY" 2>>"$TXT" || echo "curl exit=$?" >>"$TXT"

{
  echo "bytes=$(wc -c <"$BODY")"
  echo "error_events=$(grep -c 'event: error' "$BODY" || true)"
  echo "done_events=$(grep -c 'event: done' "$BODY" || true)"
  echo "--- answer (first 800 chars) ---"
  python3 - "$BODY" <<'PY'
import json, re, sys
raw = open(sys.argv[1], encoding="utf-8", errors="replace").read()
texts = []
for line in raw.splitlines():
    if line.startswith("data: "):
        try:
            obj = json.loads(line[6:])
        except Exception:
            continue
        for key in ("answer_text", "text", "delta"):
            val = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(val, str) and val:
                texts.append(val)
joined = "".join(texts)
print(json.dumps({"answer_len": len(joined), "answer_head": joined[:800]}, ensure_ascii=False))
PY
} >>"$TXT" 2>&1

echo "wrote $TXT"
tail -6 "$TXT"
