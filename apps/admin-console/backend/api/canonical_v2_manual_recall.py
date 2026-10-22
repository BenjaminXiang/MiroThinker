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

from fastapi import APIRouter, Form, HTTPException, Path, Request, UploadFile
from pydantic import BaseModel, Field

from backend.services.admin_session import current_operator
from backend.services.canonical_v2_manual_recall import (
    ManualRecallError,
    ManualRecallStore,
    chunk_document_text,
)
from backend.services.excel_ingest import ExcelIngestError, ingest_analysis
from backend.services.excel_structure import analyze_workbook, iter_structured_rows

router = APIRouter(prefix="/api/canonical-v2/admin")

_STORE_STATE_NAME = "canonical_v2_manual_recall_store"

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_MAX_EXTRACTED_CHARS = 24_000
_DOC_ID_MAX = 200

_SUFFIXES = frozenset({".pdf", ".docx", ".txt", ".md", ".xlsx"})
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


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _unprocessable("text file must be UTF-8 decodable") from exc


def _xlsx_text(data: bytes) -> str:
    """Flatten the active sheet into one ``header: value`` block per row."""

    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        sheet = workbook.active
        headers: list[str] = []
        blocks: list[str] = []
        used = 0
        for index, row in enumerate(sheet.iter_rows(values_only=True)):
            if index == 0:
                headers = [
                    str(cell).strip()
                    if cell is not None and str(cell).strip()
                    else f"列{i + 1}"
                    for i, cell in enumerate(row)
                ]
                continue
            values = []
            for i, cell in enumerate(row):
                if cell is None or str(cell).strip() == "":
                    continue
                header = headers[i] if i < len(headers) else f"列{i + 1}"
                values.append(f"{header}: {cell}")
            if not values:
                continue
            block = "；".join(values)
            if used + len(block) + 2 > _MAX_EXTRACTED_CHARS:
                break
            blocks.append(block)
            used += len(block) + 2
        return "\n\n".join(blocks)
    finally:
        workbook.close()


def _extract_text(filename: str, data: bytes) -> tuple[str, str]:
    """Return (media_kind, extracted text); raise 422 on unsupported input."""

    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix not in _SUFFIXES:
        raise _unprocessable(
            "unsupported file type; allowed: .pdf, .docx, .txt, .md, .xlsx"
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
    if suffix == ".xlsx":
        if not data.startswith(_ZIP_MAGIC):
            raise _unprocessable("file content is not an XLSX workbook")
        try:
            return "xlsx", _xlsx_text(data)
        except Exception as exc:  # noqa: BLE001 - parser boundary -> 422
            raise _unprocessable(f"XLSX text extraction failed: {exc}") from exc
    if suffix == ".txt":
        return "text", _decode_text(data)
    if data.startswith((_PDF_MAGIC, _ZIP_MAGIC)):
        raise _unprocessable("file content does not match its .md extension")
    return "text", _decode_text(data)


def _analysis_payload(analysis: Any) -> dict[str, Any]:
    best = analysis.best
    return {
        "domain": best.domain,
        "domain_label": best.domain_label,
        "confidence": best.confidence,
        "sheet_name": best.sheet_name,
        "header_row": best.header_row,
        "headers": list(best.headers),
        "mapping": [
            {"source": item.source, "field": item.field} for item in best.mapping
        ],
        "row_count": best.row_count,
        "sample_rows": list(best.sample_rows),
        "warnings": list(best.warnings),
        "alternatives": [
            {
                "domain": item.domain,
                "domain_label": item.domain_label,
                "confidence": item.confidence,
                "sheet_name": item.sheet_name,
                "row_count": item.row_count,
                "mapping": [
                    {"source": column.source, "field": column.field}
                    for column in item.mapping
                ],
            }
            for item in analysis.alternatives
        ],
        "sheets": list(analysis.sheets),
    }


@router.post("/company-documents/preview")
async def preview_company_document(file: UploadFile) -> dict[str, Any]:
    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="upload exceeds 10 MiB")
    media_kind, text = _extract_text(file.filename or "", data)
    analysis_payload = None
    analysis_error = None
    if media_kind == "xlsx":
        try:
            analysis_payload = _analysis_payload(analyze_workbook(data))
        except Exception as exc:  # noqa: BLE001 - structure detection is advisory
            analysis_error = f"{type(exc).__name__}: {exc}"[:300]
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
        "row_count": (
            len([block for block in text.split("\n\n") if block.strip()])
            if media_kind == "xlsx"
            else None
        ),
        "analysis": analysis_payload,
        "analysis_error": analysis_error,
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
            operator=current_operator(request),
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


@router.post("/company-documents/structured", status_code=201)
async def ingest_structured_document(
    request: Request,
    file: UploadFile,
    title: str = Form(default=""),
    reason: str = Form(...),
    domain: str = Form(default=""),
    company_name: str = Form(default=""),
) -> dict[str, Any]:
    """Analyse the workbook, map columns, and write the detected domain rows."""

    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="upload exceeds 10 MiB")
    filename = file.filename or "upload.xlsx"
    if not filename.lower().endswith(".xlsx"):
        raise _unprocessable("structured import currently supports .xlsx")
    if not reason.strip():
        raise _unprocessable("reason must not be empty")
    try:
        analysis = analyze_workbook(data)
    except Exception as exc:  # noqa: BLE001 - parser boundary
        raise _unprocessable(f"workbook structure detection failed: {exc}") from exc
    if domain.strip() and domain.strip() != analysis.best.domain:
        raise _unprocessable(
            f"declared domain {domain!r} does not match detected {analysis.best.domain!r}"
        )
    try:
        ingest = ingest_analysis(
            analysis.best,
            iter_structured_rows(analysis.best, data),
            operator=current_operator(request),
        )
    except ExcelIngestError as exc:
        raise _unprocessable(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - DB boundary
        raise HTTPException(
            status_code=502, detail=f"structured ingest failed: {type(exc).__name__}"
        ) from exc

    recall: dict[str, Any] = {"status": "skipped"}
    store = manual_recall_store_from(request)
    if store is not None:
        label = (company_name or title or filename).strip()[:200]
        text = _xlsx_text(data)
        try:
            doc_id, chunk_count = store.add_upload(
                domain=analysis.best.domain,
                company_name=label,
                title=title,
                text=text,
                reason=reason,
                operator=current_operator(request),
                source_label=filename,
                matched_canonical_id=None,
            )
            recall = {"status": "active", "doc_id": doc_id, "chunk_count": chunk_count}
        except Exception as exc:  # noqa: BLE001 - recall sidecar is optional
            recall = {"status": "failed", "error": type(exc).__name__}
    return {
        "analysis": _analysis_payload(analysis),
        "ingest": ingest,
        "recall": recall,
    }


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
