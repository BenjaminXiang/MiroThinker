#!/usr/bin/env bash
# Second serving instance (18189) with the remote rerank model enabled and the
# lexical index off. Scratch DBs (the 18189 command file) keep it from touching
# the 18188 access logs. The model credential is read from a managed key file;
# no secret is stored in this script or printed here.
set -u
REPO=/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation
RUN_DIR=/home/longxiang/MiroThinker/.agents/runs/retrieval-v2-derived-index-and-fusion
export PATH="$HOME/.local/bin:$PATH"

export CANONICAL_V2_LEXICAL_INDEX=0
export CANONICAL_V2_RERANK_BASE_URL=http://100.64.0.27:18006
export CANONICAL_V2_RERANK_MODEL=qwen3-reranker-8b
export CANONICAL_V2_RERANK_API_KEY_FILE=/home/longxiang/.config/mirothinker/rerank-api-key
export CANONICAL_V2_RERANK_TIMEOUT_SECONDS=3
export CANONICAL_V2_RERANK_MAX_DOCUMENTS=128
export CANONICAL_V2_RERANK_DEBUG=1
export CANONICAL_V2_TURN_DEBUG_DIR="$RUN_DIR/turn-debug-rerank-on"

cd "$REPO"
# shellcheck disable=SC2046
exec env $(cat "$REPO/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18189-command.sh")
