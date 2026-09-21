"""The page's one embedding key must reach the slot the serving lane reads.

The chain (R16, one mechanism): ``/admin`` writes
``config/managed/secrets.json`` → ``managed_runtime.apply_managed_runtime_config``
projects it into the process environment at startup → the serving embedding
authority reads it.

This fleet has **two** embedding authorities and they read **different**
variables:

* the candidate (DashScope / MaaS gateway) authority reads
  ``CANONICAL_V2_EMBEDDING_API_KEY`` — the slot its bundle's frozen
  ``api_key_source`` names, read by
  ``knowledge_build_isolated._load_gateway_embedding_api_key``;
* the recorded (self-hosted) authority reads ``load_local_api_key()`` —
  ``API_KEY`` → ``OPENAI_API_KEY`` → ``SGLANG_API_KEY`` → ``.sglang_api_key``.

So the page's single ``embedding.api_key`` field must occupy both, or a customer
site that fills the key once starves one of the two lines.

What must **not** change is the read side: a bundle may still read only the slot
it declared, so a third-party gateway can never be handed the self-hosted
endpoint's key (that is what makes the two slots different in the first place).

Fixtures: the real store over scratch managed files, the real startup
projection, the real readers. No network, no live state directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data_agents.canonical_v2.knowledge_build_isolated import (
    _GATEWAY_EMBEDDING_API_KEY_ENV,
    _load_gateway_embedding_api_key,
)
from src.data_agents.canonical_v2.managed_config import ManagedSettingsStore
from src.data_agents.canonical_v2.managed_runtime import apply_managed_runtime_config
from src.data_agents.canonical_v2.managed_secrets import (
    SECRET_SPECS,
    ManagedSecretsStore,
)
from src.data_agents.providers.local_api_key import load_local_api_key

# Locally generated fake; no fixture in this file carries a real key.
_KEY = "sk-fake-candidate-0000-1111-4f2a"
_CANDIDATE_SLOT = "CANONICAL_V2_EMBEDDING_API_KEY"
_LOCAL_SLOTS = ("API_KEY", "OPENAI_API_KEY", "SGLANG_API_KEY")


def _stores(tmp_path: Path) -> tuple[ManagedSettingsStore, ManagedSecretsStore]:
    root = tmp_path / "managed"
    return (
        ManagedSettingsStore(root / "settings.json", environ={}),
        ManagedSecretsStore(root / "secrets.json", environ={}, key_file_roots=()),
    )


def _project(
    stores: tuple[ManagedSettingsStore, ManagedSecretsStore], target: dict[str, str]
) -> dict[str, object]:
    settings, secrets = stores
    return apply_managed_runtime_config(
        environ=target, settings_store=settings, secrets_store=secrets
    )


def test_the_embedding_slot_name_matches_the_loader_that_reads_it() -> None:
    """One slot name, two modules: a drift here would starve the switched lane."""

    spec = next(spec for spec in SECRET_SPECS if spec.field == "embedding.api_key")

    assert _GATEWAY_EMBEDDING_API_KEY_ENV in spec.mirror_env_vars


def test_the_page_key_reaches_the_slot_the_loader_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole chain: page write → managed file → projection → reader."""

    stores = _stores(tmp_path)
    stores[1].patch({"embedding.api_key": _KEY}, operator="tester")

    target: dict[str, str] = {}
    receipt = _project(stores, target)
    applied = tuple(receipt["secrets_applied_env"])  # type: ignore[arg-type]

    # The projection decides the names; the readers resolve the value under them.
    assert _CANDIDATE_SLOT in applied
    for name in (*_LOCAL_SLOTS, _CANDIDATE_SLOT):
        if name in applied:
            monkeypatch.setenv(name, target[name])
        else:
            monkeypatch.delenv(name, raising=False)

    assert _load_gateway_embedding_api_key() == _KEY
    assert load_local_api_key(repo_root=tmp_path) == _KEY


def test_the_recorded_slot_keeps_being_filled(tmp_path: Path) -> None:
    """The line that is live today must not lose its credential to the switch."""

    stores = _stores(tmp_path)
    stores[1].patch({"embedding.api_key": _KEY})

    target: dict[str, str] = {}
    _project(stores, target)

    assert target["SGLANG_API_KEY"] == _KEY
    assert target[_CANDIDATE_SLOT] == _KEY


def test_an_environment_value_wins_in_either_slot(tmp_path: Path) -> None:
    """The service unit stays the authority, and the receipt carries names only."""

    stores = _stores(tmp_path)
    stores[1].patch({"embedding.api_key": _KEY})

    target = {"SGLANG_API_KEY": "unit-local-1111", _CANDIDATE_SLOT: "unit-candidate-22"}
    receipt = _project(stores, target)

    assert target["SGLANG_API_KEY"] == "unit-local-1111"
    assert target[_CANDIDATE_SLOT] == "unit-candidate-22"
    assert set(receipt["secrets_skipped_env"]) == {"SGLANG_API_KEY", _CANDIDATE_SLOT}  # type: ignore[arg-type]
    assert _KEY not in json.dumps(receipt)


def test_the_gateway_slot_is_the_only_one_a_candidate_bundle_may_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read side keeps its discipline — which is why the fix is on the write side.

    A bundle pointing at a third-party host must never be handed the self-hosted
    endpoint's key, so the candidate reader takes its own slot and does not fall
    back to ``SGLANG_API_KEY``.
    """

    for name in (*_LOCAL_SLOTS, _CANDIDATE_SLOT):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SGLANG_API_KEY", "self-hosted-only-key")

    assert _load_gateway_embedding_api_key() == ""
