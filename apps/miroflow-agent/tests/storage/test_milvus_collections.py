"""RED-phase tests for M3 Unit 1 — Milvus collection schema + ensure helpers."""

from __future__ import annotations

from src.data_agents.storage.milvus_collections import (
    PAPER_CHUNKS_COLLECTION,
    drop_paper_chunks_collection,
    ensure_paper_chunks_collection,
)


def _fresh_milvus():
    """Create an in-memory Milvus-Lite client."""
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        from pymilvus import MilvusClient

        return MilvusClient(uri=":memory:")


def test_constant_collection_name():
    assert PAPER_CHUNKS_COLLECTION == "paper_chunks"


def test_ensure_creates_collection_on_fresh_client():
    client = _fresh_milvus()
    assert not client.has_collection(PAPER_CHUNKS_COLLECTION)
    ensure_paper_chunks_collection(client)
    assert client.has_collection(PAPER_CHUNKS_COLLECTION)


def test_ensure_is_idempotent():
    client = _fresh_milvus()
    ensure_paper_chunks_collection(client)
    # Second call must not raise or duplicate.
    ensure_paper_chunks_collection(client)
    assert client.has_collection(PAPER_CHUNKS_COLLECTION)


def test_drop_removes_collection():
    client = _fresh_milvus()
    ensure_paper_chunks_collection(client)
    assert client.has_collection(PAPER_CHUNKS_COLLECTION)
    drop_paper_chunks_collection(client)
    assert not client.has_collection(PAPER_CHUNKS_COLLECTION)


def test_ensure_recreates_after_drop():
    client = _fresh_milvus()
    ensure_paper_chunks_collection(client)
    drop_paper_chunks_collection(client)
    ensure_paper_chunks_collection(client)
    assert client.has_collection(PAPER_CHUNKS_COLLECTION)


def test_module_import_has_no_side_effects():
    """Importing the module should NOT create any Milvus collection."""
    import importlib

    import src.data_agents.storage.milvus_collections as mc

    importlib.reload(mc)
    # Reimport succeeds without side effects. No assertion needed — if the
    # module tried to create a collection on import, the import would fail
    # (no Milvus client constructed at import time).
    assert mc.PAPER_CHUNKS_COLLECTION == "paper_chunks"
