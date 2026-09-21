#!/usr/bin/env bash
# precheck.sh — preconditions for the embedding-model switch rebuild window.
#
# Change: switch-embedding-model-to-qwen37-flash
# Runbook: .agents/runs/embedding-model-switch-v2/rebuild-runbook.md
#
# Usage
#   bash precheck.sh                 # default: hashes the 8.3 GB run16 envelope, one live call
#   bash precheck.sh --fast          # skip large-file hashing (size-only)
#   bash precheck.sh --full          # also hash the pack lookup/relationships and the index artifacts
#   bash precheck.sh --offline       # no network at all (endpoint checks reported as SKIP)
#   bash precheck.sh --batch-probe   # adds ONE extra live call: a 20-text batch (the declared value)
#
# Exit codes: 0 = no FAIL (warnings allowed) · 2 = at least one FAIL
#
# What it checks
#   A  trees, interpreter pair, candidate bundles (self-hash + frozen authority),
#      credential availability, converter/sealer presence, app-local venv trap
#   B  the rollback anchor: the served pack, the served index, its 4096 matrix,
#      the live serve command file
#   C  the envelope: the run16 identity record, and the switch line's fixed path
#      must be free (or archivable)
#   D  fresh targets: index roots, staging, pack dir, target database
#   E  the disposable Postgres
#   F  disk head-room
#   G  the recall gate: harness, baseline, control, protocol, noise floor, cases
#   H  the candidate endpoint: route statuses + ONE authenticated call
#
# It never prints a secret and never writes outside /tmp. It never touches the
# live 18188 service, the live pack, or the live index root.

set -uo pipefail

FAST=0; FULL=0; OFFLINE=0; BATCH_PROBE=0
for arg in "$@"; do
  case "$arg" in
    --fast) FAST=1 ;;
    --full) FULL=1 ;;
    --offline) OFFLINE=1 ;;
    --batch-probe) BATCH_PROBE=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------- configuration
REPO=${REPO:-/home/longxiang/MiroThinker}
SWITCH_LINE=${SWITCH_LINE:-$REPO/.worktrees/embedding-switch-line}
OLD_LINE=${OLD_LINE:-$REPO/.worktrees/data-rebuild}          # holds the run16 envelope
LIVE_TREE=${LIVE_TREE:-$REPO/.worktrees/canonical-v2-s11-consolidation}
RECALL_ROOT=${RECALL_ROOT:-$REPO/.worktrees/recall-regression}
GATE_ROOT="$SWITCH_LINE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
RUN_ROOT="$SWITCH_LINE/.agents/runs/full-column-serving-pack-rebuild"
RUNS="$SWITCH_LINE/.agents/runs/embedding-model-switch-v2"
FALLBACK_RUNS="$REPO/.worktrees/embedding-model-switch/.agents/runs/embedding-model-switch-v2"

DEPLOY_VENV=${DEPLOY_VENV:-$REPO/.venv}
DEPLOY_PY="$DEPLOY_VENV/bin/python"

DATA_ROOT=${DATA_ROOT:-/var/tmp/mirothinker-data-v2}
OLD_PACK=${OLD_PACK:-$DATA_ROOT/serving-pack-run16-readerbound}
OLD_INDEX=${OLD_INDEX:-$DATA_ROOT/index-v3-v2}
NEW_INDEX=${NEW_INDEX:-$DATA_ROOT/index-v4}
NEW_INDEX_V2=${NEW_INDEX_V2:-$DATA_ROOT/index-v4-v2}
NEW_STAGING=${NEW_STAGING:-$DATA_ROOT/staging-v4}
NEW_PACK=${NEW_PACK:-$DATA_ROOT/serving-pack-fembed-v1}
TARGET_DB=${TARGET_DB:-miroflow_candidate_v2_20260922_r1}
PG_DSN=${PG_DSN:-postgresql://miroflow@127.0.0.1:55458/postgres}
PG_CONTAINER=${PG_CONTAINER:-canonical-v2-s12c-pg-20260726-r8}

KEY_FILE=${KEY_FILE:-/var/tmp/mirothinker-qianwen-api-key}
GATEWAY_URL=${GATEWAY_URL:-https://maas.qianwenaiapi.com}
CONTAINER="${CANONICAL_V2_EMBEDDING_API_KEY:-}"

# frozen identities (see the change's acceptance.md / design.md)
OLD_MARKER_SHA=b6f78a3b1e28c280860a4210bfad286ef65090e758de5b876d7f639eefaa8373
OLD_LOOKUP_SHA=2f3e69f4ed0dabe18eb104e296e6dbe4c0ef90683871ab2edf7c1643ecd2ddb8
OLD_REL_SHA=b65794b005ede1aa04e3743307044bbfe0895541c28b4251dc0ddc35be4bca7f
OLD_MATRIX_BYTES=1676818545
OLD_POINTS=51026
OLD_DIM=4096
RUN16_ENVELOPE_SHA=43735faa9300fc834bffcea44304462f30128d5dfa0eb048e76075a115ccea20
RUN16_ENVELOPE_BYTES=8303007285
BUNDLE_NATIVE_SHA=67927ea060ec3036927376c7059aaa7d3140c33160b9be440556a19cd8d64ef3
BUNDLE_COMPAT_SHA=d5ff0ffb52bdaa70a5103fb9747fa7f320547f21dd8e7b6e3a5ce6bd05a2baf4
HARNESS_SHA=ed80f818d4f902b3d5044e42910f046fbd6b9ca8ceb395f39386295c123b0e70
GATE_SHA=(
  "baseline.json:7af37a34e57f5fe9f500d1d7810911a1cb7067fa651b27b8ad6867a8b51f99a2"
  "control.json:54a695ac72c0f8e708ecfde70e2e82b60b148b786a2a3dc1b326f23f8eeb4330"
  "protocol.md:dcb3beb69d58f64967d1cb1e161b67d3811c84919cbf9d5adc2867f272101bb0"
  "noise-floor.md:03a943aa6ed0031428f4d7c3d6ebd3221cd7119f831785bf5b603e843e744c51"
  "testset-cases.json:7dd0113f804668ea183ded2802836946daaa4819486456fe8ce8dca3815d7999"
  "semantic-probes.json:2093dba97ecc28af9692fc7c39e0263ac46b4bdfb90389a926e307df49f44594"
)

OKS=0; WARNS=0; FAILS=0
ok()   { printf '[OK]   %s — %s\n'   "$1" "$2"; OKS=$((OKS+1)); }
warn() { printf '[WARN] %s — %s\n'   "$1" "$2"; WARNS=$((WARNS+1)); }
fail() { printf '[FAIL] %s — %s\n'   "$1" "$2"; FAILS=$((FAILS+1)); }
skip() { printf '[SKIP] %s — %s\n'   "$1" "$2"; }
head2() { printf '\n== %s ==\n' "$1"; }
sha() { sha256sum -- "$1" 2>/dev/null | cut -d' ' -f1; }

echo "embedding-switch precheck — $(date -u +%FT%TZ)"
echo "switch line : $SWITCH_LINE"
echo "recall root : $RECALL_ROOT"

# ------------------------------------------------------------------ A: trees
head2 "A. trees, interpreter, bundles, credential"

if [[ ! -d "$SWITCH_LINE" ]]; then
  fail "A1 switch line" "missing: $SWITCH_LINE (runbook T2.1 has not been done)"
else
  ok "A1 switch line" "$SWITCH_LINE"
  [[ -f "$GATE_ROOT/s12a/complete_candidate_runner.py" ]] \
    && ok "A1a runner" "present" || fail "A1a runner" "missing $GATE_ROOT/s12a/complete_candidate_runner.py"
  [[ -f "$GATE_ROOT/s12c/build_serving_pack.py" ]] \
    && ok "A1b sealer" "$(grep -c -- '--pack-schema-version' "$GATE_ROOT/s12c/build_serving_pack.py") refs to --pack-schema-version" \
    || fail "A1b sealer" "missing $GATE_ROOT/s12c/build_serving_pack.py"
  CONVERTER="$SWITCH_LINE/.agents/runs/drop-milvus-from-serving-pack/convert_index_to_v2.py"
  [[ -f "$CONVERTER" ]] && ok "A1c converter CLI" "$CONVERTER" \
    || fail "A1c converter CLI" "missing (the v2 seal refuses an unconverted index root)"
  grep -q "def convert_isolated_index_to_v2" "$SWITCH_LINE/apps/miroflow-agent/src/data_agents/canonical_v2/index_projection_isolated.py" 2>/dev/null \
    && ok "A1d converter module" "convert_isolated_index_to_v2 present" \
    || fail "A1d converter module" "module missing in the switch line"
fi

if [[ -x "$DEPLOY_PY" ]]; then
  read -r PYV PYD < <("$DEPLOY_PY" -c 'import sys,pydantic;print(sys.version.split()[0], pydantic.VERSION)' 2>/dev/null)
  if [[ "$PYV" == "3.12.12" && "$PYD" == "2.12.5" ]]; then
    ok "A2 interpreter" "$PYV + pydantic $PYD (the pair the live pack's reader digest records)"
  else
    fail "A2 interpreter" "$PYV + pydantic $PYD — expected 3.12.12 + 2.12.5 (a different pair replays the pack reconstruction on every boot)"
  fi
else
  fail "A2 interpreter" "missing deployment venv: $DEPLOY_PY"
fi

APP_VENV="$SWITCH_LINE/apps/miroflow-agent/.venv"
if [[ -x "$APP_VENV/bin/python" ]]; then
  APPV=$("$APP_VENV/bin/python" -c 'import pydantic;print(pydantic.VERSION)' 2>/dev/null)
  if [[ "$APPV" == "2.12.5" ]]; then
    ok "A3 app-local venv" "pydantic $APPV (safe, but the runbook still pins \$DEPLOY_PY)"
  else
    warn "A3 app-local venv" "apps/miroflow-agent/.venv has pydantic $APPV — a bare 'uv run' from that directory would use it and change the reader digest; pin \$DEPLOY_PY"
  fi
else
  ok "A3 app-local venv" "absent (no trap)"
fi

for pair in "native:qwen3.7-text-embedding-flash-embedding-bundle-v1.json:$BUNDLE_NATIVE_SHA" \
            "compat:qwen3.7-text-embedding-flash-embedding-bundle-v1-openai-compat.json:$BUNDLE_COMPAT_SHA"; do
  label=${pair%%:*}; rest=${pair#*:}; name=${rest%%:*}; want=${rest##*:}
  path="$RUNS/$name"
  [[ -f "$path" ]] || path="$FALLBACK_RUNS/$name"
  if [[ ! -f "$path" ]]; then
    fail "A4 bundle($label)" "missing in $RUNS and $FALLBACK_RUNS"
    continue
  fi
  got=$("$DEPLOY_PY" - "$path" <<'PY' 2>/dev/null
import hashlib, json, sys
doc = json.loads(open(sys.argv[1], "rb").read())
recorded = doc.pop("content_sha256")
canon = hashlib.sha256(json.dumps(doc, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":"), allow_nan=False).encode()).hexdigest()
print(canon if canon == recorded else f"MISMATCH:{canon}")
PY
)
  if [[ "$got" == "$want" ]]; then ok "A4 bundle($label)" "self-hash $got matches the frozen authority"; else fail "A4 bundle($label)" "self-hash $got != $want"; fi
done

if [[ -n "$CONTAINER" ]]; then
  ok "A5 credential" "CANONICAL_V2_EMBEDDING_API_KEY set in this environment (never printed)"
elif [[ -f "$KEY_FILE" ]]; then
  ok "A5 credential" "key file present at $KEY_FILE (mode $(stat -c '%a' "$KEY_FILE")); the build reads it with \$(cat …)"
else
  fail "A5 credential" "neither CANONICAL_V2_EMBEDDING_API_KEY nor $KEY_FILE — the rebuild cannot embed"
fi

if [[ -f "$SWITCH_LINE/apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py" ]]; then
  accepted=$("$DEPLOY_PY" - <<PY 2>/dev/null
import re
src = open("$SWITCH_LINE/apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py").read()
print("$BUNDLE_COMPAT_SHA" in src, "$BUNDLE_NATIVE_SHA" in src)
PY
)
  [[ "$accepted" == "True True" ]] && ok "A6 authorities" "both candidate hashes are in the frozen table" \
    || warn "A6 authorities" "candidate hash lookup in the module returned: $accepted"
fi

# ------------------------------------------------------- B: the rollback anchor
head2 "B. rollback anchor (must stay byte-identical through the window)"

if [[ -f "$OLD_PACK/.canonical-v2-isolated-index-target.json" ]]; then
  got=$(sha "$OLD_PACK/.canonical-v2-isolated-index-target.json")
  [[ "$got" == "$OLD_MARKER_SHA" ]] && ok "B1 served pack marker" "${got:0:16}…" || fail "B1 served pack marker" "$got != $OLD_MARKER_SHA"
else
  fail "B1 served pack" "missing $OLD_PACK"
fi
if [[ -f "$OLD_PACK/lookup.sqlite3" ]]; then
  sz=$(stat -c %s "$OLD_PACK/lookup.sqlite3")
  [[ "$sz" == "896270336" ]] && ok "B1a pack lookup size" "$sz bytes" || warn "B1a pack lookup size" "$sz != 896270336"
fi
if [[ -f "$OLD_PACK.mount-receipt.json" ]]; then
  rc=$("$DEPLOY_PY" - "$OLD_PACK.mount-receipt.json" <<'PY' 2>/dev/null
import json, sys
d = json.load(open(sys.argv[1]))
print(d.get("release_id"), d.get("pack_manifest_sha256", "")[:12], d.get("verification"), round(d.get("mount_seconds", 0), 1))
PY
)
  ok "B1b mount receipt" "$rc"
else
  warn "B1b mount receipt" "no receipt beside the pack (the live boot writes it on first mount)"
fi

if [[ -f "$OLD_INDEX/.canonical-v2-isolated-index-target.json" ]]; then
  got=$(sha "$OLD_INDEX/.canonical-v2-isolated-index-target.json")
  [[ "$got" == "$OLD_MARKER_SHA" ]] && ok "B2 served index marker" "${got:0:16}…" || fail "B2 served index marker" "$got != $OLD_MARKER_SHA"
else
  fail "B2 served index" "missing $OLD_INDEX"
fi
if [[ -f "$OLD_INDEX/vector_matrix.npz" ]]; then
  meta=$("$DEPLOY_PY" - "$OLD_INDEX/vector_matrix.npz" "$OLD_MATRIX_BYTES" "$OLD_DIM" "$OLD_POINTS" <<'PY' 2>/dev/null
import json, sys, numpy as np
path, want_bytes, want_dim, want_points = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
d = np.load(path, allow_pickle=True)
m = json.loads(str(d["meta"].item()))
size = __import__("os").path.getsize(path)
verdict = "ok" if (m["dimension"] == want_dim and m["point_count"] == want_points
                   and size == want_bytes and m["embedding_model_id"] == "Qwen/Qwen3-Embedding-8B") else "drift"
print(verdict, m["embedding_model_id"], m["dimension"], m["point_count"], size)
PY
)
  [[ "$meta" == ok\ * ]] && ok "B3 served matrix" "${meta#ok }" || fail "B3 served matrix" "$meta"
else
  fail "B3 served matrix" "missing $OLD_INDEX/vector_matrix.npz"
fi

if [[ $FULL -eq 1 && -f "$OLD_PACK/lookup.sqlite3" ]]; then
  got=$(sha "$OLD_PACK/lookup.sqlite3"); [[ "$got" == "$OLD_LOOKUP_SHA" ]] && ok "B4 pack lookup sha" "${got:0:16}…" || fail "B4 pack lookup sha" "differs"
  if [[ -f "$OLD_PACK/relationships.json" ]]; then
    got=$(sha "$OLD_PACK/relationships.json"); [[ "$got" == "$OLD_REL_SHA" ]] && ok "B4a relationships sha" "${got:0:16}…" || fail "B4a relationships sha" "differs"
  fi
else
  [[ $FULL -eq 1 ]] || skip "B4 big-file hashes" "run with --full to hash the pack lookup/relationships"
fi

LIVE_CMD="$LIVE_TREE/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18188-command.sh"
if [[ -f "$LIVE_CMD" ]]; then
  ok "B5 live serve command" "$(grep -o -- '--serving-pack [^ ]*' "$LIVE_CMD" | head -1)"
else
  warn "B5 live serve command" "not found at $LIVE_CMD — take the rollback copy by hand"
fi

# --------------------------------------------------------- C: envelope records
head2 "C. envelopes"

OLD_ENVELOPE="$OLD_LINE/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope.json"
if [[ -f "$OLD_ENVELOPE" ]]; then
  sz=$(stat -c %s "$OLD_ENVELOPE")
  if [[ "$sz" == "$RUN16_ENVELOPE_BYTES" ]]; then ok "C1 run16 envelope size" "$sz bytes"; else warn "C1 run16 envelope size" "$sz != $RUN16_ENVELOPE_BYTES"; fi
  if [[ $FAST -eq 1 ]]; then
    skip "C1a run16 envelope sha256" "--fast"
  else
    got=$(sha "$OLD_ENVELOPE")
    [[ "$got" == "$RUN16_ENVELOPE_SHA" ]] && ok "C1a run16 envelope sha256" "${got:0:16}…" \
      || fail "C1a run16 envelope sha256" "$got != $RUN16_ENVELOPE_SHA"
  fi
else
  warn "C1 run16 envelope" "not at $OLD_ENVELOPE (already archived?) — check the -run16.json archive instead"
fi

if [[ -d "$GATE_ROOT/s12a" ]]; then
  SW_ENVELOPE="$GATE_ROOT/s12a/complete-candidate-build-envelope.json"
  if [[ -e "$SW_ENVELOPE" ]]; then
    rid=$("$DEPLOY_PY" - "$SW_ENVELOPE" <<'PY' 2>/dev/null
import json, sys
d = json.load(open(sys.argv[1]))
print(d.get("receipt", {}).get("candidate", {}).get("release_id", "?"))
PY
)
    warn "C2 switch-line envelope path" "occupied by release '$rid' ($(stat -c %s "$SW_ENVELOPE") bytes) — archive it before the build (runbook step 2)"
  else
    ok "C2 switch-line envelope path" "free"
  fi
else
  warn "C2 switch-line envelope path" "gate root not found — switch line not created yet"
fi

# ------------------------------------------------------------ D: fresh targets
head2 "D. new targets must be fresh"

for p in "$NEW_INDEX" "$NEW_INDEX_V2" "$NEW_STAGING"; do
  if [[ -e "$p" ]]; then fail "D1 $(basename "$p")" "already exists — the build requires a fresh target"; else ok "D1 $(basename "$p")" "absent"; fi
done
if [[ ! -e "$NEW_PACK" ]]; then ok "D2 pack dir" "absent"
elif [[ -d "$NEW_PACK" && -z "$(ls -A "$NEW_PACK" 2>/dev/null)" ]]; then warn "D2 pack dir" "exists but empty — remove it (the sealer refuses an existing directory)"
else fail "D2 pack dir" "exists with content — remove it or pick another name"; fi

# ------------------------------------------------------------- E: the database
head2 "E. disposable Postgres"

if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$PG_CONTAINER"; then
  ok "E1 container" "$PG_CONTAINER running"
else
  fail "E1 container" "$PG_CONTAINER not running (docker ps)"
fi
PG_REPORT=$("$DEPLOY_PY" - "$PG_DSN" "$TARGET_DB" <<'PY' 2>/dev/null
import sys, psycopg
dsn, target = sys.argv[1], sys.argv[2]
with psycopg.connect(dsn, connect_timeout=5) as conn:
    ver = conn.execute("select version()").fetchone()[0].split(",")[0]
    row = conn.execute("select shobj_description(oid,'pg_database') from pg_database where datname=%s", (target,)).fetchone()
print(f"{ver} | target {target}: {row[0] if row else 'absent (fresh)'}")
PY
)
if [[ -n "$PG_REPORT" ]]; then
  ok "E2 connect" "$PG_REPORT"
else
  fail "E2 connect" "cannot connect to $PG_DSN"
fi
if [[ -d "$SWITCH_LINE/apps/miroflow-agent" && -x "$DEPLOY_VENV/bin/alembic" ]]; then
  heads=$(cd "$SWITCH_LINE/apps/miroflow-agent" && "$DEPLOY_VENV/bin/alembic" -c canonical_v2_alembic.ini heads 2>/dev/null | wc -l)
  [[ "$heads" == "1" ]] && ok "E3 alembic" "exactly one head" || warn "E3 alembic" "heads: $heads (expected 1)"
else
  skip "E3 alembic" "switch line or alembic CLI unavailable"
fi

# ------------------------------------------------------------------- F: disk
head2 "F. disk head-room"

avail_gb() { df -BG --output=avail "$1" 2>/dev/null | tail -1 | tr -dc '0-9'; }
va=$(avail_gb "$DATA_ROOT"); if [[ -n "$va" && "$va" -ge 25 ]]; then ok "F1 /var/tmp" "${va} GB free (need ≥25 for the two index roots + pack + staging)"; else fail "F1 /var/tmp" "${va:-?} GB free — need ≥25"; fi
ha=$(avail_gb "$REPO"); if [[ -n "$ha" && "$ha" -ge 15 ]]; then ok "F2 worktree fs" "${ha} GB free (need ≥15 for the ~8.3 GB envelope + slack)"; else fail "F2 worktree fs" "${ha:-?} GB free — need ≥15"; fi

# ------------------------------------------------------------ G: the recall gate
head2 "G. recall gate artifacts (frozen)"

HARNESS="$RECALL_ROOT/apps/admin-console/scripts/eval_recall_canonical_v2.py"
if [[ -f "$HARNESS" ]]; then
  got=$(sha "$HARNESS"); [[ "$got" == "$HARNESS_SHA" ]] && ok "G1 harness" "${got:0:16}…" || fail "G1 harness" "$got != $HARNESS_SHA (the gate's behaviour changed)"
else
  fail "G1 harness" "missing $HARNESS"
fi
GATE_DIR="$RECALL_ROOT/.agents/runs/embedding-model-switch"
for entry in "${GATE_SHA[@]}"; do
  name=${entry%%:*}; want=${entry#*:}; path="$GATE_DIR/$name"
  if [[ ! -f "$path" ]]; then fail "G2 $name" "missing $path"; continue; fi
  got=$(sha "$path"); [[ "$got" == "$want" ]] && ok "G2 $name" "${got:0:16}…" || fail "G2 $name" "sha differs — the gate calibration is invalidated"
done
if [[ -f "$GATE_DIR/testset-cases.json" && -f "$GATE_DIR/semantic-probes.json" ]]; then
  counts=$("$DEPLOY_PY" - "$GATE_DIR/testset-cases.json" "$GATE_DIR/semantic-probes.json" <<'PY' 2>/dev/null
import json, sys
t = json.load(open(sys.argv[1])); p = json.load(open(sys.argv[2]))
def n(o):
    for k in ("cases", "probes", "turns"):
        if isinstance(o, dict) and k in o: return len(o[k])
    return len(o)
print(n(t), n(p))
PY
)
  ok "G3 case files" "testset + probes parse: $(echo "$counts" | tr ' ' '/') cases"
fi
[[ -f "$GATE_DIR/serve-18295-command.sh" ]] && ok "G4 scratch recipe" "serve-18295-command.sh present (rebased port/state dirs)" \
  || warn "G4 scratch recipe" "no scratch boot recipe found"

# ---------------------------------------------------------------- H: endpoint
head2 "H. candidate endpoint"

if [[ $OFFLINE -eq 1 ]]; then
  skip "H0 endpoint" "--offline"
else
  route_status() { curl -s -o /dev/null -w '%{http_code}' -m 15 -X POST "$GATEWAY_URL$1" \
      -H 'Content-Type: application/json' -d '{"model":"qwen3.7-text-embedding-flash","input":["ping"]}' 2>/dev/null; }
  compat=$(route_status "/compatible-mode/v1/embeddings")
  plain=$(route_status "/v1/embeddings")
  case "$compat" in
    401|200) ok "H1 compatible route" "$compat (route exists)" ;;
    000) fail "H1 compatible route" "no response (network/DNS)" ;;
    *) fail "H1 compatible route" "$compat (expected 401 without a key)" ;;
  esac
  [[ "$plain" == "404" || "$plain" == "401" ]] && ok "H1a /v1/embeddings" "$plain" || warn "H1a /v1/embeddings" "$plain"

  KEYSRC=""
  [[ -n "$CONTAINER" ]] && KEYSRC=env
  [[ -z "$KEYSRC" && -f "$KEY_FILE" ]] && KEYSRC=file
  if [[ -z "$KEYSRC" ]]; then
    skip "H2 authenticated probe" "no key available — the question 'is the flash model served on the compatible route?' stays open"
  else
    KEYSRC_ENV="$KEYSRC" KEY_FILE="$KEY_FILE" GATEWAY_URL="$GATEWAY_URL" \
    CANONICAL_V2_EMBEDDING_API_KEY="$CONTAINER" "$DEPLOY_PY" - <<'PY'
import json, os, time, urllib.error, urllib.request
key = os.environ.get("CANONICAL_V2_EMBEDDING_API_KEY") or open(os.environ["KEY_FILE"]).read().strip()
url = os.environ["GATEWAY_URL"].rstrip("/") + "/compatible-mode/v1/embeddings"
body = json.dumps({"model": "qwen3.7-text-embedding-flash", "input": ["深圳具身智能"]}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json",
                                                     "Authorization": f"Bearer {key}"})
t0 = time.perf_counter()
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        raw, status = r.read(), r.status
except urllib.error.HTTPError as e:
    raw, status = e.read(), e.code
except Exception as e:                                    # noqa: BLE001
    print(f"[FAIL] H2 authenticated probe — transport: {type(e).__name__}"); raise SystemExit(0)
lat = time.perf_counter() - t0
try:
    doc = json.loads(raw)
except Exception:                                         # noqa: BLE001
    print(f"[FAIL] H2 authenticated probe — HTTP {status}, non-JSON body ({len(raw)} bytes)"); raise SystemExit(0)
if status == 200 and doc.get("data"):
    dims = len(doc["data"][0]["embedding"])
    tag = "OK" if dims == 1024 else "FAIL"
    print(f"[{tag}]   H2 authenticated probe — HTTP 200, model={doc.get('model')}, dims={dims}, "
          f"latency={lat:.3f}s, usage={doc.get('usage')}  (key source: {os.environ['KEYSRC_ENV']})")
else:
    print(f"[FAIL] H2 authenticated probe — HTTP {status}: {json.dumps(doc)[:200]}")
PY
  fi

  if [[ $BATCH_PROBE -eq 1 ]]; then
    if [[ -z "$KEYSRC" ]]; then
      skip "H3 batch probe" "no key"
    else
      KEYSRC_ENV="$KEYSRC" KEY_FILE="$KEY_FILE" GATEWAY_URL="$GATEWAY_URL" \
      CANONICAL_V2_EMBEDDING_API_KEY="$CONTAINER" "$DEPLOY_PY" - <<'PY'
import json, os, time, urllib.error, urllib.request
key = os.environ.get("CANONICAL_V2_EMBEDDING_API_KEY") or open(os.environ["KEY_FILE"]).read().strip()
url = os.environ["GATEWAY_URL"].rstrip("/") + "/compatible-mode/v1/embeddings"
texts = [f"批量上限探针 {i} — batch cap probe" for i in range(20)]
body = json.dumps({"model": "qwen3.7-text-embedding-flash", "input": texts}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json",
                                                     "Authorization": f"Bearer {key}"})
t0 = time.perf_counter()
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        doc, status = json.loads(r.read()), r.status
except urllib.error.HTTPError as e:
    print(f"[WARN] H3 batch probe — HTTP {e.code} for a 20-text batch: {e.read()[:200]!r} "
          f"(20 is what both bundles declare; the gateway measured 25 as its cap, so a "
          f"rejection here means the limit dropped below the declared value — lower "
          f"batch_size and re-freeze the bundle's content_sha256)")
    raise SystemExit(0)
lat = time.perf_counter() - t0
rows = len(doc.get("data") or [])
tag = "OK" if rows == 20 else "WARN"
print(f"[{tag}]   H3 batch probe — HTTP {status}, rows={rows}/20, latency={lat:.3f}s, usage={doc.get('usage')}")
PY
    fi
  else
    skip "H3 batch probe" "--batch-probe not requested (one extra live call; re-confirms the declared batch of 25 is accepted)"
  fi
fi

# ----------------------------------------------------------------- summary
head2 "summary"
printf 'OK=%d  WARN=%d  FAIL=%d\n' "$OKS" "$WARNS" "$FAILS"
if [[ "$FAILS" -gt 0 ]]; then
  echo "RESULT: NOT READY — resolve the FAIL lines before opening the window."
  exit 2
fi
echo "RESULT: READY (warnings above are informational; re-run this script immediately before the window)."
