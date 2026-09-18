"""Dump the real payloads for the 模型与连接 harness (fixtures.json).

Runs the **live** route handlers in-process (FastAPI TestClient, temp managed
settings/secrets stores, ambient credential variables removed, fake keys written
through the real store) so the DOM harness and the browser stub render what the
server actually sends — not a hand-copied shape. The model-list payloads come
from `fetch_model_list()` itself with an injected transport (a 401 body, a 260-id
list, a read timeout, a closed port), which is the same code path the page hits.

Run from `apps/admin-console`:

    uv run python ../../.agents/runs/connect-collection-line/model-roles-harness/dump_fixtures.py

Nothing here reads a real credential: the managed stores are temporary, the key
values are fakes, and the ambient credential variables are removed for the dump.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

REPO = Path(__file__).resolve().parents[4]
ADMIN = REPO / "apps" / "admin-console"
sys.path.insert(0, str(ADMIN))

from backend.api.canonical_v2_admin_config import (  # noqa: E402
    get_managed_secrets_store,
    get_managed_settings_store,
)
from backend.main import app  # noqa: E402
from backend.services.canonical_v2_connection_tests import fetch_model_list  # noqa: E402
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore  # noqa: E402
from src.data_agents.canonical_v2.managed_secrets import ManagedSecretsStore  # noqa: E402

OUT = Path(__file__).with_name("fixtures.json")
FAKE_LLM_KEY = "sk-fake-llm-9f2c000000000000"
FAKE_BOCHA_KEY = "sk-fake-bocha-beef00000000"
FAKE_LOCAL_KEY = "sk-fake-local-c0de00000000"

_AMBIENT_CREDENTIAL_VARS = (
    "API_KEY",
    "OPENAI_API_KEY",
    "SGLANG_API_KEY",
    "BOCHA_API_KEY",
    "SERPER_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "ARK_API_KEY",
    "LOCAL_LLM_API_KEY",
    "CANONICAL_V2_RERANK_API_KEY",
    "CANONICAL_V2_RERANK_BASE_URL",
    "CANONICAL_V2_EMBEDDING_BASE_URL",
    "LOCAL_LLM_BASE_URL",
    "CAMOUFOX_DEBUG_WS",
)


def _transport(status: int, payload: bytes):
    def caller(url: str, *, headers, timeout, max_bytes):  # noqa: ANN001
        return status, payload

    return caller


def _timeout_transport(url: str, *, headers, timeout, max_bytes):  # noqa: ANN001
    raise TimeoutError("dump fixture")


def main() -> int:
    for name in _AMBIENT_CREDENTIAL_VARS:
        os.environ.pop(name, None)
    os.environ.pop("CHAT_LLM_PROFILE", None)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings = ManagedSettingsStore(
            root / "managed" / "settings.json", environ=dict(os.environ), repo_root=root
        )
        secrets = ManagedSecretsStore(
            root / "managed" / "secrets.json",
            environ=dict(os.environ),
            key_file_roots=(),
            repo_root=root,
        )
        # Written through the real store: sources, masks and origins are the ones
        # the page will be rendered from, and no ambient key is involved.
        settings.patch(
            {
                "extraction_endpoints": {
                    "llm_base_url": "http://127.0.0.1:8000/v1",
                    "llm_model": "qwen3.6-35b-a3b",
                    "rerank_base_url": "http://127.0.0.1:9000/v1",
                    "rerank_model": "qwen3-reranker-8b",
                },
                "serving": {"chat_llm_profile": "deepseekv4flash"},
            },
            operator="fixture",
        )
        secrets.patch(
            {
                "llm.api_key": FAKE_LLM_KEY,
                "bocha.api_key": FAKE_BOCHA_KEY,
                "embedding.api_key": FAKE_LOCAL_KEY,
            },
            operator="fixture",
        )
        app.state.canonical_v2_managed_settings_store = settings
        app.state.canonical_v2_managed_secrets_store = secrets
        app.dependency_overrides[get_managed_settings_store] = lambda: settings
        app.dependency_overrides[get_managed_secrets_store] = lambda: secrets
        from tests.conftest import authorized_client

        client = authorized_client(raise_server_exceptions=False)
        config = client.get("/api/canonical-v2/admin/config")
        secrets_payload = client.get("/api/canonical-v2/admin/secrets")
        presets = client.get("/api/canonical-v2/admin/connections/presets")
        assert config.status_code == 200, config.text
        assert secrets_payload.status_code == 200, secrets_payload.text
        assert presets.status_code == 200, presets.text

    many_ids = [f"model-{index:03d}" for index in range(600)]
    ok_ids = ["qwen3.6-35b-a3b", "qwen3.6-plus", "deepseek-v4-flash"]
    models_ok = fetch_model_list(
        base_url="http://127.0.0.1:8000/v1",
        api_key=FAKE_LLM_KEY,
        transport=_transport(
            200, json.dumps({"object": "list", "data": [{"id": i} for i in ok_ids]}).encode()
        ),
    )
    models_many = fetch_model_list(
        base_url="http://127.0.0.1:9000/v1",
        transport=_transport(
            200, json.dumps({"data": [{"id": i} for i in many_ids]}).encode()
        ),
    )
    models_unauthorized = fetch_model_list(
        base_url="http://127.0.0.1:9000/v1",
        api_key="sk-fake-rejected-key-0000",
        transport=_transport(401, b'{"error":"invalid api key: sk-fake-rejected-key-0000"}'),
    )
    models_timeout = fetch_model_list(
        base_url="http://127.0.0.1:9000/v1", transport=_timeout_transport
    )
    models_unreachable = fetch_model_list(base_url="http://127.0.0.1:9/v1")

    fixtures = {
        "config": config.json(),
        "secrets": secrets_payload.json(),
        "presets": presets.json(),
        "modelsOk": models_ok,
        "modelsMany": models_many,
        "modelsUnauthorized": models_unauthorized,
        "modelsTimeout": models_timeout,
        "modelsUnreachable": models_unreachable,
    }
    OUT.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    print("models ok:", models_ok["count"], "| many:", models_many["count"], models_many.get("truncated"))
    print("unauthorized:", models_unauthorized["error"], models_unauthorized["status"])
    print("timeout:", models_timeout["error"], "| unreachable:", models_unreachable["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
