from __future__ import annotations

import hashlib

from src.data_agents.paper.raw_pdf_store import persist_raw_pdf_bytes


def test_persist_raw_pdf_bytes_writes_sha_addressed_blob(tmp_path):
    pdf_bytes = b"%PDF-1.4 raw content"
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    blob_ref = persist_raw_pdf_bytes(pdf_bytes, sha256, storage_dir=tmp_path)

    assert sha256 in blob_ref
    stored = list(tmp_path.rglob(f"{sha256}.pdf"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == pdf_bytes


def test_persist_raw_pdf_bytes_dedupes_existing_blob(tmp_path):
    pdf_bytes = b"%PDF-1.4 same content"
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    first_ref = persist_raw_pdf_bytes(pdf_bytes, sha256, storage_dir=tmp_path)
    first_path = next(tmp_path.rglob(f"{sha256}.pdf"))
    first_mtime = first_path.stat().st_mtime_ns
    second_ref = persist_raw_pdf_bytes(pdf_bytes, sha256, storage_dir=tmp_path)

    assert second_ref == first_ref
    assert list(tmp_path.rglob(f"{sha256}.pdf")) == [first_path]
    assert first_path.stat().st_mtime_ns == first_mtime
