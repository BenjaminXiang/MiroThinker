"""Pure tests for Slice A's read-only DB/Milvus snapshot preflight."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import paper_snapshot_preflight as preflight  # noqa: E402
from paper_snapshot_preflight import (  # noqa: E402
    ActualChunk,
    ExpectedChunk,
    compare_parity,
    hash_canonical_rows,
    hash_float_vector,
)


def test_row_manifest_is_order_independent_but_content_sensitive() -> None:
    rows = [
        {"paper_id": "P2", "title": "two", "year": 2025},
        {"paper_id": "P1", "title": "one", "year": 2024},
    ]
    reversed_rows = list(reversed(rows))
    changed_rows = [dict(rows[0]), {**rows[1], "title": "changed"}]
    assert hash_canonical_rows(rows, identity_fields=("paper_id",)) == (
        hash_canonical_rows(reversed_rows, identity_fields=("paper_id",))
    )
    assert hash_canonical_rows(rows, identity_fields=("paper_id",)) != (
        hash_canonical_rows(changed_rows, identity_fields=("paper_id",))
    )


def test_vector_hash_binds_dimension_order_and_values() -> None:
    base = hash_float_vector([1.0, 2.0, 3.0])
    assert base != hash_float_vector([1.0, 3.0, 2.0])
    assert base != hash_float_vector([1.0, 2.0, 3.001])
    assert base != hash_float_vector([1.0, 2.0])


def test_equal_paper_counts_do_not_hide_different_chunk_identity() -> None:
    expected = (
        ExpectedChunk(
            chunk_id="P1:title:0",
            paper_id="P1",
            content_sha256="a" * 64,
        ),
        ExpectedChunk(
            chunk_id="P2:title:0",
            paper_id="P2",
            content_sha256="b" * 64,
        ),
    )
    actual = (
        ActualChunk(
            chunk_id="P1:title:0",
            paper_id="P1",
            content_sha256="a" * 64,
            vector_sha256="c" * 64,
            vector_dimension=3,
        ),
        ActualChunk(
            chunk_id="P2:obsolete:0",
            paper_id="P2",
            content_sha256="d" * 64,
            vector_sha256="e" * 64,
            vector_dimension=3,
        ),
    )
    report = compare_parity(expected, actual)
    assert report.expected_papers == report.actual_papers == 2
    assert report.paper_id_parity is True
    assert report.chunk_identity_parity is False
    assert report.missing_chunk_ids == ("P2:title:0",)
    assert report.unexpected_chunk_ids == ("P2:obsolete:0",)


def test_matching_chunk_id_with_changed_content_is_stale() -> None:
    expected = (
        ExpectedChunk(
            chunk_id="P1:abstract:0",
            paper_id="P1",
            content_sha256="a" * 64,
        ),
    )
    actual = (
        ActualChunk(
            chunk_id="P1:abstract:0",
            paper_id="P1",
            content_sha256="b" * 64,
            vector_sha256="c" * 64,
            vector_dimension=3,
        ),
    )
    report = compare_parity(expected, actual)
    assert report.stale_content_chunk_ids == ("P1:abstract:0",)
    assert report.chunk_identity_parity is False


def test_unverifiable_vector_tuple_blocks_physical_parity() -> None:
    expected = (
        ExpectedChunk(
            chunk_id="P1:title:0",
            paper_id="P1",
            content_sha256="a" * 64,
        ),
    )
    actual = (
        ActualChunk(
            chunk_id="P1:title:0",
            paper_id="P1",
            content_sha256="a" * 64,
            vector_sha256="c" * 64,
            vector_dimension=3,
            model_version=None,
            chunker_version=None,
            index_version=None,
            write_id=None,
        ),
    )
    report = compare_parity(expected, actual)
    assert report.unverifiable_version_chunk_ids == ("P1:title:0",)
    assert report.physical_version_parity is False


def test_duplicate_expected_chunk_identity_blocks_parity() -> None:
    expected = (
        ExpectedChunk(
            chunk_id="P1:title:0",
            paper_id="P1",
            content_sha256="a" * 64,
        ),
        ExpectedChunk(
            chunk_id="P1:title:0",
            paper_id="P1",
            content_sha256="b" * 64,
        ),
    )
    actual = (
        ActualChunk(
            chunk_id="P1:title:0",
            paper_id="P1",
            content_sha256="a" * 64,
            vector_sha256="c" * 64,
            vector_dimension=3,
            model_version="m1",
            chunker_version="c1",
            index_version="i1",
            write_id="w1",
        ),
    )
    report = compare_parity(expected, actual)
    assert report.conflicting_expected_chunk_ids == ("P1:title:0",)
    assert report.chunk_identity_parity is False


def test_artifact_writer_is_append_only(tmp_path: Path) -> None:
    artifact = tmp_path / "manifest.json"
    preflight._write_json(artifact, {"version": 1})
    preflight._write_json(artifact, {"version": 1})  # identical replay is idempotent
    with pytest.raises(RuntimeError, match="immutable artifact conflict"):
        preflight._write_json(artifact, {"version": 2})
    assert '"version": 1' in artifact.read_text(encoding="utf-8")


def test_evaluator_code_identity_includes_output_dependencies() -> None:
    paths = {path.resolve() for path in getattr(preflight, "RELEVANT_CODE_PATHS", ())}
    required = {
        Path(preflight.__file__).resolve(),
        Path(preflight.__file__).with_name("paper_retrieval_gate.py").resolve(),
        (
            preflight.REPO / "apps/miroflow-agent/src/data_agents/paper/chunker.py"
        ).resolve(),
        (
            preflight.REPO
            / "apps/miroflow-agent/src/data_agents/quality/gating_contract.py"
        ).resolve(),
    }
    assert required <= paths


def test_milvus_manifest_reports_vector_dimension() -> None:
    class FakeClient:
        def describe_collection(self, *, collection_name: str) -> dict:
            assert collection_name == "paper_chunks"
            return {
                "fields": [
                    {"name": "chunk_id", "params": {}},
                    {"name": "content_vector", "params": {"dim": 8}},
                ]
            }

        def list_indexes(self, *, collection_name: str) -> list[str]:
            assert collection_name == "paper_chunks"
            return []

    manifest = preflight._milvus_schema_manifest(FakeClient())
    assert manifest.get("vector_dimension") == 8


def test_query_visible_manifest_includes_professor_affiliations() -> None:
    assert "professor_affiliation" in preflight.QUERY_VISIBLE_TABLES
