#!/usr/bin/env bash
# Static pre-cutover check for the managed configuration the fembed switch depends on.
# All three fields were silent gaps measured on 2026-09-22/23 — the line boots fine
# without them and only the operator surface, or the answer model, changes:
#
#   1. serving.chat_llm_profile               — the answer model (else the code default `gemma4`)
#   2. paths.serving_pack_dir                 — the pack the status card / identity probe / connection
#                                               test report (else the literal Qwen/Qwen3-Embedding-8B)
#   3. extraction_endpoints.embedding_base_url — the address the page's connection test probes
#      + the page's credential slot (embedding.api_key) in the managed store
#
#   bash check-cutover-settings.sh <tree> <expected-pack-dir> <expected-base-url> <expected-profile>
#
# Example (the fembed cutover):
#   bash check-cutover-settings.sh /home/longxiang/MiroThinker/.worktrees/embedding-switch-line \
#        /var/tmp/mirothinker-data-v2/serving-pack-fembed-v1 \
#        https://maas.qianwenaiapi.com/api/v1 deepseekv4flash
set -uo pipefail

TREE="${1:?usage: check-cutover-settings.sh <tree> <pack-dir> <base-url> <profile>}"
PACK="${2:?}"
BASE_URL="${3:?}"
PROFILE="${4:?}"

PY_BIN=/home/longxiang/MiroThinker/.venv/bin/python
[[ -x "$PY_BIN" ]] || PY_BIN=$(command -v python3)

SET="$TREE/config/managed/settings.json"
SEC="$TREE/config/managed/secrets.json"
fails=0
echo "checking managed configuration under $TREE"
echo "  expecting: profile=$PROFILE pack=$PACK base_url=$BASE_URL"

for f in "$SET" "$SEC"; do
  if [[ ! -f "$f" ]]; then
    printf '  FAIL %s missing\n' "$(basename "$f")"
    fails=$((fails + 1))
    continue
  fi
  mode=$(stat -c '%a' "$f")
  if [[ "$mode" == "600" ]]; then printf '  OK   %s 0600\n' "$(basename "$f")"
  else printf '  FAIL %s mode %s (want 600)\n' "$(basename "$f")" "$mode"; fails=$((fails + 1)); fi
done

PYTHONPATH="$TREE/apps/miroflow-agent" "$PY_BIN" - "$TREE" "$PACK" "$BASE_URL" "$PROFILE" <<'PY' || fails=$((fails + 1))
import sys

from src.data_agents.canonical_v2.managed_config import (
    ManagedSettingsStore,
    default_settings_path,
)
from src.data_agents.canonical_v2.managed_secrets import (
    ManagedSecretsStore,
    default_secrets_path,
)

tree, pack, base_url, profile = sys.argv[1:5]
raw = ManagedSettingsStore(
    path=default_settings_path(
        {"CANONICAL_V2_MANAGED_SETTINGS": f"{tree}/config/managed/settings.json"}
    ),
    environ={},
).raw()

bad = 0


def check(label: str, got: object, want: object) -> None:
    global bad
    if got == want:
        print(f"  OK   {label} = {got}")
    else:
        print(f"  FAIL {label} = {got!r} (want {want!r})")
        bad += 1


check("serving.chat_llm_profile", (raw.get("serving") or {}).get("chat_llm_profile"), profile)
check("paths.serving_pack_dir", (raw.get("paths") or {}).get("serving_pack_dir"), pack)
check(
    "extraction_endpoints.embedding_base_url",
    (raw.get("extraction_endpoints") or {}).get("embedding_base_url"),
    base_url,
)

try:
    secrets = ManagedSecretsStore(
        path=default_secrets_path(
            {"CANONICAL_V2_MANAGED_SECRETS": f"{tree}/config/managed/secrets.json"}
        ),
        environ={},
    ).raw()
except Exception as exc:  # noqa: BLE001 - report, never traceback at an operator
    print(f"  FAIL secrets store unreadable: {type(exc).__name__}")
    raise SystemExit(1)

value = str(secrets.get("embedding.api_key") or "")
if value:
    print(f"  OK   secrets embedding.api_key set ({len(value)} chars, tail …{value[-4:]})")
else:
    print("  FAIL secrets embedding.api_key missing — the page's connection test has nothing to probe")
    bad += 1

raise SystemExit(1 if bad else 0)
PY

echo "  ---- failures=$fails"
[[ "$fails" -eq 0 ]] || exit 1
