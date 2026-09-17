#!/usr/bin/env bash
# Seal the run16 serving pack (v2 contract) with the official s12c sealer.
#
# Parameter copy of build_run15_serving_pack.sh.  Differences that matter:
#   - the sealer must support `--pack-schema-version` (P1, fix/slim-serving-pack):
#     run16 ships the v2 pack contract (index_point in the lookup db, no Milvus),
#     so this script refuses a sealer that lacks the flag;
#   - it runs from the SERVING worktree that will serve the pack (the serving
#     line after P1 + the model-sync merge), never from the build-line tree;
#   - the index marker sha is computed here and cross-checked against
#     EXPECTED_MARKER_SHA256 when that variable is exported (fill it from the
#     `index marker sha256=` line printed by build-run16.sh).
#
# Read-only against the index root (the sealer copies, never modifies) and
# write-once into a fresh pack directory: every earlier sealed pack is untouched.
set -euo pipefail

WORKTREE=/home/longxiang/MiroThinker/.worktrees/data-rebuild
SERVING_WORKTREE=${SERVING_WORKTREE:-/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation}
SERVING_RUNS="$SERVING_WORKTREE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
BUILDER="$SERVING_RUNS/s12c/build_serving_pack.py"
GATE_ROOT="$WORKTREE/.agents/runs/rebuild-canonical-v2-knowledge-platform"
ENVELOPE="$GATE_ROOT/s12a/complete-candidate-build-envelope.json"
INDEX_ROOT=${INDEX_ROOT:-/var/tmp/mirothinker-data-v2/index-v3}
PACK_DIR=/var/tmp/mirothinker-data-v2/serving-pack-run16-sealed
MARKER="${INDEX_ROOT}/.canonical-v2-isolated-index-target.json"
RELEASE_ID=candidate-v2-20260916-r1
GENERATOR_RUN_ID=p4-pack-20260916-v1
EXPECTED_MARKER_SHA256=${EXPECTED_MARKER_SHA256:-}

[[ -f "${ENVELOPE}" && ! -L "${ENVELOPE}" ]] || { echo "missing regular envelope: ${ENVELOPE}" >&2; exit 2; }
[[ -d "${INDEX_ROOT}" && ! -L "${INDEX_ROOT}" ]] || { echo "missing index root: ${INDEX_ROOT}" >&2; exit 2; }
[[ ! -e "${PACK_DIR}" ]] || { echo "pack destination must be fresh: ${PACK_DIR}" >&2; exit 2; }
[[ -f "${MARKER}" && ! -L "${MARKER}" ]] || { echo "missing marker: ${MARKER}" >&2; exit 2; }
actual="$(sha256sum -- "${MARKER}" | cut -d ' ' -f1)"
if [[ -n "${EXPECTED_MARKER_SHA256}" && "${actual}" != "${EXPECTED_MARKER_SHA256}" ]]; then
  echo "marker sha differs: ${actual} != ${EXPECTED_MARKER_SHA256}" >&2
  exit 2
fi
echo "index marker sha256=${actual}"
[[ -f "${BUILDER}" ]] || { echo "official sealer missing: ${BUILDER}" >&2; exit 2; }
if ! grep -q -- "--pack-schema-version" "${BUILDER}"; then
  echo "sealer at ${BUILDER} has no --pack-schema-version; run16 requires the v2 sealer (P1)" >&2
  exit 2
fi

# Run with the SERVING-line tree: the pack this produces is loaded by that same
# tree at boot.
cd "$SERVING_WORKTREE/apps/miroflow-agent"
exec uv run python "${BUILDER}" \
  --envelope "${ENVELOPE}" \
  --index-root "${INDEX_ROOT}" \
  --pack-dir "${PACK_DIR}" \
  --expected-release-id "${RELEASE_ID}" \
  --generator-run-id "${GENERATOR_RUN_ID}" \
  --pack-schema-version canonical-v2-serving-pack-v2
