"""Embedding endpoint resolution: identity frozen, address operational (F2.1/F2.2).

Cluster D of
`.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/verification-contract.md`.

Fixture source: a bundle-document fixture written to a temporary file. It is the
verbatim frozen qwen document (its `content_sha256` is the sha256 of the document
itself), so the loader's full verification chain runs for real. No repository
bundle file is ever edited.
"""

from __future__ import annotations

import hashlib
from importlib import import_module
import json
from pathlib import Path
from typing import Any

import pytest

BUILD_MODULE = "src.data_agents.canonical_v2.knowledge_build_isolated"
ENV = "CANONICAL_V2_EMBEDDING_BASE_URL"
RECORDED_BASE_URL = "http://100.64.0.27:18005/v1"

FROZEN_DOCUMENT: dict[str, Any] = {
    "schema_version": "canonical-v2-openai-compatible-embedding-bundle-v1",
    "provider": "openai-compatible",
    "model_id": "Qwen/Qwen3-Embedding-8B",
    "dimension": 4096,
    "base_url": RECORDED_BASE_URL,
    "api_key_source": "local_api_key",
    "batch_size": 32,
    "max_workers": 32,
    "timeout_seconds": 180,
    "content_sha256": "05473fabc8055e9ce3ebca9d846761cab7cb8c89eb51c96607172c402d1f46db",
}


def _module() -> Any:
    return import_module(BUILD_MODULE)


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _write_bundle(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "embedding-bundle.json"
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return path


def _resealed(document: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """The document with *changes* applied and its self-hash recomputed."""

    updated = {**document, **changes}
    updated.pop("content_sha256", None)
    return {**updated, "content_sha256": _canonical_sha256(updated)}


def test_the_fixture_is_the_frozen_document() -> None:
    """Guard: the fixture must be the real frozen bundle, not a loosened copy."""

    payload = {k: v for k, v in FROZEN_DOCUMENT.items() if k != "content_sha256"}
    assert _canonical_sha256(payload) == FROZEN_DOCUMENT["content_sha256"]


def test_the_operator_address_wins_over_the_recorded_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV, "http://10.20.30.40:9000/v1")

    adapter = _module().load_content_addressed_embedding_adapter(
        _write_bundle(tmp_path, FROZEN_DOCUMENT)
    )

    assert adapter.base_url == "http://10.20.30.40:9000/v1"
    assert adapter.model_id == "Qwen/Qwen3-Embedding-8B"
    assert adapter.dimension == 4096


def test_without_the_setting_the_recorded_address_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV, raising=False)

    adapter = _module().load_content_addressed_embedding_adapter(
        _write_bundle(tmp_path, FROZEN_DOCUMENT)
    )

    assert adapter.base_url == RECORDED_BASE_URL


def test_a_blank_setting_falls_back_to_the_recorded_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV, "   ")

    adapter = _module().load_content_addressed_embedding_adapter(
        _write_bundle(tmp_path, FROZEN_DOCUMENT)
    )

    assert adapter.base_url == RECORDED_BASE_URL


def test_the_effective_address_is_stripped_and_keeps_its_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV, "  https://embed.example.cn:8443/v1  ")

    assert (
        _module().resolve_embedding_base_url(RECORDED_BASE_URL)
        == "https://embed.example.cn:8443/v1"
    )


def test_a_non_http_effective_address_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    for value in (
        "embed.example.cn/v1",
        "ftp://embed.example.cn/v1",
        "/v1",
        "https://",
    ):
        monkeypatch.setenv(ENV, value)
        with pytest.raises(ValueError):
            module.resolve_embedding_base_url(RECORDED_BASE_URL)


def test_a_non_http_recorded_address_is_refused_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    monkeypatch.delenv(ENV, raising=False)
    for value in ("", "   ", "embed.example.cn/v1"):
        with pytest.raises(ValueError):
            module.resolve_embedding_base_url(value)


def test_the_identity_gates_still_reject_a_changed_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    monkeypatch.delenv(ENV, raising=False)
    resealed = {
        "model identity": {"model_id": "Qwen/Qwen3-Embedding-4B"},
        "dimension": {"dimension": 1024},
    }
    for name, change in resealed.items():
        document = _resealed(FROZEN_DOCUMENT, **change)
        with pytest.raises(ValueError):
            module.load_content_addressed_embedding_adapter(
                _write_bundle(tmp_path, document)
            )
        assert name

    # A foreign content hash: the document says one thing, its own bytes another.
    forged = {**FROZEN_DOCUMENT, "content_sha256": "0" * 64}
    with pytest.raises(ValueError):
        module.load_content_addressed_embedding_adapter(_write_bundle(tmp_path, forged))


def test_a_resealed_bundle_with_another_address_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The frozen hash covers every recorded field — including the address.

    This is why the operator's address lives in the environment rather than in
    the bundle: the bundle stays byte-frozen (no reseal, no rebuild), and the
    address is moved at the one resolution point.
    """

    module = _module()
    monkeypatch.delenv(ENV, raising=False)
    document = _resealed(FROZEN_DOCUMENT, base_url="http://10.20.30.40:9000/v1")

    assert document["content_sha256"] != FROZEN_DOCUMENT["content_sha256"]
    with pytest.raises(ValueError):
        module.load_content_addressed_embedding_adapter(
            _write_bundle(tmp_path, document)
        )


def test_the_address_is_not_part_of_the_frozen_identity_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identity comparison drops ``base_url`` on both sides (F2.1).

    The provider dispatch moved the expected documents into
    ``_OPENAI_COMPATIBLE_EMBEDDING_AUTHORITIES``, so the guarantee is asserted
    where it now lives: behaviourally, through the one comparison seam every
    branch uses. A bundle that differs from its registered authority *only* in
    the recorded address still loads, and the address it then uses is its own
    recorded one (the resolver's fallback).
    """

    import inspect

    module = _module()
    monkeypatch.delenv(ENV, raising=False)
    elsewhere = "https://elsewhere.invalid/v1"
    resealed = _resealed(FROZEN_DOCUMENT, base_url=elsewhere)
    monkeypatch.setattr(
        module,
        "_OPENAI_COMPATIBLE_EMBEDDING_AUTHORITIES",
        (
            (
                # Same authority in every field but the address: the hash is the
                # bundle's own (so the document passes its self-hash check), and
                # only `base_url` differs from the registered copy.
                {**resealed, "base_url": RECORDED_BASE_URL},
                module._OpenAICompatibleEmbeddingAdapter,
            ),
        ),
    )

    adapter = module.load_content_addressed_embedding_adapter(
        _write_bundle(tmp_path, resealed)
    )

    assert adapter.base_url == elsewhere
    assert adapter.model_id == FROZEN_DOCUMENT["model_id"]
    # The seam itself: both sides of the comparison skip the address, and the new
    # provider branches go through it rather than comparing documents themselves.
    assert (
        inspect.getsource(module._matches_frozen_authority).count('key != "base_url"')
        == 2
    )
    for function in (
        module.load_content_addressed_embedding_adapter,
        module._load_dashscope_native_embedding_adapter,
    ):
        assert "_matches_frozen_authority(document, expected)" in (
            inspect.getsource(function)
        )


def test_the_resolution_precedence_has_exactly_one_reader() -> None:
    """Only the resolver reads the variable — no second, drifting code path."""

    module_path = Path(import_module(BUILD_MODULE).__file__ or "")
    source_root = module_path.parents[2]
    readers = sorted(
        str(path.relative_to(source_root))
        for path in source_root.rglob("*.py")
        if ENV in path.read_text(encoding="utf-8")
    )

    assert readers == [
        str(module_path.relative_to(source_root)),
        "data_agents/canonical_v2/managed_config.py",
    ], readers
