# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import inspect
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import get_type_hints

import pytest


_COMPAT_MODULE = "src.data_agents.providers.openai_client_compat"
_ISOLATED_IMPORT = textwrap.dedent(
    """
    import importlib
    import inspect
    import sys
    from pathlib import Path

    package_root, provider_name, provider_class_name = sys.argv[1:]
    sys.path.insert(0, package_root)

    provider_module = importlib.import_module(provider_name)
    compat_module = importlib.import_module(
        "src.data_agents.providers.openai_client_compat"
    )
    provider_class = getattr(provider_module, provider_class_name)
    factory = compat_module.build_openai_client

    assert provider_module.build_openai_client is factory
    assert provider_class().client_factory is factory
    assert factory.__module__ == compat_module.__name__
    assert Path(inspect.getsourcefile(factory)).resolve() == Path(
        compat_module.__file__
    ).resolve()
    assert Path(compat_module.__file__).resolve() == Path(
        package_root,
        "src",
        "data_agents",
        "providers",
        "openai_client_compat.py",
    ).resolve()
    """
)


def _load_compat_module():
    return importlib.import_module(_COMPAT_MODULE)


@pytest.mark.parametrize(
    ("provider_name", "provider_class_name"),
    [
        ("src.data_agents.providers.qwen", "QwenProvider"),
        ("src.data_agents.providers.mirothinker", "MiroThinkerProvider"),
    ],
    ids=("qwen", "mirothinker"),
)
def test_provider_import_uses_packaged_compat_helper(
    tmp_path: Path,
    provider_name: str,
    provider_class_name: str,
) -> None:
    package_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    assert not any(tmp_path.iterdir())

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            _ISOLATED_IMPORT,
            str(package_root),
            provider_name,
            provider_class_name,
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_build_openai_client_uses_exact_primary_construction(monkeypatch) -> None:
    compat = _load_compat_module()
    signature = inspect.signature(compat.build_openai_client)
    assert tuple(signature.parameters) == ("base_url", "api_key", "timeout")
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    assert all(
        parameter.default is inspect.Parameter.empty
        for parameter in signature.parameters.values()
    )
    assert get_type_hints(compat.build_openai_client) == {
        "base_url": str,
        "api_key": str,
        "timeout": float,
        "return": compat.openai.Client,
    }

    client = object()
    calls = []

    def fake_client(**kwargs):
        calls.append(kwargs)
        return client

    def unexpected_http_client(**kwargs):
        raise AssertionError(f"unexpected fallback: {kwargs}")

    monkeypatch.setattr(compat.openai, "Client", fake_client)
    monkeypatch.setattr(compat.openai, "DefaultHttpxClient", unexpected_http_client)

    assert (
        compat.build_openai_client(
            base_url="https://provider.example/v1",
            api_key="test-key",
            timeout=12.5,
        )
        is client
    )
    assert calls == [
        {
            "base_url": "https://provider.example/v1",
            "api_key": "test-key",
            "timeout": 12.5,
        }
    ]


@pytest.mark.parametrize(
    "compatibility_error",
    [
        ImportError("optional dependency socksio is unavailable"),
        TypeError("Client.__init__() got an unexpected keyword argument 'proxies'"),
    ],
    ids=("socksio", "proxies"),
)
def test_build_openai_client_retries_exact_compatibility_errors(
    monkeypatch,
    compatibility_error: Exception,
) -> None:
    compat = _load_compat_module()
    client = object()
    http_client = object()
    client_calls = []
    http_client_calls = []

    def fake_client(**kwargs):
        client_calls.append(kwargs)
        if len(client_calls) == 1:
            raise compatibility_error
        return client

    def fake_http_client(**kwargs):
        http_client_calls.append(kwargs)
        return http_client

    monkeypatch.setattr(compat.openai, "Client", fake_client)
    monkeypatch.setattr(compat.openai, "DefaultHttpxClient", fake_http_client)

    assert (
        compat.build_openai_client(
            base_url="https://provider.example/v1",
            api_key="test-key",
            timeout=9.0,
        )
        is client
    )
    assert client_calls == [
        {
            "base_url": "https://provider.example/v1",
            "api_key": "test-key",
            "timeout": 9.0,
        },
        {
            "base_url": "https://provider.example/v1",
            "api_key": "test-key",
            "timeout": 9.0,
            "http_client": http_client,
        },
    ]
    assert http_client_calls == [{"timeout": 9.0, "trust_env": False}]


@pytest.mark.parametrize(
    "non_compatibility_error",
    [
        ImportError("unrelated optional dependency is unavailable"),
        TypeError("Client.__init__() got an unexpected keyword argument 'transport'"),
    ],
    ids=("unrelated-import-error", "unrelated-type-error"),
)
def test_build_openai_client_propagates_non_matching_errors(
    monkeypatch,
    non_compatibility_error: Exception,
) -> None:
    compat = _load_compat_module()

    def fake_client(**kwargs):
        raise non_compatibility_error

    def unexpected_http_client(**kwargs):
        raise AssertionError(f"unexpected fallback: {kwargs}")

    monkeypatch.setattr(compat.openai, "Client", fake_client)
    monkeypatch.setattr(compat.openai, "DefaultHttpxClient", unexpected_http_client)

    with pytest.raises(type(non_compatibility_error)) as caught:
        compat.build_openai_client(
            base_url="https://provider.example/v1",
            api_key="test-key",
            timeout=3.0,
        )

    assert caught.value is non_compatibility_error
