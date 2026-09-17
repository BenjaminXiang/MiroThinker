"""R7 — the human-review workspace is gone from the admin console.

Locks: `/review` and `/api/review/*` answer 404, the review modules and static
assets are absent, and no production module under ``backend/`` or ``scripts/``
carries a retired review token any more.
"""

from __future__ import annotations

import importlib
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

from backend.main import app


_APP_ROOT = Path(__file__).resolve().parents[1]
_SCANNED_ROOTS = (_APP_ROOT / "backend", _APP_ROOT / "scripts")
_FORBIDDEN_TOKENS = (
    "canonical_v2_review",
    "create_canonical_v2_review_app",
    "get_canonical_v2_review_workspace",
    "ReviewWorkspace",
    "include_review",
    "review_presentation",
    "18189",
    "review.html",
)
_RETIRED_FILES = (
    "backend/api/canonical_v2_review.py",
    "backend/services/canonical_v2_review.py",
    "backend/static/review.html",
    "backend/static/review.js",
    "backend/static/review.css",
    "backend/static/review_mutation_coordinator.js",
    "backend/static/review_presentation.js",
    "scripts/run_canonical_v2_review.py",
    "tests/test_canonical_v2_review_workspace.py",
    "tests/test_canonical_v2_review_http.py",
    "tests/test_canonical_v2_review_launcher.py",
    "tests/test_canonical_v2_review_ui.py",
)


@pytest.mark.parametrize("relative", _RETIRED_FILES)
def test_retired_review_files_are_deleted(relative: str) -> None:
    assert not (_APP_ROOT / relative).exists()


def test_review_routes_answer_not_found() -> None:
    client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)

    assert client.get("/review").status_code == 404
    assert client.get("/api/review/workspace").status_code == 404
    assert client.post("/api/review/decisions", json={}).status_code == 404


def test_retired_review_modules_are_not_importable() -> None:
    for name in ("backend.api.canonical_v2_review", "backend.services.canonical_v2_review"):
        sys.modules.pop(name, None)
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(name)


def test_no_production_module_mentions_a_retired_review_token() -> None:
    offenders: list[str] = []
    for root in _SCANNED_ROOTS:
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for token in _FORBIDDEN_TOKENS:
                if token in text:
                    offenders.append(f"{path.relative_to(_APP_ROOT)}: {token}")

    assert offenders == []


def test_review_is_not_mounted_on_the_route_shell() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/review" not in paths
    assert not any(path.startswith("/api/review") for path in paths)
