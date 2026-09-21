#!/usr/bin/env bash
# v1.1 re-seal of the run16 serving pack against the merged release/v1.1 code.
#
# This is the official seal path (the sealer the reader-bound re-seal used,
# `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py`),
# run from the release worktree so that the `reader_contract_sha256` the pack
# records is the digest of the v1.1 code, not of the frozen v1 tree.
#
# Preconditions (verified before this ran, see current-state.md):
#   * interpreter = CPython 3.12.12 + pydantic 2.12.5 (same as the serving venv;
#     a different patch version silently costs ~190 s per boot);
#   * envelope readable, index root readable, marker sha b6f78a3b…;
#   * `--pack-dir` must not exist (the sealer refuses an existing directory);
#   * `serving-pack-run16-readerbound` and `index-v3-v2` are read-only inputs —
#     this command never writes to them (no `--link`: the pack must not share
#     inodes with the live index root).
#
# Usage:  bash .agents/runs/release-v11/reseal-command.sh
set -euo pipefail

cd /home/longxiang/MiroThinker/.worktrees/release-v11

ENVELOPE=/home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope.json
INDEX_ROOT=/var/tmp/mirothinker-data-v2/index-v3-v2
PACK_DIR=/var/tmp/mirothinker-data-v2/serving-pack-run16-v11

exec uv run python \
  .agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py \
  --envelope "${ENVELOPE}" \
  --index-root "${INDEX_ROOT}" \
  --pack-dir "${PACK_DIR}" \
  --expected-release-id candidate-v2-20260916-r1 \
  --generator-run-id run16-v11-20260921-v1 \
  --pack-schema-version canonical-v2-serving-pack-v2
