#!/usr/bin/env bash
# Build the run15 serving pack with the official s12c sealer.
#
# This is a parameter copy of build_p4_serving_pack.sh (the accepted run14 path):
# same builder, same fail-fast prechecks — only the release-bound identities
# change (envelope is now run15's, index-v2, new pack dir, new release id,
# run15 marker sha, new generator run id).
#
# Read-only against the index root (the sealer copies, never modifies) and
# write-once into a fresh pack directory: the run14 sealed pack is never touched.
set -euo pipefail

WORKTREE=/home/longxiang/MiroThinker/.worktrees/data-rebuild
S11_WORKTREE=/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation
S11_RUNS="$S11_WORKTREE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
BUILDER="$S11_RUNS/s12c/build_serving_pack.py"
GATE_ROOT="$WORKTREE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
ENVELOPE="$GATE_ROOT/s12a/complete-candidate-build-envelope.json"
INDEX_ROOT="/var/tmp/mirothinker-data-v2/index-v2"
PACK_DIR="/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed"
MARKER="${INDEX_ROOT}/.canonical-v2-isolated-index-target.json"
EXPECTED_MARKER_SHA256="071b858627559d87be09eb01363e951b1275d513aa7a8cddbd45f423b9bac1e9"
RELEASE_ID="candidate-v2-20260913-r1"
GENERATOR_RUN_ID="p4-pack-20260914-v1"

[[ -f "${ENVELOPE}" && ! -L "${ENVELOPE}" ]] || { echo "missing regular envelope" >&2; exit 2; }
[[ -d "${INDEX_ROOT}" && ! -L "${INDEX_ROOT}" ]] || { echo "missing index root" >&2; exit 2; }
[[ ! -e "${PACK_DIR}" ]] || { echo "pack destination must be fresh" >&2; exit 2; }
[[ -f "${MARKER}" && ! -L "${MARKER}" ]] || { echo "missing marker" >&2; exit 2; }
actual="$(sha256sum -- "${MARKER}" | cut -d ' ' -f1)"
[[ "${actual}" == "${EXPECTED_MARKER_SHA256}" ]] || { echo "marker sha differs: ${actual}" >&2; exit 2; }
[[ -f "${BUILDER}" ]] || { echo "official sealer missing: ${BUILDER}" >&2; exit 2; }

# Run with the SERVING-line tree: the build-line tree (data-rebuild) predates
# placeholder_scrub and other s11 modules the sealer imports, and the pack it
# produces is loaded by that same serving tree (proved by the dogfood open below).
cd "$S11_WORKTREE/apps/miroflow-agent"
exec uv run python "${BUILDER}" \
  --envelope "${ENVELOPE}" \
  --index-root "${INDEX_ROOT}" \
  --pack-dir "${PACK_DIR}" \
  --expected-release-id "${RELEASE_ID}" \
  --generator-run-id "${GENERATOR_RUN_ID}"
