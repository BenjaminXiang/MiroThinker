"""Suite-wide isolation from the machine's operator configuration.

``managed_runtime.apply_managed_runtime_config()`` projects the managed settings and
credentials into ``os.environ`` when a service starts, and those values then persist for
the rest of the process. A developer machine that carries a real
``<tree>/config/managed/settings.json`` — i.e. every configured deployment — therefore
changes what later tests observe through production code: measured 2026-09-23, the switch
line's ``serving_pack_dir`` made ``_parse_args`` pick up ``CANONICAL_V2_SERVING_PACK`` as
its env fallback, so ``test_parse_args_default_has_no_serving_pack`` failed in a full run
and passed in isolation. R16 is "one read at service startup"; a test session is not a
service, so it gets empty files, pinned before the first test runs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

_MANAGED_ENV_VARS = ("CANONICAL_V2_MANAGED_SETTINGS", "CANONICAL_V2_MANAGED_SECRETS")


@pytest.fixture(scope="session", autouse=True)
def _isolate_managed_configuration(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Path]:
    root = tmp_path_factory.mktemp("managed-config")
    settings = root / "settings.json"
    secrets = root / "secrets.json"
    settings.write_text("{}\n", encoding="utf-8")
    secrets.write_text("{}\n", encoding="utf-8")

    overrides = {
        "CANONICAL_V2_MANAGED_SETTINGS": str(settings),
        "CANONICAL_V2_MANAGED_SECRETS": str(secrets),
    }
    previous = {name: os.environ.get(name) for name in _MANAGED_ENV_VARS}
    os.environ.update(overrides)
    try:
        yield root
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
