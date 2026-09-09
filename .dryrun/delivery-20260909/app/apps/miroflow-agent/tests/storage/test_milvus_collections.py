"""RED-phase tests for M3 Unit 1 — Milvus collection schema + ensure helpers."""

from __future__ import annotations

from src.data_agents.storage.milvus_collections import (
    PAPER_CHUNKS_COLLECTION,
    PROFESSOR_IDENTITY_PROFILES_COLLECTION,
    drop_paper_chunks_collection,
    drop_professor_identity_profiles_collection,
    drop_professor_research_profiles_collection,
    ensure_paper_chunks_collection,
    ensure_professor_identity_profiles_collection,
    ensure_professor_research_profiles_collection,
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


def _schema_field_names(client, collection_name: str) -> set[str]:
    schema = client._delegate._collections[collection_name]["schema"]
    return {field.name for field in schema.fields}


def test_professor_split_collection_names_and_legacy_name_are_available():
    import src.data_agents.storage.milvus_collections as mc

    assert mc.PROFESSOR_PROFILES_COLLECTION == "professor_profiles"
    assert mc.PROFESSOR_IDENTITY_PROFILES_COLLECTION == "professor_identity_profiles"
    assert mc.PROFESSOR_RESEARCH_PROFILES_COLLECTION == "professor_research_profiles"


def test_ensure_creates_professor_identity_collection_with_identity_vector():
    client = _fresh_milvus()

    ensure_professor_identity_profiles_collection(client)

    assert client.has_collection(PROFESSOR_IDENTITY_PROFILES_COLLECTION)
    fields = _schema_field_names(client, PROFESSOR_IDENTITY_PROFILES_COLLECTION)
    assert {"id", "name", "institution", "department", "title", "identity_text"} <= fields
    assert "identity_vector" in fields
    assert "research_vector" not in fields


def test_ensure_creates_professor_research_collection_with_research_vector():
    client = _fresh_milvus()

    ensure_professor_research_profiles_collection(client)

    assert client.has_collection("professor_research_profiles")
    fields = _schema_field_names(client, "professor_research_profiles")
    assert {
        "id",
        "research_text",
        "research_directions",
        "profile_summary",
        "paper_summary",
        "patent_summary",
    } <= fields
    assert "research_vector" in fields
    assert "identity_vector" not in fields


def test_drop_removes_professor_split_collections():
    client = _fresh_milvus()
    ensure_professor_identity_profiles_collection(client)
    ensure_professor_research_profiles_collection(client)

    drop_professor_identity_profiles_collection(client)
    drop_professor_research_profiles_collection(client)

    assert not client.has_collection("professor_identity_profiles")
    assert not client.has_collection("professor_research_profiles")


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
