# Eval env truth: match the deployed backend env, or measure a broken system.
# The 58%/Serper-dead false reading came from a run WITHOUT SERPER_API_KEY + WITH proxy vars.
# Usage (from apps/admin-console): source scripts/eval_env.sh
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY

# Load the same keys the running backend (uvicorn backend.main) has, so the in-process
# TestClient sees the same external-service credentials the deployed system uses.
_backend_pid=$(pgrep -f "uvicorn backend.main" | head -1)
if [ -n "$_backend_pid" ]; then
  for var in SERPER_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL \
             ANTHROPIC_DEFAULT_HAIKU_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL \
             ANTHROPIC_DEFAULT_OPUS_MODEL DATABASE_URL HF_TOKEN; do
    _val=$(tr '\0' '\n' < /proc/$_backend_pid/environ 2>/dev/null | grep "^${var}=" | cut -d= -f2-)
    if [ -n "$_val" ]; then
      export "$var=$_val"
    fi
  done
  echo "eval_env: loaded keys from backend (pid $_backend_pid): SERPER(len=${#SERPER_API_KEY}) ANTHROPIC(token len=${#ANTHROPIC_AUTH_TOKEN})"
else
  echo "eval_env: no running backend; set SERPER_API_KEY + ANTHROPIC_* manually."
fi

# L3 judge (异模型 — different model from synthesis). Set in your shell or .env:
#   EVAL_JUDGE_API_KEY, EVAL_JUDGE_BASE_URL, EVAL_JUDGE_MODEL
# Until set, L3 is all-N/A (L1/L2 still run).
export CHAT_LLM_SYNTHESIS=on
