"""Correction overlay HTTP adapter for the Canonical V2 Admin surface.

Edits are stored in an independent corrections database and merged into
browse read paths at response time. The immutable serving-pack release
artifacts are never modified, and chat retrieval never reads this overlay —
corrections reach chat only after the next release build absorbs them.

Overlay semantics: when no corrections store is wired (app.state missing),
every read path is byte-identical to before. Overlay keys appear only on
objects that actually have active corrections, so uncorrected responses
keep their exact previous shape.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field

from backend.canonical_v2_deps import get_canonical_v2_admin_runtime
from backend.services.canonical_v2_admin import (
    CanonicalV2AdminRuntime,
    PublicDomain,
)
from backend.services.canonical_v2_corrections import (
    CorrectionsStore,
    CorrectionsStoreError,
    FieldCorrectionRecord,
)
from backend.services.canonical_v2_corrections import (
    FieldCorrectionDetail as _FieldCorrectionDetail,
)


router = APIRouter(prefix="/api/canonical-v2/admin")

_STORE_STATE_NAME = "canonical_v2_corrections_store"

# Provenance/structure fields are never editable; everything else that is a
# top-level display field of the object payload may be corrected.
_FORBIDDEN_FIELDS = frozenset(
    {
        "release_id",
        "canonical_identity_id",
        "id",
        "identity_decision_id",
        "inclusion_decision_id",
        "projection_version",
        "catalog_schema_version",
        "catalog_version",
        "catalog_content_sha256",
        "content_sha256",
        "as_of",
        "entity_type",
        "field_lineage",
        "evidence",
        "evidence_ids",
        "limitations",
        "quality_status",
        "run_id",
        "last_updated",
        "retrieval_traces",
        "domain",
        "industry",
        "origin",
        "corrections",
        "corrected_fields",
    }
)

_CORRECTION_ID_MAX = 200
_MANUAL_QUALITY_STATUS = "manual"


class FieldCorrectionBody(BaseModel):
    field_path: str = Field(min_length=1, max_length=200)
    new_value: Any = None
    reason: str = Field(min_length=1, max_length=500)


class AddedRecordBody(BaseModel):
    payload: dict[str, Any]
    reason: str = Field(min_length=1, max_length=500)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def corrections_store_from(request: Request) -> CorrectionsStore | None:
    store = getattr(request.app.state, _STORE_STATE_NAME, None)
    if store is None:
        return None
    if not isinstance(store, CorrectionsStore):
        raise HTTPException(
            status_code=503, detail="Canonical V2 corrections are unavailable"
        )
    return store


def _require_store(request: Request) -> CorrectionsStore:
    store = corrections_store_from(request)
    if store is None:
        raise HTTPException(
            status_code=503, detail="Canonical V2 corrections are not configured"
        )
    return store


def _operator(request: Request) -> str:
    value = request.headers.get("x-remote-user", "").strip()
    return value or "unknown"


def _store_error(exc: CorrectionsStoreError) -> HTTPException:
    return _unprocessable(str(exc))


def _correction_public(detail: _FieldCorrectionDetail) -> dict[str, Any]:
    return {
        "correction_id": detail.correction_id,
        "domain": detail.domain,
        "canonical_object_id": detail.canonical_object_id,
        "field_path": detail.field_path,
        "old_value": detail.old_value,
        "new_value": detail.new_value,
        "reason": detail.reason,
        "operator": detail.operator,
        "created_at": detail.created_at,
        "status": detail.status,
    }


def apply_detail_overlay(
    store: CorrectionsStore | None, *, domain: str, detail: dict[str, Any]
) -> dict[str, Any]:
    """Merge active corrections into one detail payload (shape unchanged
    when there is no store or no active correction for the object)."""

    if store is None:
        return detail
    canonical_id = detail.get("canonical_identity_id")
    if not isinstance(canonical_id, str) or not canonical_id:
        return detail
    active = store.active_corrections(domain=domain, canonical_object_id=canonical_id)
    if not active:
        return detail
    merged = dict(detail)
    for correction in active:
        merged[correction.field_path] = correction.new_value
    merged["corrected_fields"] = sorted(c.field_path for c in active)
    merged["corrections"] = [_correction_public(c) for c in active]
    return merged


def apply_list_overlay(
    store: CorrectionsStore | None,
    *,
    domain: str,
    result: dict[str, Any],
    unfiltered_first_page: bool,
) -> dict[str, Any]:
    """Merge corrections into list items and prepend manual records.

    Manual records join only on the unfiltered first page (q/filters empty,
    offset 0); filtering manual rows against release-scoped filter fields
    would be dishonest since they have no projections yet.
    """

    if store is None:
        return result
    items = result.get("items")
    if not isinstance(items, list):
        return result
    merged_items = [
        apply_detail_overlay(store, domain=domain, detail=item)
        for item in items
        if isinstance(item, dict)
    ]
    manual = store.list_added_records(domain=domain, status="active")
    if unfiltered_first_page and manual:
        manual_items = [manual_detail_item(row) for row in manual]
        merged = dict(result)
        merged["items"] = [*manual_items, *merged_items]
        if isinstance(result.get("total"), int):
            merged["total"] = result["total"] + len(manual_items)
        return merged
    if merged_items != items:
        merged = dict(result)
        merged["items"] = merged_items
        return merged
    return result


def manual_detail_item(row: Any) -> dict[str, Any]:
    return {
        **row.payload,
        "canonical_identity_id": row.manual_object_id,
        "id": row.manual_object_id,
        "entity_type": row.domain,
        "domain": row.domain,
        "origin": "manual",
        "quality_status": _MANUAL_QUALITY_STATUS,
        "added_record_id": row.record_id,
        "operator": row.operator,
        "created_at": row.created_at,
    }


def apply_export_overlay(
    store: CorrectionsStore | None, *, domain: str, lines: tuple[str, ...]
) -> tuple[str, ...]:
    """Rewrite exported JSONL lines with corrected field values."""

    if store is None:
        return lines
    rewritten: list[str] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            rewritten.append(line)
            continue
        if not isinstance(payload, dict):
            rewritten.append(line)
            continue
        merged = apply_detail_overlay(store, domain=domain, detail=payload)
        rewritten.append(json.dumps(merged, ensure_ascii=False))
    return tuple(rewritten)


# --- write endpoints -------------------------------------------------------


@router.post("/domains/{domain}/{canonical_id}/corrections", status_code=201)
def create_field_correction(
    request: Request,
    domain: PublicDomain,
    canonical_id: Annotated[str, Path(min_length=1, max_length=200)],
    body: FieldCorrectionBody,
    runtime: CanonicalV2AdminRuntime = Depends(get_canonical_v2_admin_runtime),
) -> object:
    store = _require_store(request)
    field_path = body.field_path.strip()
    if field_path in _FORBIDDEN_FIELDS or "." in field_path:
        raise _unprocessable("field_path is not editable for this object")
    detail = runtime.detail(domain=domain, canonical_id=canonical_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Canonical V2 object not found")
    if field_path not in detail:
        raise _unprocessable("field_path does not exist on this object")
    old_value = detail[field_path]
    if old_value == body.new_value:
        raise _unprocessable("new_value must differ from the current value")
    try:
        correction_id = store.record_correction(
            FieldCorrectionRecord(
                domain=domain,
                canonical_object_id=canonical_id,
                field_path=field_path,
                old_value=old_value,
                new_value=body.new_value,
                reason=body.reason,
                operator=_operator(request),
                created_at=runtime.as_of,
            )
        )
    except CorrectionsStoreError as exc:
        raise _store_error(exc) from exc
    merged = apply_detail_overlay(store, domain=domain, detail=detail)
    return {"correction_id": correction_id, "detail": merged}


@router.post("/corrections/{correction_id}/revert")
def revert_field_correction(
    request: Request,
    correction_id: Annotated[str, Path(min_length=1, max_length=_CORRECTION_ID_MAX)],
) -> object:
    store = _require_store(request)
    if not store.revert_correction(correction_id):
        raise HTTPException(status_code=404, detail="Canonical V2 correction not found")
    return {"correction_id": correction_id, "status": "reverted"}


@router.post("/domains/{domain}/records", status_code=201)
def create_added_record(
    request: Request,
    domain: PublicDomain,
    body: AddedRecordBody,
    runtime: CanonicalV2AdminRuntime = Depends(get_canonical_v2_admin_runtime),
) -> object:
    store = _require_store(request)
    payload = dict(body.payload)
    name = payload.get("name") or payload.get("title")
    if not isinstance(name, str) or not name.strip():
        raise _unprocessable("added record payload requires a non-empty name or title")
    for forbidden in _FORBIDDEN_FIELDS:
        payload.pop(forbidden, None)
    if not payload:
        raise _unprocessable("added record payload must keep at least one field")
    try:
        detail = store.add_record(
            domain=domain,
            payload=payload,
            reason=body.reason,
            operator=_operator(request),
            created_at=runtime.as_of,
        )
    except CorrectionsStoreError as exc:
        raise _store_error(exc) from exc
    return {
        "record_id": detail.record_id,
        "manual_object_id": detail.manual_object_id,
        "detail": manual_detail_item(detail),
    }


@router.post("/records/{record_id}/revert")
def revert_added_record(
    request: Request,
    record_id: Annotated[str, Path(min_length=1, max_length=_CORRECTION_ID_MAX)],
) -> object:
    store = _require_store(request)
    if not store.revert_added_record(record_id):
        raise HTTPException(status_code=404, detail="Canonical V2 added record not found")
    return {"record_id": record_id, "status": "reverted"}


# --- read endpoints --------------------------------------------------------


@router.get("/corrections")
def list_corrections(
    request: Request,
    domain: PublicDomain | None = None,
    canonical_id: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    status: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
) -> object:
    store = _require_store(request)
    try:
        rows = store.list_corrections(
            domain=domain, canonical_object_id=canonical_id, status=status
        )
    except CorrectionsStoreError as exc:
        raise _store_error(exc) from exc
    return {"items": [_correction_public(row) for row in rows], "total": len(rows)}


@router.get("/corrections/export")
def export_corrections(request: Request) -> Response:
    """All active corrections + added records as JSONL build input."""

    store = _require_store(request)
    lines: list[str] = []
    for row in store.list_corrections(status="active"):
        lines.append(
            json.dumps({"kind": "field_correction", **_correction_public(row)}, ensure_ascii=False)
        )
    for row in store.list_added_records(status="active"):
        lines.append(
            json.dumps(
                {
                    "kind": "added_record",
                    "record_id": row.record_id,
                    "domain": row.domain,
                    "manual_object_id": row.manual_object_id,
                    "payload": row.payload,
                    "reason": row.reason,
                    "operator": row.operator,
                    "created_at": row.created_at,
                },
                ensure_ascii=False,
            )
        )
    body = "" if not lines else "\n".join(lines) + "\n"
    return Response(content=body, media_type="application/x-ndjson")


__all__ = [
    "apply_detail_overlay",
    "apply_export_overlay",
    "apply_list_overlay",
    "corrections_store_from",
    "manual_detail_item",
    "router",
]
