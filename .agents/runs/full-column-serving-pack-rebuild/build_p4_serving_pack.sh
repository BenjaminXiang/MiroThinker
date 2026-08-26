#!/usr/bin/env bash
# Build the exact P4 Serving Pack. Run only after the complete-candidate
# envelope exists (run 9 delivered it 2026-08-26). Destination must be fresh.
set -euo pipefail

WORKTREE=/home/longxiang/MiroThinker/.worktrees/data-rebuild
SCRIPT_DIR="$WORKTREE/.agents/runs/full-column-serving-pack-rebuild"
GATE_ROOT="$WORKTREE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
S11_RUNS=/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation/.agents/runs/rebuild-canonical-v2-knowledge-platform
BUILDER="$S11_RUNS/s12c/build_serving_pack.py"
VERIFIER="$S11_RUNS/s12f/post_build_verify.py"
ENVELOPE="$GATE_ROOT/s12a/complete-candidate-build-envelope.json"
INDEX_ROOT="/var/tmp/mirothinker-data-v2/index-v1"
PACK_DIR="/var/tmp/mirothinker-data-v2/serving-pack"
MARKER="${INDEX_ROOT}/.canonical-v2-isolated-index-target.json"
EXPECTED_MARKER_SHA256="8848197caaa665fa093f054aa6c7c241b90376f311ec62e089ddb479a6e97c8b"
RELEASE_ID="candidate-v2-20260819-r1"
GENERATOR_RUN_ID="p4-pack-20260826-v1"

[[ -f "${ENVELOPE}" && ! -L "${ENVELOPE}" ]] || { echo "missing regular envelope" >&2; exit 2; }
[[ -d "${INDEX_ROOT}" && ! -L "${INDEX_ROOT}" ]] || { echo "missing index root" >&2; exit 2; }
[[ ! -e "${PACK_DIR}" ]] || { echo "pack destination must be fresh" >&2; exit 2; }
[[ -f "${MARKER}" && ! -L "${MARKER}" ]] || { echo "missing marker" >&2; exit 2; }
actual="$(sha256sum -- "${MARKER}" | cut -d ' ' -f1)"
[[ "${actual}" == "${EXPECTED_MARKER_SHA256}" ]] || { echo "marker sha differs: ${actual}" >&2; exit 2; }

cd "$WORKTREE/apps/miroflow-agent"
exec uv run python "${BUILDER}" \
  --envelope "${ENVELOPE}" \
  --index-root "${INDEX_ROOT}" \
  --pack-dir "${PACK_DIR}" \
  --expected-release-id "${RELEASE_ID}" \
  --generator-run-id "${GENERATOR_RUN_ID}"
