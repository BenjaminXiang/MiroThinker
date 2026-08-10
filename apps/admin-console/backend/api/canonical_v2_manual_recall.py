"""Company document upload HTTP adapter for the manual recall sidecar.

Two-step flow: ``preview`` extracts and chunks the document without
persisting anything; ``confirm`` embeds the (operator-edited) text into
the sidecar store so chat recalls it immediately. ``revert`` tombstones
every chunk of one document. When no sidecar store is wired
(app.state missing), preview still works and the mutating endpoints
answer 503.
"""

from __future__ import annotations

import io
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Request, UploadFile
from pydantic import BaseModel, Field

from backend.services.canonical_v2_manual_recall import (
    ManualRecallError,
    ManualRecallStore,
    chunk_document_text,
)

router = APIRouter(prefix="/api/canonical-v2/admin")

_STORE_STATE_NAME = "canonical_v2_manual_recall_store"

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_MAX_EXTRACTED_CHARS = 24_000
_DOC_ID_MAX = 200

_SUFFIXES = frozenset({".pdf", ".docx", ".txt", ".md"})
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"


class ConfirmUploadBody(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    title: str = Field(default="", max_length=200)
    text: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)
    matched_canonical_id: str | None = Field(default=None, max_length=200)
    source_label: str = Field(default="admin-upload", max_length=200)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def manual_recall_store_from(request: Request) -> ManualRecallStore | None:
    store = getattr(request.app.state, _STORE_STATE_NAME, None)
    if isinstance(store, ManualRecallStore):
        return store
    return None


def _require_store(request: Request) -> ManualRecallStore:
    store = manual_recall_store_from(request)
    if store is None:
        raise HTTPException(
            status_code=503, detail="Canonical V2 manual recall is not configured"
        )
    return store


def _operator(request: Request) -> str:
    value = request.headers.get("x-remote-user", "").strip()
    return value or "unknown"


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _unprocessable("text file must be UTF-8 decodable") from exc


def _extract_text(filename: str, data: bytes) -> tuple[str, str]:
    """Return (media_kind, extracted text); raise 422 on unsupported input."""

    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix not in _SUFFIXES:
        raise _unprocessable(
            "unsupported file type; allowed: .pdf, .docx, .txt, .md"
        )
    if suffix == ".pdf":
        if not data.startswith(_PDF_MAGIC):
            raise _unprocessable("file content is not a PDF document")
        try:
            from pdfminer.high_level import extract_text as pdf_extract_text

            return "pdf", pdf_extract_text(io.BytesIO(data)) or ""
        except Exception as exc:  # noqa: BLE001 - parser boundary -> 422
            raise _unprocessable(f"PDF text extraction failed: {exc}") from exc
    if suffix == ".docx":
        if not data.startswith(_ZIP_MAGIC):
            raise _unprocessable("file content is not a DOCX document")
        try:
            import mammoth

            with io.BytesIO(data) as stream:
                return "docx", mammoth.extract_raw_text(stream).value or ""
        except Exception as exc:  # noqa: BLE001 - parser boundary -> 422
            raise _unprocessable(f"DOCX text extraction failed: {exc}") from exc
    if suffix == ".txt":
        return "text", _decode_text(data)
    if data.startswith((_PDF_MAGIC, _ZIP_MAGIC)):
        raise _unprocessable("file content does not match its .md extension")
    return "text", _decode_text(data)


@router.post("/company-documents/preview")
async def preview_company_document(file: UploadFile) -> dict[str, Any]:
    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="upload exceeds 10 MiB")
    media_kind, text = _extract_text(file.filename or "", data)
    truncated = len(text) > _MAX_EXTRACTED_CHARS
    if truncated:
        text = text[:_MAX_EXTRACTED_CHARS]
    if not text.strip():
        raise _unprocessable("no extractable text content")
    return {
        "filename": file.filename or "",
        "media_kind": media_kind,
        "extracted_chars": len(text),
        "truncated": truncated,
        "chunk_count": len(chunk_document_text(text)),
        "text": text,
    }


@router.post("/company-documents", status_code=201)
def confirm_company_document(
    request: Request,
    body: ConfirmUploadBody,
) -> dict[str, Any]:
    store = _require_store(request)
    if not body.text.strip():
        raise _unprocessable("text must not be empty")
    try:
        doc_id, chunk_count = store.add_upload(
            domain="company",
            company_name=body.company_name,
            title=body.title,
            text=body.text,
            reason=body.reason,
            operator=_operator(request),
            source_label=body.source_label,
            matched_canonical_id=body.matched_canonical_id or None,
        )
    except ManualRecallError as exc:
        raise _unprocessable(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - embedding backend boundary
        raise HTTPException(
            status_code=502,
            detail="embedding backend failed; document was not saved",
        ) from exc
    return {"doc_id": doc_id, "chunk_count": chunk_count, "status": "active"}


@router.get("/company-documents")
def list_company_documents(request: Request) -> dict[str, Any]:
    store = _require_store(request)
    return {"items": list(store.list_uploads())}


@router.post("/company-documents/{doc_id}/revert")
def revert_company_document(
    request: Request,
    doc_id: Annotated[str, Path(min_length=1, max_length=_DOC_ID_MAX)],
) -> dict[str, Any]:
    store = _require_store(request)
    reverted = store.tombstone_by_ref(doc_id)
    if reverted == 0:
        raise HTTPException(
            status_code=404, detail="Canonical V2 company document not found"
        )
    return {"doc_id": doc_id, "reverted_points": reverted, "status": "reverted"}


__all__ = ["manual_recall_store_from", "router"]
