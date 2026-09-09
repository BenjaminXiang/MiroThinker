"""Company document upload API + corrections edit hooks for manual recall.

Preview extracts/chunks without persisting; confirm embeds into the
sidecar (502 + nothing persisted when the embedding backend fails);
revert tombstones the document's chunks. Corrections record creates are
embedded into the same sidecar with a compensating revert on embedding
failure, and record reverts tombstone their points. Without a mounted
sidecar the corrections behavior is byte-identical to before.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from fastapi.testclient import TestClient
import pytest

from backend.canonical_v2_deps import get_canonical_v2_admin_runtime
from backend.main import app
from backend.services.canonical_v2_corrections import CorrectionsStore
from backend.services.canonical_v2_manual_recall import ManualRecallStore


_CORRECTIONS_STATE = "canonical_v2_corrections_store"
_RECALL_STATE = "canonical_v2_manual_recall_store"
_AS_OF = datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC)


class _FakeEmbeddingAdapter:
    def __init__(self, *, dimension: int = 8, fail: bool = False) -> None:
        self.dimension = dimension
        self.fail = fail
        self.calls = 0

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("embedding backend unavailable")
        return tuple(
            tuple(
                byte / 255.0
                for byte in hashlib.sha256(text.encode("utf-8")).digest()[
                    : self.dimension
                ]
            )
            for text in texts
        )


class _FakeRuntime:
    @property
    def as_of(self) -> datetime:
        return _AS_OF

    def detail(self, *, domain: str, canonical_id: str) -> dict[str, Any] | None:
        return None

    def list_domain(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "release_id": "rel-test-1",
            "domain": "company",
            "as_of": _AS_OF.isoformat(),
            "items": [],
            "total": 0,
            "limit": 25,
            "offset": 0,
            "sort_keys": [],
            "filter_receipt": None,
            "retrieval_traces": [],
            "limitations": [],
        }

    def export(self, *, domain: str, ids: list[str]) -> tuple[str, ...]:
        return tuple(json.dumps({}) for _ in ids)


@pytest.fixture()
def recall_adapter() -> _FakeEmbeddingAdapter:
    return _FakeEmbeddingAdapter()


@pytest.fixture()
def recall_store(
    tmp_path: Path,
    recall_adapter: _FakeEmbeddingAdapter,
) -> Iterator[ManualRecallStore]:
    instance = ManualRecallStore(tmp_path / "manual-recall", recall_adapter)
    had_prior = hasattr(app.state, _RECALL_STATE)
    prior = getattr(app.state, _RECALL_STATE, None)
    setattr(app.state, _RECALL_STATE, instance)
    try:
        yield instance
    finally:
        if had_prior:
            setattr(app.state, _RECALL_STATE, prior)
        elif hasattr(app.state, _RECALL_STATE):
            delattr(app.state, _RECALL_STATE)


@pytest.fixture()
def corrections_store(tmp_path: Path) -> Iterator[CorrectionsStore]:
    instance = CorrectionsStore(tmp_path / "corrections.sqlite3")
    had_prior = hasattr(app.state, _CORRECTIONS_STATE)
    prior = getattr(app.state, _CORRECTIONS_STATE, None)
    setattr(app.state, _CORRECTIONS_STATE, instance)
    app.dependency_overrides[get_canonical_v2_admin_runtime] = lambda: _FakeRuntime()
    try:
        yield instance
    finally:
        app.dependency_overrides.pop(get_canonical_v2_admin_runtime, None)
        if had_prior:
            setattr(app.state, _CORRECTIONS_STATE, prior)
        elif hasattr(app.state, _CORRECTIONS_STATE):
            delattr(app.state, _CORRECTIONS_STATE)
        instance.close()


@pytest.fixture()
def client(recall_store: ManualRecallStore) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("utf-8")
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(stream)).encode("ascii") + b">>\nstream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    header = b"%PDF-1.4\n"
    body = b""
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(header) + len(body))
        body += f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref_pos = len(header) + len(body)
    xref = b"xref\n0 6\n0000000000 65535 f \n" + b"".join(
        f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets
    )
    trailer = (
        b"trailer\n<</Size 6/Root 1 0 R>>\nstartxref\n"
        + str(xref_pos).encode("ascii")
        + b"\n%%EOF\n"
    )
    return header + body + xref + trailer


# --- preview ----------------------------------------------------------------


def test_preview_pdf_extracts_and_chunks(client: TestClient) -> None:
    response = client.post(
        "/api/canonical-v2/admin/company-documents/preview",
        files={"file": ("robotics.pdf", _minimal_pdf("Shenzhen Robotics"), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["media_kind"] == "pdf"
    assert "Shenzhen Robotics" in payload["text"]
    assert payload["chunk_count"] >= 1
    assert payload["truncated"] is False


def test_preview_text_file(client: TestClient) -> None:
    response = client.post(
        "/api/canonical-v2/admin/company-documents/preview",
        files={"file": ("notes.txt", "公司主营业务：协作机器人。".encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["media_kind"] == "text"
    assert "协作机器人" in payload["text"]


def test_preview_rejects_unsupported_extension(client: TestClient) -> None:
    response = client.post(
        "/api/canonical-v2/admin/company-documents/preview",
        files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert response.status_code == 422


def test_preview_rejects_extension_content_mismatch(client: TestClient) -> None:
    response = client.post(
        "/api/canonical-v2/admin/company-documents/preview",
        files={"file": ("fake.pdf", b"plain text, not a pdf", "application/pdf")},
    )
    assert response.status_code == 422


def test_preview_rejects_oversize_upload(client: TestClient) -> None:
    oversize = b"x" * (10 * 1024 * 1024 + 1)
    response = client.post(
        "/api/canonical-v2/admin/company-documents/preview",
        files={"file": ("big.txt", oversize, "text/plain")},
    )
    assert response.status_code == 413


def test_preview_rejects_empty_extraction(client: TestClient) -> None:
    response = client.post(
        "/api/canonical-v2/admin/company-documents/preview",
        files={"file": ("blank.txt", b"   \n  ", "text/plain")},
    )
    assert response.status_code == 422


# --- confirm / list / revert ------------------------------------------------


def _confirm_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "company_name": "深圳机器人公司",
        "title": "融资新闻稿",
        "text": "深圳机器人公司主营协作机器人，2026 年完成 B 轮融资。",
        "reason": "补充企业最新公开信息",
    }
    body.update(overrides)
    return body


def test_confirm_embeds_document_and_list_shows_it(
    client: TestClient,
    recall_store: ManualRecallStore,
) -> None:
    response = client.post(
        "/api/canonical-v2/admin/company-documents",
        json=_confirm_body(),
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["doc_id"].startswith("doc-")
    assert payload["chunk_count"] >= 1

    points = recall_store.active_points()
    assert len(points) == payload["chunk_count"]
    assert all(point.ref_id == payload["doc_id"] for point in points)
    assert all(point.domain == "company" for point in points)
    assert points[0].canonical_ref == f"manual-upload:{payload['doc_id']}"

    listing = client.get("/api/canonical-v2/admin/company-documents")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["doc_id"] == payload["doc_id"]
    assert items[0]["company_name"] == "深圳机器人公司"
    assert items[0]["status"] == "active"


def test_confirm_with_matched_canonical_id(
    client: TestClient,
    recall_store: ManualRecallStore,
) -> None:
    response = client.post(
        "/api/canonical-v2/admin/company-documents",
        json=_confirm_body(matched_canonical_id="company-c-existing"),
    )
    assert response.status_code == 201, response.text
    points = recall_store.active_points()
    assert all(point.canonical_ref == "company-c-existing" for point in points)


def test_confirm_embedding_failure_persists_nothing(
    tmp_path: Path,
    recall_store: ManualRecallStore,
) -> None:
    failing = _FakeEmbeddingAdapter(fail=True)
    broken_store = ManualRecallStore(tmp_path / "broken", failing)
    setattr(app.state, _RECALL_STATE, broken_store)
    try:
        failing_client = TestClient(app, raise_server_exceptions=False)
        response = failing_client.post(
            "/api/canonical-v2/admin/company-documents",
            json=_confirm_body(),
        )
    finally:
        setattr(app.state, _RECALL_STATE, recall_store)
    assert response.status_code == 502, response.text
    assert broken_store.active_points() == ()
    assert not broken_store.store_path.exists()


def test_revert_tombstones_document_chunks(
    client: TestClient,
    recall_store: ManualRecallStore,
) -> None:
    created = client.post(
        "/api/canonical-v2/admin/company-documents",
        json=_confirm_body(),
    ).json()
    response = client.post(
        f"/api/canonical-v2/admin/company-documents/{created['doc_id']}/revert"
    )
    assert response.status_code == 200, response.text
    assert response.json()["reverted_points"] == created["chunk_count"]
    assert recall_store.active_points() == ()

    again = client.post(
        f"/api/canonical-v2/admin/company-documents/{created['doc_id']}/revert"
    )
    assert again.status_code == 404


def test_mutations_require_store() -> None:
    bare = TestClient(app, raise_server_exceptions=False)
    assert (
        bare.post(
            "/api/canonical-v2/admin/company-documents",
            json=_confirm_body(),
        ).status_code
        == 503
    )
    assert bare.get("/api/canonical-v2/admin/company-documents").status_code == 503
    assert (
        bare.post("/api/canonical-v2/admin/company-documents/doc-x/revert").status_code
        == 503
    )


# --- corrections record hooks ----------------------------------------------


def test_record_create_embeds_and_revert_tombstones(
    recall_store: ManualRecallStore,
    corrections_store: CorrectionsStore,
) -> None:
    client = TestClient(app, raise_server_exceptions=False)
    created = client.post(
        "/api/canonical-v2/admin/domains/company/records",
        json={
            "payload": {"name": "手工企业甲", "profile_summary": "人工补充的企业。"},
            "reason": "运营手工新增",
        },
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["record_id"]
    manual_object_id = created.json()["manual_object_id"]

    points = recall_store.active_points()
    assert len(points) == 1
    point = points[0]
    assert point.ref_id == record_id
    assert point.point_id == f"manual-{record_id}"
    assert point.canonical_ref == manual_object_id
    assert point.display_name == "手工企业甲"

    reverted = client.post(f"/api/canonical-v2/admin/records/{record_id}/revert")
    assert reverted.status_code == 200
    assert recall_store.active_points() == ()


def test_record_create_embedding_failure_compensates(
    tmp_path: Path,
    recall_store: ManualRecallStore,
    corrections_store: CorrectionsStore,
) -> None:
    failing_store = ManualRecallStore(
        tmp_path / "failing", _FakeEmbeddingAdapter(fail=True)
    )
    setattr(app.state, _RECALL_STATE, failing_store)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        created = client.post(
            "/api/canonical-v2/admin/domains/company/records",
            json={
                "payload": {"name": "手工企业乙"},
                "reason": "运营手工新增",
            },
        )
    finally:
        setattr(app.state, _RECALL_STATE, recall_store)
    assert created.status_code == 502, created.text
    assert failing_store.active_points() == ()
    active_records = [
        detail
        for detail in corrections_store.list_added_records(domain="company")
        if detail.status == "active"
    ]
    assert active_records == []


def test_record_create_without_sidecar_keeps_prior_behavior(
    corrections_store: CorrectionsStore,
) -> None:
    client = TestClient(app, raise_server_exceptions=False)
    created = client.post(
        "/api/canonical-v2/admin/domains/company/records",
        json={
            "payload": {"name": "手工企业丙"},
            "reason": "运营手工新增",
        },
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["record_id"]
    reverted = client.post(f"/api/canonical-v2/admin/records/{record_id}/revert")
    assert reverted.status_code == 200
