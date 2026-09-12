"""Unit tests for the derived lexical index (retrieval-v2 Step 1)."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from src.data_agents.canonical_v2 import lexical_index as lex


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _document(
    *,
    document_id: str,
    canonical_id: str,
    domain: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "canonical_object_id": canonical_id,
        "release_id": "candidate-v2-test-r1",
        "domain": domain,
        "lookup_content": json.dumps(payload, ensure_ascii=False),
    }


def _lookup_db(tmp_path: Path, documents: list[dict[str, Any]]) -> Path:
    path = tmp_path / "lookup.sqlite3"
    connection = sqlite3.connect(str(path))
    try:
        connection.execute(
            "CREATE TABLE lookup_document("
            "document_id TEXT PRIMARY KEY, release_id TEXT, projection_id TEXT, "
            "canonical_object_id TEXT, document_json TEXT)"
        )
        connection.executemany(
            "INSERT INTO lookup_document VALUES (?, ?, ?, ?, ?)",
            [
                (
                    document["document_id"],
                    document["release_id"],
                    "lookup:exact-lookup:test",
                    document["canonical_object_id"],
                    json.dumps(document, ensure_ascii=False),
                )
                for document in documents
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return path


_DICTIONARY_WORDS = (
    "大疆",
    "优必选",
    "则成电子",
    "顺易捷",
    "深南电路",
    "激光雷达",
)


def _build(tmp_path: Path, documents: list[dict[str, Any]]) -> tuple[Path, Path]:
    lookup = _lookup_db(tmp_path, documents)
    out_dir = tmp_path / "artifact"
    lex.build_lexical_index(
        lookup_sqlite=lookup,
        out_dir=out_dir,
        release_id="candidate-v2-test-r1",
        dictionary_words=_DICTIONARY_WORDS,
        built_at=NOW.isoformat(),
    )
    return lookup, out_dir


def test_entity_names_segment_as_whole_words() -> None:
    segmenter = lex.Segmenter(_DICTIONARY_WORDS)
    assert "优必选" in segmenter.tokens("深圳市优必选科技股份有限公司")
    assert "则成电子" in segmenter.tokens("深圳市则成电子股份有限公司")
    assert "深南电路" in segmenter.tokens("深南电路股份有限公司")
    # Without the dictionary the same text fragments (the defect the
    # dictionary exists to fix).
    plain = lex.Segmenter(())
    assert "优必选" not in plain.tokens("优必选")


def test_segmentation_matches_between_build_and_query(tmp_path: Path) -> None:
    documents = [
        _document(
            document_id="doc:u",
            canonical_id="company-c-u",
            domain="company",
            payload={
                "name": "深圳市优必选科技股份有限公司",
                "profile_summary": "人形机器人企业，产品覆盖服务与工业场景。",
            },
        ),
        _document(
            document_id="doc:z",
            canonical_id="company-c-z",
            domain="company",
            payload={
                "name": "深圳市则成电子股份有限公司",
                "tech_tags": [{"name": "PCB"}],
            },
        ),
    ]
    lookup, out_dir = _build(tmp_path, documents)
    index = lex.LexicalIndex.open(
        out_dir,
        expected_release_id="candidate-v2-test-r1",
        lookup_sqlite=lookup,
    )
    assert index is not None
    hits = index.search("优必选", domains=("company",), limit=5)
    assert [document_id for document_id, _ in hits] == ["doc:u"]
    assert index.search("则成电子", domains=("company",), limit=5)[0][0] == "doc:z"
    assert index.search("大疆", domains=("company",), limit=5) == ()


def test_field_weights_prefer_name_over_body(tmp_path: Path) -> None:
    documents = [
        _document(
            document_id="doc:name",
            canonical_id="company-c-name",
            domain="company",
            payload={"name": "深圳市启航激光雷达有限公司"},
        ),
        _document(
            document_id="doc:body",
            canonical_id="company-c-body",
            domain="company",
            payload={
                "name": "深圳某某设备有限公司",
                "profile_summary": "公司业务涉及激光雷达下游集成。",
            },
        ),
    ]
    lookup, out_dir = _build(tmp_path, documents)
    index = lex.LexicalIndex.open(
        out_dir, expected_release_id="candidate-v2-test-r1", lookup_sqlite=lookup
    )
    assert index is not None
    hits = index.search("激光雷达", domains=("company",), limit=5)
    assert [document_id for document_id, _ in hits][0] == "doc:name"


def test_multi_term_query_is_a_ranked_sample(tmp_path: Path) -> None:
    documents = [
        _document(
            document_id="doc:both",
            canonical_id="company-c-both",
            domain="company",
            payload={
                "name": "深圳顺易捷科技有限公司",
                "tech_tags": [{"name": "PCB打样"}],
            },
        ),
        _document(
            document_id="doc:one",
            canonical_id="company-c-one",
            domain="company",
            payload={"name": "深圳某某科技有限公司", "profile_summary": "PCB 生产。"},
        ),
    ]
    lookup, out_dir = _build(tmp_path, documents)
    index = lex.LexicalIndex.open(
        out_dir, expected_release_id="candidate-v2-test-r1", lookup_sqlite=lookup
    )
    assert index is not None
    hits = index.search("顺易捷 PCB打样", domains=("company",), limit=5, mode="or")
    assert [document_id for document_id, _ in hits] == ["doc:both", "doc:one"]


def test_hash_and_decision_fields_never_reach_the_index(tmp_path: Path) -> None:
    documents = [
        _document(
            document_id="doc:h",
            canonical_id="company-c-h",
            domain="company",
            payload={
                "name": "深圳市和谐科技有限公司",
                "content_sha256": "deadbeef" * 8,
                "identity_decision_id": "identity-decision:0123456789abcdef",
            },
        )
    ]
    lookup, out_dir = _build(tmp_path, documents)
    index = lex.LexicalIndex.open(
        out_dir, expected_release_id="candidate-v2-test-r1", lookup_sqlite=lookup
    )
    assert index is not None
    assert index.search("deadbeef", domains=("company",), limit=5) == ()
    assert index.search("identity-decision", domains=("company",), limit=5) == ()


def test_manifest_bindings_refuse_mismatches(tmp_path: Path) -> None:
    documents = [
        _document(
            document_id="doc:a",
            canonical_id="company-c-a",
            domain="company",
            payload={"name": "深圳市阿尔法科技有限公司"},
        )
    ]
    lookup, out_dir = _build(tmp_path, documents)

    with pytest.raises(lex.LexicalIndexIntegrityError):
        lex.LexicalIndex.open(out_dir, expected_release_id="candidate-v2-other-r9")

    manifest_path = out_dir / lex.MANIFEST_FILENAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "canonical-v2-lexical-index-v0"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(lex.LexicalIndexIntegrityError):
        lex.LexicalIndex.open(out_dir, expected_release_id="candidate-v2-test-r1")


def test_pack_stat_mismatch_refused(tmp_path: Path) -> None:
    documents = [
        _document(
            document_id="doc:a",
            canonical_id="company-c-a",
            domain="company",
            payload={"name": "深圳市阿尔法科技有限公司"},
        )
    ]
    lookup, out_dir = _build(tmp_path, documents)
    # Touch the source database so its stat fingerprint moves.
    with sqlite3.connect(str(lookup)) as connection:
        connection.execute(
            "INSERT INTO lookup_document VALUES "
            "('doc:new', 'candidate-v2-test-r1', 'p', 'company-c-new', '{}')"
        )
    with pytest.raises(lex.LexicalIndexIntegrityError):
        lex.LexicalIndex.open(
            out_dir, expected_release_id="candidate-v2-test-r1", lookup_sqlite=lookup
        )


def test_missing_artifact_returns_none(tmp_path: Path) -> None:
    assert (
        lex.LexicalIndex.open(
            tmp_path / "absent", expected_release_id="candidate-v2-test-r1"
        )
        is None
    )


def test_build_is_idempotent_and_does_not_touch_the_source(tmp_path: Path) -> None:
    documents = [
        _document(
            document_id="doc:a",
            canonical_id="company-c-a",
            domain="company",
            payload={"name": "深圳市阿尔法科技有限公司"},
        )
    ]
    lookup = _lookup_db(tmp_path, documents)
    before = lex.sha256_file(lookup)
    out_dir = tmp_path / "artifact"
    lex.build_lexical_index(
        lookup_sqlite=lookup,
        out_dir=out_dir,
        release_id="candidate-v2-test-r1",
        dictionary_words=_DICTIONARY_WORDS,
        built_at=NOW.isoformat(),
    )
    first_manifest = (out_dir / lex.MANIFEST_FILENAME).read_text(encoding="utf-8")
    lex.build_lexical_index(
        lookup_sqlite=lookup,
        out_dir=out_dir,
        release_id="candidate-v2-test-r1",
        dictionary_words=_DICTIONARY_WORDS,
        built_at="2026-09-12T23:00:00+00:00",
    )
    second_manifest = (out_dir / lex.MANIFEST_FILENAME).read_text(encoding="utf-8")
    assert first_manifest == second_manifest
    assert lex.sha256_file(lookup) == before


def test_domain_filter_limits_hits(tmp_path: Path) -> None:
    documents = [
        _document(
            document_id="doc:c",
            canonical_id="company-c-c",
            domain="company",
            payload={"name": "深圳市阿尔法机器人有限公司"},
        ),
        _document(
            document_id="doc:p",
            canonical_id="professor-c-p",
            domain="professor",
            payload={
                "name": "某某教授",
                "profile_summary": "任职于深圳市阿尔法机器人有限公司",
            },
        ),
    ]
    lookup, out_dir = _build(tmp_path, documents)
    index = lex.LexicalIndex.open(
        out_dir, expected_release_id="candidate-v2-test-r1", lookup_sqlite=lookup
    )
    assert index is not None
    assert [
        hit[0] for hit in index.search("阿尔法", domains=("company",), limit=5)
    ] == ["doc:c"]
    assert [
        hit[0] for hit in index.search("阿尔法", domains=("professor",), limit=5)
    ] == ["doc:p"]


def test_phrase_mode_requires_token_adjacency(tmp_path: Path) -> None:
    """Quoted raw CJK is ONE FTS5 token; the phrase must be built from the
    segmented tokens ("激光" "雷达"), and adjacency is what keeps the
    laser-equipment class out of a laser-radar query."""
    documents = [
        _document(
            document_id="doc:radar",
            canonical_id="company-c-radar",
            domain="company",
            payload={
                "name": "深圳市镭神智能系统有限公司",
                "profile_summary": "专注激光雷达产品研发与量产。",
            },
        ),
        _document(
            document_id="doc:laser",
            canonical_id="company-c-laser",
            domain="company",
            payload={
                "name": "深圳市某某激光设备有限公司",
                "profile_summary": "工业激光设备研发。",
            },
        ),
    ]
    lookup, out_dir = _build(tmp_path, documents)
    index = lex.LexicalIndex.open(
        out_dir, expected_release_id="candidate-v2-test-r1", lookup_sqlite=lookup
    )
    assert index is not None
    phrase_hits = [hit[0] for hit in index.search("激光雷达", limit=5, mode="phrase")]
    or_hits = [hit[0] for hit in index.search("激光雷达", limit=5, mode="or")]
    assert phrase_hits == ["doc:radar"]
    assert set(or_hits) == {"doc:radar", "doc:laser"}


def test_phrase_mode_matches_segmented_terms(tmp_path: Path) -> None:
    """储能电池 segments to 储能+电池 on both sides; the naive raw quoted
    phrase returned 0 hits against this pack (measured 2026-09-12)."""
    documents = [
        _document(
            document_id="doc:storage",
            canonical_id="company-c-storage",
            domain="company",
            payload={
                "name": "深圳市某某储能科技有限公司",
                "profile_summary": "储能电池系统集成与销售。",
            },
        )
    ]
    lookup, out_dir = _build(tmp_path, documents)
    index = lex.LexicalIndex.open(
        out_dir, expected_release_id="candidate-v2-test-r1", lookup_sqlite=lookup
    )
    assert index is not None
    assert [hit[0] for hit in index.search("储能电池", limit=5, mode="phrase")] == [
        "doc:storage"
    ]


def test_lane_document_selection_is_phrase_first_then_or_fill(tmp_path: Path) -> None:
    """The lane helper: adjacency pass first, OR fill only when thin."""
    from src.data_agents.canonical_v2.knowledge_read_isolated import (
        _indexed_lexical_document_ids,
    )

    documents = [
        _document(
            document_id="doc:radar",
            canonical_id="company-c-radar",
            domain="company",
            payload={
                "name": "深圳市镭神智能系统有限公司",
                "profile_summary": "专注激光雷达产品研发与量产。",
            },
        ),
        _document(
            document_id="doc:laser",
            canonical_id="company-c-laser",
            domain="company",
            payload={
                "name": "深圳市某某激光设备有限公司",
                "profile_summary": "工业激光设备研发。",
            },
        ),
    ]
    lookup, out_dir = _build(tmp_path, documents)
    index = lex.LexicalIndex.open(
        out_dir, expected_release_id="candidate-v2-test-r1", lookup_sqlite=lookup
    )
    assert index is not None
    selected = _indexed_lexical_document_ids(
        index=index,
        query_phrase="激光雷达",
        domains=("company",),
        max_candidates=10,
    )
    assert selected[0] == "doc:radar"
    assert "doc:laser" in selected  # OR fill restores ranked-sample recall


def test_open_cache_hides_nothing_and_pins_successes(tmp_path: Path) -> None:
    """A rejected artifact must not be cached: rebuilding it has to take
    effect without restarting the serving process."""
    documents = [
        _document(
            document_id="doc:a",
            canonical_id="company-c-a",
            domain="company",
            payload={"name": "深圳市阿尔法科技有限公司"},
        )
    ]
    lookup, out_dir = _build(tmp_path, documents)
    artifact_root = tmp_path / "derived"

    def _open() -> lex.LexicalIndex | None:
        return lex.open_lexical_index(
            artifact_root=artifact_root,
            release_id="candidate-v2-test-r1",
            lookup_sqlite=lookup,
        )

    assert _open() is None  # nothing published yet
    (artifact_root / "candidate-v2-test-r1").parent.mkdir(parents=True, exist_ok=True)
    out_dir.rename(artifact_root / "candidate-v2-test-r1")
    first = _open()
    assert first is not None  # the rebuild is picked up by the next call
    assert _open() is first  # and once open, the index is cached
