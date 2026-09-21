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
#   bash check-cutover-command.sh <command-file> [--expect-tree <switch-line-path>]
set -uo pipefail

FILE="${1:?usage: check-cutover-command.sh <command-file> [--expect-tree <path>]}"
EXPECT_TREE="${3:-/home/longxiang/MiroThinker/.worktrees/embedding-switch-line}"
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
#    the switch line has no .venv, so a `uv run` from there is NOT a pin)
if grep -qF "PYTHONPATH=${EXPECT_TREE}/apps/miroflow-agent" "$FILE" \
   || grep -qF "PYTHONPATH=$EXPECT_TREE/apps/miroflow-agent" "$FILE"; then
  ok "pins PYTHONPATH to the expected tree's package root"
else
  bad "no PYTHONPATH=<expected tree>/apps/miroflow-agent — the imported canonical_v2 would come from another tree"
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

# 5. the credential is supplied at launch
if grep -qF "CANONICAL_V2_EMBEDDING_API_KEY" "$FILE"; then
  ok "supplies CANONICAL_V2_EMBEDDING_API_KEY"
else
  bad "no CANONICAL_V2_EMBEDDING_API_KEY — the embedding lane would fail closed"
fi

# 6. the two 64-hex values the window fills in (step 7 marker, step 10 bundle sha)
for flag in "--index-marker-sha256" "--recorded-serving-bundle-sha256"; do
  if grep -qE -- "$flag [0-9a-f]{64}( |$)" "$FILE"; then ok "$flag is a filled 64-hex"; else bad "$flag missing or not 64-hex"; fi
done

# 7. the fembed identities
for frag in "serving-pack-fembed-v1" "index-v4-v2" "candidate-v2-20260922-r1"; do
  if grep -qF "$frag" "$FILE"; then ok "carries $frag"; else bad "missing $frag"; fi
done

echo "  ---- $PASS ok / $FAIL fail"
[[ "$FAIL" -eq 0 ]] || exit 1
