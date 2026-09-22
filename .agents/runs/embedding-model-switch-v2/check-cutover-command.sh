#!/usr/bin/env bash
# Invariant checker for the fembed cutover serve-command file (runbook step 12).
#
# Two failure modes this exists to catch, both SILENT (no error at runtime):
#   1. the code tree — a command that keeps the live line's `uv run` form while
#      pointing at the switch line's launcher resolves `src` through whichever venv
#      wins, and a tree mismatch means the new pack is served by the old code;
#   2. the embedding route — build and serve must name the SAME bundle, because the
#      native and openai-compatible routes are different vector spaces (same-text
#      cross-route cosine <= 0.9594 vs 1.0 same-route).
#
#   bash check-cutover-command.sh <command-file> [--expect-tree <switch-line-path>] [--expect-key-file <path>]
set -uo pipefail

FILE="${1:?usage: check-cutover-command.sh <command-file> [--expect-tree <path>] [--expect-key-file <path>]}"
EXPECT_TREE="${3:-/home/longxiang/MiroThinker/.worktrees/embedding-switch-line}"
KEY_FILE=""
if [[ "${4:-}" == "--expect-key-file" ]]; then KEY_FILE="${5:?--expect-key-file needs a path}"; fi
LIVE_TREE_MARKER=".worktrees/canonical-v2-s11-consolidation"
LIVE_PACK_FRAGMENT="serving-pack-run16-readerbound"
LIVE_INDEX_FRAGMENT="index-v3-v2"

PASS=0; FAIL=0
ok()   { printf '  OK   %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL+1)); }

have() { grep -qF -- "$1" "$FILE"; }

[[ -f "$FILE" ]] || { echo "no such command file: $FILE" >&2; exit 2; }
echo "checking $FILE"
echo "  expected tree: $EXPECT_TREE"

# 1. the launcher lives under the expected tree
if have "$EXPECT_TREE" ; then ok "references the expected tree"; else bad "does not reference $EXPECT_TREE"; fi
if have "serve_s12e_port.py"; then ok "names the s12e launcher"; else bad "does not name serve_s12e_port.py"; fi

# 2. the tree is pinned explicitly (PYTHONPATH precedes the editable .pth;
#    the switch line has no .venv, so a `uv run` from there is NOT a pin).
#    BOTH package roots must be pinned, not just `src`: the main venv's editable
#    .pth also carries apps/admin-console, so a `src`-only pin leaves `backend`
#    (chat adapter + admin APIs) on the main tree, silently. Found 2026-09-22 on
#    the gate instance (empty turn-debug dir; /api/auth/me 404).
PP=$(tr ' ' '\n' < "$FILE" | grep -E '^PYTHONPATH=' | head -1 || true)
for root in "apps/miroflow-agent" "apps/admin-console"; do
  if [[ "$PP" == *"$EXPECT_TREE/$root"* ]]; then
    ok "pins PYTHONPATH to the expected tree's $root"
  else
    bad "PYTHONPATH does not carry $EXPECT_TREE/$root — that package would come from another tree"
  fi
done

# 2b. and the pin must actually WIN — resolve the packages through the command's
#     own python + PYTHONPATH. A form check cannot see the editable .pth ordering.
SELF_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [[ -f "$SELF_DIR/check-package-resolution.sh" ]]; then
  if out=$(bash "$SELF_DIR/check-package-resolution.sh" "$FILE" --expect-tree "$EXPECT_TREE" 2>&1); then
    ok "PACKAGE_RESOLUTION: backend + src both resolve under the expected tree"
  else
    bad "PACKAGE_RESOLUTION: $(printf '%s' "$out" | tr '\n' '|' | tail -c 400)"
  fi
else
  bad "PACKAGE_RESOLUTION checker missing: $SELF_DIR/check-package-resolution.sh"
fi

# 3. nothing of the pre-switch line survives
if grep -qF "$LIVE_TREE_MARKER" "$FILE"; then bad "still references the live/serving tree ($LIVE_TREE_MARKER)"; else ok "no live-tree path"; fi
if grep -qF "$LIVE_PACK_FRAGMENT" "$FILE"; then bad "still points at the pre-switch pack"; else ok "not the pre-switch pack"; fi
if grep -qF "$LIVE_INDEX_FRAGMENT" "$FILE"; then bad "still points at the pre-switch index root"; else ok "not the pre-switch index root"; fi

# 4. the embedding route matches the build (native, NOT the compat twin)
if grep -q -- "-openai-compat" "$FILE"; then
  bad "names the openai-compatible twin — different vector space from the build's documents, and no query-side treatment"
elif grep -qF "qwen3.7-text-embedding-flash-embedding-bundle-v1.json" "$FILE"; then
  ok "names the native embedding bundle (same route as the build)"
else
  bad "does not name the native embedding bundle"
fi
if grep -qF "qwen3.7-text-embedding-flash" "$FILE"; then ok "names the candidate model id"; else bad "does not name the candidate model id"; fi

# 5. the credential must reach the process WITHOUT shell evaluation. The host unit
#    (deploy/start-canonical-v2.sh) expands this file with `exec env $(cat …)`, so a
#    shell-substituted token becomes argv and env(1) tries to exec the literal path
#    (proven 2026-09-22 with a synthetic file: `env: '/tmp/x)"': No such file or
#    directory`; the live run16 file is quote-free for exactly this reason). The key
#    therefore belongs to the unit's EnvironmentFile — name it with
#    --expect-key-file to have it checked here.
if grep -qF 'CANONICAL_V2_EMBEDDING_API_KEY="$(cat' "$FILE"; then
  bad "EMBEDDING_KEY: shell substitution in the command file — the host unit does no shell evaluation"
elif [[ -n "$KEY_FILE" ]]; then
  if [[ -f "$KEY_FILE" ]] && grep -qE '^CANONICAL_V2_EMBEDDING_API_KEY=.+' "$KEY_FILE"; then
    ok "EMBEDDING_KEY: supplied by $KEY_FILE"
  else
    bad "EMBEDDING_KEY: $KEY_FILE missing or without CANONICAL_V2_EMBEDDING_API_KEY"
  fi
elif grep -qF "CANONICAL_V2_EMBEDDING_API_KEY" "$FILE"; then
  ok "EMBEDDING_KEY: named in argv (bash launch only — the unit cannot evaluate it)"
else
  bad "EMBEDDING_KEY: not supplied — the embedding lane would fail closed"
fi

# 5b. HOST_QUOTING: the same expansion means the host file must stay quote-free.
if grep -qF '"' "$FILE" || grep -qF '$(' "$FILE"; then
  bad "HOST_QUOTING: contains a double quote or a command substitution — the host unit expands it with exec env, so they survive as literal argv"
else
  ok "HOST_QUOTING: quote-free, survives the host unit's expansion"
fi

# 6. the two 64-hex values the window fills in (step 7 marker, step 10 bundle sha)
for flag in "--index-marker-sha256" "--recorded-serving-bundle-sha256"; do
  if grep -qE -- "$flag [0-9a-f]{64}( |$)" "$FILE"; then ok "$flag is a filled 64-hex"; else bad "$flag missing or not 64-hex"; fi
done

# 6b. every path a flag names must EXIST on this host. Added 2026-09-22 after a
# filename-only check let a wrong-directory bundle through: the sed that derived this
# file replaced the tail of the --recorded-embedding-bundle path but kept the
# .../data-rebuild/ prefix, so the file named itself correctly and did not exist.
for flag in --serving-pack --index-root --recorded-embedding-bundle --recorded-serving-bundle \
            --recorded-decision-bundle --source-manifest --envelope-output --accepted-backup-gate-root; do
  value=$(tr ' ' '\n' < "$FILE" | awk -v f="$flag" '$0==f {getline; print; exit}')
  if [[ -n "$value" && "$value" == /* && "$value" != *'$('* ]]; then
    if [[ -e "$value" ]]; then ok "exists: $flag"; else bad "PATHS_EXIST: $flag -> $value does not exist"; fi
  fi
done

# 6c. --recorded-serving-bundle-sha256 must be the bundle's DECLARED content_sha256,
# not the file's sha256 (learned 2026-09-22: the gate instance refused to start with
# "serving bundle declared hash differs" because the runbook's own step-10 instruction
# said to use sha256sum; the live run16 command passes 0a09aecde9… = the declared hash).
BUNDLE=$(tr ' ' '\n' < "$FILE" | awk '$0=="--recorded-serving-bundle" {getline; print; exit}')
BFLAG=$(tr ' ' '\n' < "$FILE" | awk '$0=="--recorded-serving-bundle-sha256" {getline; print; exit}')
if [[ -f "$BUNDLE" && -n "$BFLAG" ]]; then
  BDECL=$("$([ -x /home/longxiang/MiroThinker/.venv/bin/python ] && echo /home/longxiang/MiroThinker/.venv/bin/python || echo python3)" -c "import json,sys;print(json.load(open(sys.argv[1])).get('content_sha256',''))" "$BUNDLE")
  if [[ "$BFLAG" == "$BDECL" ]]; then ok "BUNDLE_CONTENT_SHA matches the bundle's declared content_sha256"
  else bad "BUNDLE_CONTENT_SHA: flag=$BFLAG but bundle declares $BDECL"; fi
fi

# 6d. the bundle must bind to THIS command: knowledge_serving_isolated compares
# release_id / database_name+kind / index_target_id+index_root / envelope_path against
# the runner's own arguments and refuses with "serving bundle <field> differs" otherwise.
# Added 2026-09-22 after the gate instance refused on envelope_path (the derivation kept
# the live line's data-rebuild envelope while the bundle recorded this line's).
if [[ -f "$BUNDLE" ]]; then
  PY_BIN=$([ -x /home/longxiang/MiroThinker/.venv/bin/python ] && echo /home/longxiang/MiroThinker/.venv/bin/python || echo python3)
  field_of() { tr ' ' '\n' < "$FILE" | awk -v f="$1" '$0==f {getline; print; exit}'; }
  rel=$(field_of --candidate-release-id); dburl=$(field_of --database-url); idroot=$(field_of --index-root); envp=$(field_of --envelope-output)
  db=${dburl##*/}
  want_rel=$("$PY_BIN" -c "import json,sys;d=json.load(open(sys.argv[1]));print(d.get('release_id',''),d.get('database_name',''),d.get('index_root',''),d.get('index_target_id',''),d.get('envelope_path',''),sep='|')" "$BUNDLE")
  IFS='|' read -r b_rel b_db b_root b_tid b_env <<<"$want_rel"
  [[ "$b_rel" == "$rel" ]] && ok "BUNDLE_BINDING release_id" || bad "BUNDLE_BINDING release_id: bundle=$b_rel flag=$rel"
  [[ "$b_db" == "$db" ]] && ok "BUNDLE_BINDING database_name" || bad "BUNDLE_BINDING database_name: bundle=$b_db flag=$db"
  [[ "$b_tid" == "index:$rel" ]] && ok "BUNDLE_BINDING index_target_id" || bad "BUNDLE_BINDING index_target_id: bundle=$b_tid"
  [[ "$b_root" == "$idroot" ]] && ok "BUNDLE_BINDING index_root" || bad "BUNDLE_BINDING index_root: bundle=$b_root flag=$idroot"
  [[ "$b_env" == "$envp" ]] && ok "BUNDLE_BINDING envelope_path" || bad "BUNDLE_BINDING envelope_path: bundle=$b_env flag=$envp"
fi

# 6e. --envelope-output must equal <--accepted-backup-gate-root>/s12a/complete-candidate-build-envelope.json
# (complete_candidate_runner._parse_args derives that fixed path from the gate root and
# refuses with "envelope output must use the fixed candidate evidence path"; found 2026-09-22).
GR=$(tr ' ' '\n' < "$FILE" | awk '$0=="--accepted-backup-gate-root" {getline; print; exit}')
EO=$(tr ' ' '\n' < "$FILE" | awk '$0=="--envelope-output" {getline; print; exit}')
if [[ -n "$GR" && -n "$EO" ]]; then
  if [[ "$EO" == "$GR/s12a/complete-candidate-build-envelope.json" ]]; then ok "GATE_ENVELOPE_PAIR (envelope under the gate root)"
  else bad "GATE_ENVELOPE_PAIR: envelope=$EO but the gate root requires $GR/s12a/complete-candidate-build-envelope.json"; fi
fi

# 7. the fembed identities
for frag in "serving-pack-fembed-v1" "index-v4-v2" "candidate-v2-20260922-r1"; do
  if grep -qF "$frag" "$FILE"; then ok "carries $frag"; else bad "missing $frag"; fi
done

echo "  ---- $PASS ok / $FAIL fail"
[[ "$FAIL" -eq 0 ]] || exit 1
