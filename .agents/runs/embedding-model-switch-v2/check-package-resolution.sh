#!/usr/bin/env bash
# Which tree's packages does a serve-command file actually import?
#
# Added 2026-09-22 (runbook steps 11/12) after the gate's candidate layer came back
# empty. Cause: the main venv carries an editable .pth for BOTH apps/admin-console
# and apps/miroflow-agent pointing at the MAIN tree, so pinning only
# apps/miroflow-agent on PYTHONPATH puts `src` on the switch line while `backend`
# (the chat adapter and the admin APIs) still resolves to the main tree. The
# runner's own fallback insert never fires because `import backend.main` already
# succeeds. Silent at boot; symptoms were /api/auth/me and
# /api/canonical-v2/admin/chat-gaps 404 on the gate instance and an empty
# turn-debug dir (the main tree's adapter has no _maybe_dump_turn_debug, so the
# comparator reported REVIEW for every case).
#
#   bash check-package-resolution.sh <command-file> [--expect-tree <tree>]
set -uo pipefail

FILE="${1:?usage: check-package-resolution.sh <command-file> [--expect-tree <tree>]}"
EXPECT=""
if [[ "${2:-}" == "--expect-tree" ]]; then EXPECT="${3:?--expect-tree needs a path}"; fi
EXPECT="${EXPECT:-/home/longxiang/MiroThinker/.worktrees/embedding-switch-line}"
[[ -f "$FILE" ]] || { echo "no such command file: $FILE" >&2; exit 2; }

PYBIN=$(tr ' ' '\n' < "$FILE" | grep -E '/python[0-9.]*$' | head -1)
PP=$(tr ' ' '\n' < "$FILE" | grep -E '^PYTHONPATH=' | head -1 || true)
[[ -n "$PYBIN" ]] || { echo "no python binary in $FILE" >&2; exit 2; }

OUT=$(PYTHONPATH="${PP#PYTHONPATH=}" "$PYBIN" - <<'PY'
import importlib.util as u

for name in ("backend", "src"):
    spec = u.find_spec(name)
    locs = list(getattr(spec, "submodule_search_locations", None) or ())
    print(f"{name}={locs[0] if locs else '?'}")
PY
) || { echo "probe failed to run (python=$PYBIN)" >&2; exit 2; }

echo "checking package resolution: $FILE"
echo "  python: $PYBIN"
[[ -n "$PP" ]] && echo "  $PP"
echo "  expected tree: $EXPECT"

fail=0
while IFS='=' read -r name path; do
  [[ -n "$name" ]] || continue
  if [[ "$path" == "$EXPECT"/* ]]; then
    printf '  OK   %-7s -> %s\n' "$name" "$path"
  else
    printf '  FAIL %-7s -> %s (not under %s)\n' "$name" "$path" "$EXPECT"
    fail=1
  fi
done <<<"$OUT"
exit "$fail"
