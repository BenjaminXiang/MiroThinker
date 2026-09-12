#!/usr/bin/env bash
# Third serving instance (18190) for live fault injection: the rerank base URL
# points at the local stub (127.0.0.1:18099) that answers with a malformed
# payload. Every turn must fall back to the deterministic order and still
# answer, with no credential or candidate text in the logs.
set -u
REPO=/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation
RUN_DIR=/home/longxiang/MiroThinker/.agents/runs/retrieval-v2-derived-index-and-fusion
export PATH="$HOME/.local/bin:$PATH"

export CANONICAL_V2_LEXICAL_INDEX=0
export CANONICAL_V2_RERANK_BASE_URL=http://127.0.0.1:18099
export CANONICAL_V2_RERANK_MODEL=qwen3-reranker-8b
export CANONICAL_V2_RERANK_API_KEY_FILE=/home/longxiang/.config/mirothinker/rerank-api-key
export CANONICAL_V2_RERANK_TIMEOUT_SECONDS=3
export CANONICAL_V2_RERANK_MAX_DOCUMENTS=128
export CANONICAL_V2_RERANK_DEBUG=1
export CANONICAL_V2_TURN_DEBUG_DIR="$RUN_DIR/turn-debug-fault-injection"

cd "$REPO"
# shellcheck disable=SC2046
exec env $(cat "$RUN_DIR/serve-18190-command.sh")
