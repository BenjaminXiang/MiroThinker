"""R5 — `extraction_endpoints.*` has exactly one entry point.

Two greps, both fail-closed: the rebuilt page must hold no endpoint field
knowledge of its own (it renders whatever the catalogue sends), and no module
may hand-build a second payload for those paths (the old defect was a page-local
`connectionKey === "embedding" ? …` mapping PATCHed from inside a secrets save).

Fixture source: the shipped source tree, read from disk — no network, no
service, no state directory.
"""

from __future__ import annotations

from pathlib import Path
import re

from src.data_agents.canonical_v2.managed_config import (
    FIELD_CATALOG,
    ManagedSettings,
    flatten_settings,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_ADMIN_BACKEND = REPO_ROOT / "apps" / "admin-console" / "backend"
_AGENT_SRC = REPO_ROOT / "apps" / "miroflow-agent" / "src"

ENDPOINT_FIELD_NAMES = (
    "llm_base_url",
    "llm_model",
    "embedding_base_url",
    "embedding_model",
    "rerank_base_url",
    "rerank_model",
)

_PAYLOAD_LITERAL = re.compile(r'"extraction_endpoints"\s*:\s*\{')


def _page_assets() -> str:
    static = _ADMIN_BACKEND / "static"
    return "\n".join(
        (static / name).read_text(encoding="utf-8")
        for name in ("admin.html", "admin.js")
    )


def test_the_page_holds_no_endpoint_field_knowledge() -> None:
    page = _page_assets()

    assert "extraction_endpoints" not in page
    for name in ENDPOINT_FIELD_NAMES:
        assert name not in page, name


def test_no_module_builds_a_second_endpoint_payload() -> None:
    offenders = sorted(
        str(path.relative_to(REPO_ROOT))
        for root in (_ADMIN_BACKEND, _AGENT_SRC)
        for path in root.rglob("*.py")
        if _PAYLOAD_LITERAL.search(path.read_text(encoding="utf-8"))
    )

    assert offenders == []


def test_the_running_image_has_a_single_settings_writer() -> None:
    """The admin config route is the only HTTP writer of the settings store."""

    routes = (_ADMIN_BACKEND / "api" / "canonical_v2_admin_config.py").read_text(
        encoding="utf-8"
    )
    writers = re.findall(r'@router\.(patch|put|post)\("(/config)"\)', routes)

    assert writers == [("patch", "/config")]


def test_every_endpoint_path_is_owned_by_the_connection_group() -> None:
    endpoint_paths = {
        path
        for path in flatten_settings(ManagedSettings().model_dump(mode="json"))
        if path.startswith("extraction_endpoints.")
    }

    assert endpoint_paths
    for path in sorted(endpoint_paths):
        spec = FIELD_CATALOG[path]
        assert spec.group == "endpoints", path
        assert spec.connection in {"llm", "embedding", "rerank"}, path
