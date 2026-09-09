#!/usr/bin/env bash
# Build and dogfood-open the exact s12f Serving Pack. Run only after the
# complete-candidate envelope exists. The destination must not already exist.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../../.." && pwd -P)"
BUILDER="${REPO_ROOT}/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py"
VERIFIER="${SCRIPT_DIR}/post_build_verify.py"
ENVELOPE="${SCRIPT_DIR}/complete-candidate-build-envelope.json"
INDEX_ROOT="/var/tmp/mirothinker-canonical-v2-s12f/index-v1"
PACK_DIR="/var/tmp/mirothinker-canonical-v2-s12f/serving-pack"
MARKER="${INDEX_ROOT}/.canonical-v2-isolated-index-target.json"
EXPECTED_MARKER_SHA256="e4314c15518980aaa75a0069dce14c3857df43b74705ce600c6741af74d49f51"
RELEASE_ID="candidate-s12f-20260801-v1"
GENERATOR_RUN_ID="s12f-pack-20260801-v1"

if [[ ! -f "${ENVELOPE}" || -L "${ENVELOPE}" ]]; then
    printf 'missing regular s12f envelope: %s\n' "${ENVELOPE}" >&2
    exit 2
fi
if [[ ! -d "${INDEX_ROOT}" || -L "${INDEX_ROOT}" ]]; then
    printf 'missing non-symlink s12f index root: %s\n' "${INDEX_ROOT}" >&2
    exit 2
fi
if [[ -e "${PACK_DIR}" || -L "${PACK_DIR}" ]]; then
    printf 's12f serving-pack destination must be fresh: %s\n' "${PACK_DIR}" >&2
    exit 2
fi
if [[ ! -f "${MARKER}" || -L "${MARKER}" ]]; then
    printf 'missing regular s12f index marker: %s\n' "${MARKER}" >&2
    exit 2
fi
marker_sha256="$(sha256sum -- "${MARKER}" | cut -d ' ' -f 1)"
if [[ "${marker_sha256}" != "${EXPECTED_MARKER_SHA256}" ]]; then
    printf 's12f index marker sha256 differs: expected=%s actual=%s\n' \
        "${EXPECTED_MARKER_SHA256}" "${marker_sha256}" >&2
    exit 2
fi

cd -- "${REPO_ROOT}/apps/miroflow-agent"
uv run python "${VERIFIER}" \
    --envelope "${ENVELOPE}" \
    --index-root "${INDEX_ROOT}" \
    --envelope-identity-only
exec uv run python "${BUILDER}" \
    --envelope "${ENVELOPE}" \
    --index-root "${INDEX_ROOT}" \
    --pack-dir "${PACK_DIR}" \
    --expected-release-id "${RELEASE_ID}" \
    --generator-run-id "${GENERATOR_RUN_ID}"
