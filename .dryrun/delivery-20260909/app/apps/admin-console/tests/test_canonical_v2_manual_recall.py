from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.services.canonical_v2_manual_recall import (
    SCHEMA_VERSION,
    ManualRecallError,
    ManualRecallStore,
    chunk_document_text,
    serialize_manual_record,
)


class _FakeEmbeddingAdapter:
    def __init__(self, dimension: int = 8, *, fail: bool = False) -> None:
        self.dimension = dimension
        self._fail = fail
        self.calls: list[tuple[str, ...]] = []

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.calls.append(tuple(texts))
        if self._fail:
            raise RuntimeError("embedding service down")
        return tuple(
            tuple(float((len(text) + index) % 7 + 1) for index in range(self.dimension))
            for text in texts
        )


def _store(root: Path, dimension: int = 8) -> ManualRecallStore:
    return ManualRecallStore(root, _FakeEmbeddingAdapter(dimension))


# -- chunker -----------------------------------------------------------------


def test_chunker_packs_paragraphs_up_to_max_chars() -> None:
    text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
    chunks = chunk_document_text(text, max_chars=20)
    assert chunks == ["第一段内容。\n\n第二段内容。", "第三段内容。"]


def test_chunker_hard_slices_overlong_paragraph() -> None:
    text = "x" * 45
    chunks = chunk_document_text(text, max_chars=20)
    assert chunks == ["x" * 20, "x" * 20, "x" * 5]


def test_chunker_normalizes_crlf_and_strips() -> None:
    chunks = chunk_document_text("  甲\r\n\r\n乙  ", max_chars=100)
    assert chunks == ["甲\n\n乙"]


def test_chunker_rejects_empty_text() -> None:
    with pytest.raises(ManualRecallError, match="empty"):
        chunk_document_text("   \n  ")


def test_chunker_enforces_document_ceiling() -> None:
    text = "\n\n".join(f"段落{i}" for i in range(201))
    with pytest.raises(ManualRecallError, match="200 chunks"):
        chunk_document_text(text, max_chars=4)


# -- serialize ----------------------------------------------------------------


def test_serialize_company_keeps_release_shape_keys() -> None:
    raw = serialize_manual_record(
        "company",
        {"name": "测试企业", "profile_summary": "简介", "unknown_field": "丢弃"},
    )
    content = json.loads(raw)
    assert content == {"name": "测试企业", "profile_summary": "简介"}


def test_serialize_paper_uses_title_key() -> None:
    content = json.loads(serialize_manual_record("paper", {"title": "论文标题"}))
    assert content == {"title": "论文标题"}


def test_serialize_rejects_unsupported_domain() -> None:
    with pytest.raises(ManualRecallError, match="unsupported domain"):
        serialize_manual_record("government", {"name": "x"})


def test_serialize_rejects_payload_without_known_fields() -> None:
    with pytest.raises(ManualRecallError, match="no serializable fields"):
        serialize_manual_record("company", {"credit_code": "9144"})


# -- add_upload ----------------------------------------------------------------


def test_add_upload_persists_active_chunk_points(tmp_path: Path) -> None:
    store = _store(tmp_path)
    doc_id, count = store.add_upload(
        domain="company",
        company_name="测试企业",
        title="企业介绍",
        text="第一段。\n\n第二段。",
        reason="补充企业资料",
        operator="admin",
        source_label="intro.txt",
        matched_canonical_id=None,
    )
    assert doc_id.startswith("doc-")
    assert count == 1

    points = store.active_points()
    assert len(points) == 1
    point = points[0]
    assert point.kind == "upload_chunk"
    assert point.domain == "company"
    assert point.display_name == "测试企业"
    assert point.canonical_ref == f"manual-upload:{doc_id}"
    assert point.ref_id == doc_id
    assert point.status == "active"
    assert point.doc_title == "企业介绍"
    embedded = json.loads(point.embedded_content)
    assert embedded["name"] == "测试企业"
    assert "第一段" in embedded["profile_summary"]
    assert len(point.vector) == 8

    payload = json.loads(store.store_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert len(payload["points"]) == 1
    assert (os.stat(store.store_path).st_mode & 0o777) == 0o600


def test_add_upload_uses_matched_canonical_ref(tmp_path: Path) -> None:
    store = _store(tmp_path)
    doc_id, _ = store.add_upload(
        domain="company",
        company_name="测试企业",
        title="",
        text="内容。",
        reason="补充",
        operator="admin",
        source_label="a.txt",
        matched_canonical_id="company-c-4cacc13aa38cae5b1c53149a",
    )
    assert store.active_points()[0].canonical_ref == "company-c-4cacc13aa38cae5b1c53149a"
    assert doc_id.startswith("doc-")


def test_add_upload_validates_inputs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ManualRecallError, match="company_name"):
        store.add_upload(
            domain="company", company_name="  ", title="", text="内容。",
            reason="r", operator="a", source_label="s", matched_canonical_id=None,
        )
    with pytest.raises(ManualRecallError, match="reason"):
        store.add_upload(
            domain="company", company_name="n", title="", text="内容。",
            reason=" ", operator="a", source_label="s", matched_canonical_id=None,
        )
    assert store.active_points() == ()


def test_add_upload_propagates_embedding_failure_without_persisting(
    tmp_path: Path,
) -> None:
    store = ManualRecallStore(tmp_path, _FakeEmbeddingAdapter(fail=True))
    with pytest.raises(RuntimeError, match="embedding service down"):
        store.add_upload(
            domain="company", company_name="n", title="", text="内容。",
            reason="r", operator="a", source_label="s", matched_canonical_id=None,
        )
    assert store.active_points() == ()
    assert not store.store_path.exists()


# -- persistence / fail-open load ----------------------------------------------


def test_store_reloads_points_across_instances(tmp_path: Path) -> None:
    first = _store(tmp_path)
    doc_id, _ = first.add_upload(
        domain="company", company_name="测试企业", title="", text="内容。",
        reason="r", operator="a", source_label="s", matched_canonical_id=None,
    )
    second = _store(tmp_path)
    points = second.active_points()
    assert len(points) == 1
    assert points[0].ref_id == doc_id
    assert points[0].display_name == "测试企业"


def test_store_load_skips_points_with_dimension_drift(tmp_path: Path) -> None:
    first = _store(tmp_path, dimension=8)
    first.add_upload(
        domain="company", company_name="测试企业", title="", text="内容。",
        reason="r", operator="a", source_label="s", matched_canonical_id=None,
    )
    reloaded = _store(tmp_path, dimension=16)
    assert reloaded.active_points() == ()


def test_store_load_is_fail_open_on_corrupt_file(tmp_path: Path) -> None:
    (tmp_path / "manual-recall.json").write_text("{broken json", encoding="utf-8")
    store = _store(tmp_path)
    assert store.active_points() == ()


def test_store_load_is_fail_open_on_schema_mismatch(tmp_path: Path) -> None:
    (tmp_path / "manual-recall.json").write_text(
        json.dumps({"schema_version": "other", "points": []}), encoding="utf-8"
    )
    store = _store(tmp_path)
    assert store.active_points() == ()


# -- tombstones -----------------------------------------------------------------


def test_tombstone_by_ref_reverts_all_chunks_and_persists(tmp_path: Path) -> None:
    store = _store(tmp_path)
    long_text = "\n\n".join(("甲" * 500, "乙" * 500, "丙" * 500))
    doc_id, count = store.add_upload(
        domain="company", company_name="测试企业", title="", text=long_text,
        reason="r", operator="a", source_label="s", matched_canonical_id=None,
    )
    assert count == 3
    assert store.tombstone_by_ref(doc_id) == 3
    assert store.active_points() == ()
    assert store.tombstone_by_ref(doc_id) == 0

    reloaded = _store(tmp_path)
    assert reloaded.active_points() == ()
    uploads = reloaded.list_uploads()
    assert uploads[0]["status"] == "reverted"
    assert uploads[0]["chunk_count"] == 0


def test_tombstone_point_flips_one_point(tmp_path: Path) -> None:
    store = _store(tmp_path)
    point_id = store.add_manual_record(
        record_id="added-1",
        domain="company",
        manual_object_id="company-manual-1",
        payload={"name": "手工企业"},
        operator="admin",
        reason="补充",
    )
    assert store.tombstone_point(point_id) is True
    assert store.tombstone_point(point_id) is False
    assert store.tombstone_point("manual-unknown") is False
    assert store.active_points() == ()


# -- manual records ---------------------------------------------------------------


def test_add_manual_record_embeds_serialized_payload(tmp_path: Path) -> None:
    store = _store(tmp_path)
    point_id = store.add_manual_record(
        record_id="added-1",
        domain="company",
        manual_object_id="company-manual-1",
        payload={"name": "手工企业", "profile_summary": "手工简介"},
        operator="admin",
        reason="登记新企业",
    )
    assert point_id == "manual-added-1"
    points = store.active_points()
    assert len(points) == 1
    point = points[0]
    assert point.kind == "manual_record"
    assert point.canonical_ref == "company-manual-1"
    assert point.ref_id == "added-1"
    embedded = json.loads(point.embedded_content)
    assert embedded == {"name": "手工企业", "profile_summary": "手工简介"}


def test_add_manual_record_rejects_unsupported_domain(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ManualRecallError, match="unsupported domain"):
        store.add_manual_record(
            record_id="added-1", domain="government",
            manual_object_id="x", payload={"name": "n"},
            operator="a", reason="r",
        )
    assert store.active_points() == ()


def test_list_uploads_reports_newest_first_with_status(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first_doc, _ = store.add_upload(
        domain="company", company_name="甲企业", title="甲介绍", text="一",
        reason="r", operator="a", source_label="a.txt", matched_canonical_id=None,
    )
    second_doc, _ = store.add_upload(
        domain="company", company_name="乙企业", title="", text="甲" * 500 + "\n\n" + "乙" * 500,
        reason="r", operator="a", source_label="b.txt", matched_canonical_id=None,
    )
    store.tombstone_by_ref(first_doc)

    uploads = store.list_uploads()
    assert [entry["doc_id"] for entry in uploads] == [second_doc, first_doc]
    assert uploads[0]["status"] == "active"
    assert uploads[0]["chunk_count"] == 2
    assert uploads[1]["status"] == "reverted"
    assert uploads[1]["company_name"] == "甲企业"
    assert uploads[1]["title"] == "甲介绍"


# -- embedding validation -----------------------------------------------------------


def test_embed_validates_cardinality_and_dimension(tmp_path: Path) -> None:
    class _ShortAdapter(_FakeEmbeddingAdapter):
        def embed_batch(self, texts):
            return tuple(tuple(1.0 for _ in range(self.dimension)) for _ in texts[:-1])

    store = ManualRecallStore(tmp_path / "a", _ShortAdapter())
    with pytest.raises(ManualRecallError, match="cardinality"):
        store.add_upload(
            domain="company", company_name="n", title="", text="内容。",
            reason="r", operator="a", source_label="s", matched_canonical_id=None,
        )

    class _WrongDimAdapter(_FakeEmbeddingAdapter):
        def embed_batch(self, texts):
            return tuple(tuple(1.0 for _ in range(4)) for _ in texts)

    store = ManualRecallStore(tmp_path / "b", _WrongDimAdapter(dimension=8))
    with pytest.raises(ManualRecallError, match="dimension"):
        store.add_upload(
            domain="company", company_name="n", title="", text="内容。",
            reason="r", operator="a", source_label="s", matched_canonical_id=None,
        )
