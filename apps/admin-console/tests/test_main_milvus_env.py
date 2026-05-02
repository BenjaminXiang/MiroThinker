from __future__ import annotations

import importlib
import os
import sys
from types import ModuleType

import pytest


def _fresh_import_backend_main() -> ModuleType:
    sys.modules.pop("backend.main", None)
    backend_package = sys.modules.get("backend")
    if backend_package is not None and hasattr(backend_package, "main"):
        delattr(backend_package, "main")
    return importlib.import_module("backend.main")


def test_main_sets_milvus_real_client_env_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MILVUS_USE_REAL_CLIENT", raising=False)

    _fresh_import_backend_main()

    assert os.environ["MILVUS_USE_REAL_CLIENT"] == "1"


def test_main_preserves_explicit_milvus_real_client_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MILVUS_USE_REAL_CLIENT", "0")

    _fresh_import_backend_main()

    assert os.environ["MILVUS_USE_REAL_CLIENT"] == "0"
