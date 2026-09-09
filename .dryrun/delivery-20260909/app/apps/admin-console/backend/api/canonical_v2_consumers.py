"""Bounded read-only HTTP adapter for the Canonical V2 Admin runtime."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from backend.api.canonical_v2_corrections import (
    apply_detail_overlay,
    apply_export_overlay,
    apply_list_overlay,
    corrections_store_from,
    manual_detail_item,
)
from backend.canonical_v2_deps import get_canonical_v2_admin_runtime
from backend.services.canonical_v2_admin import (
    CanonicalV2AdminRuntime,
    CanonicalV2ConsumerInputError,
    CanonicalV2ConsumerIntegrityError,
    PublicDomain,
)


router = APIRouter(prefix="/api/canonical-v2/admin")

_FILTERS = {
    "company": frozenset({"industry", "geography", "quality_status"}),
    "paper": frozenset({"venue", "year", "quality_status"}),
    "patent": frozenset({"patent_type", "publication_date", "quality_status"}),
    "professor": frozenset({"institution", "department", "quality_status"}),
}
_SORTS = {
    "company": frozenset({"name", "founded_at", "last_updated"}),
    "paper": frozenset({"title", "year", "citation_count", "last_updated"}),
    "patent": frozenset({"title", "publication_date", "filing_date", "last_updated"}),
    "professor": frozenset({"name", "h_index", "citation_count", "last_updated"}),
}
_DEFAULT_SORT = {
    "company": "name",
    "paper": "title",
    "patent": "title",
    "professor": "name",
}
_RELATIONS = {
    "company": "company_has_patent",
    "patent": "company_has_patent",
    "professor": "professor_authored_paper",
    "paper": "professor_authored_paper",
}


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _bounded_text(value: str, *, label: str) -> str:
    if not value or len(value) > 200:
        raise _unprocessable(f"{label} must contain 1..200 characters")
    return value


def _validated_pairs(
    *,
    domain: PublicDomain,
    fields: list[str] | None,
    values: list[str] | None,
) -> tuple[tuple[str, str], ...]:
    raw_fields = fields or []
    raw_values = values or []
    if len(raw_fields) != len(raw_values):
        raise _unprocessable("filter fields and values must form complete pairs")
    if len(raw_fields) > 4:
        raise _unprocessable("at most four filter pairs are allowed")
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    seen_fields: set[str] = set()
    for field, raw_value in zip(raw_fields, raw_values, strict=True):
        if field not in _FILTERS[domain]:
            raise _unprocessable("filter field is not allowed for this domain")
        value = _bounded_text(raw_value, label="filter value")
        pair = (field, value)
        if pair in seen or field in seen_fields:
            raise _unprocessable("filter pairs must be unique")
        seen.add(pair)
        seen_fields.add(field)
        if domain == "paper" and field == "year":
            if len(value) != 4 or not value.isdigit() or not 1000 <= int(value) <= 9999:
                raise _unprocessable("paper year must be an exact four-digit year")
        if domain == "patent" and field == "publication_date":
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise _unprocessable(
                    "publication_date must be a valid YYYY-MM-DD date"
                ) from exc
            if parsed.isoformat() != value:
                raise _unprocessable(
                    "publication_date must be an exact zero-padded date"
                )
        pairs.append(pair)
    return tuple(pairs)


def _runtime_call(call: Callable[[], object]) -> object:
    try:
        return call()
    except CanonicalV2ConsumerInputError as exc:
        raise _unprocessable("canonical_v2_consumer_input_error") from exc
    except CanonicalV2ConsumerIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="canonical_v2_consumer_integrity_error",
        ) from exc


@router.get("/status")
def get_status(
    runtime: CanonicalV2AdminRuntime = Depends(get_canonical_v2_admin_runtime),
) -> object:
    return _runtime_call(runtime.status)


@router.get("/domains/{domain}/facets/{field}")
def get_domain_facets(
    domain: PublicDomain,
    field: Annotated[str, Path(min_length=1, max_length=200)],
    runtime: CanonicalV2AdminRuntime = Depends(get_canonical_v2_admin_runtime),
) -> object:
    if field not in _FILTERS[domain]:
        raise _unprocessable("facet field is not allowed for this domain")
    return _runtime_call(lambda: runtime.facets(domain=domain, field=field))


@router.get("/domains/{domain}/export")
def export_domain(
    request: Request,
    domain: PublicDomain,
    ids: Annotated[list[str] | None, Query(alias="id")] = None,
    format: Literal["jsonl"] | None = None,
    runtime: CanonicalV2AdminRuntime = Depends(get_canonical_v2_admin_runtime),
) -> Response:
    values = ids or []
    if format != "jsonl":
        raise _unprocessable("export format must be jsonl")
    if not 1 <= len(values) <= 500:
        raise _unprocessable("export requires 1..500 IDs")
    if len(values) != len(set(values)):
        raise _unprocessable("export IDs must be unique")
    for value in values:
        _bounded_text(value, label="canonical ID")
    lines = _runtime_call(lambda: runtime.export(domain=domain, ids=values))
    assert isinstance(lines, tuple)
    lines = apply_export_overlay(
        corrections_store_from(request), domain=domain, lines=lines
    )
    body = "" if not lines else "\n".join(lines) + "\n"
    return Response(content=body, media_type="application/x-ndjson")


@router.get("/domains/{domain}")
def list_domain(
    request: Request,
    domain: PublicDomain,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    filter_fields: Annotated[
        list[str] | None,
        Query(alias="filter_field"),
    ] = None,
    filter_values: Annotated[
        list[str] | None,
        Query(alias="filter_value"),
    ] = None,
    sort: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    runtime: CanonicalV2AdminRuntime = Depends(get_canonical_v2_admin_runtime),
) -> object:
    if offset + limit > 10_000:
        raise _unprocessable("offset plus limit must not exceed 10000")
    pairs = _validated_pairs(
        domain=domain,
        fields=filter_fields,
        values=filter_values,
    )
    selected_sort = sort or _DEFAULT_SORT[domain]
    if selected_sort not in _SORTS[domain]:
        raise _unprocessable("sort field is not allowed for this domain")
    result = _runtime_call(
        lambda: runtime.list_domain(
            domain=domain,
            q=q,
            filters=pairs,
            sort=selected_sort,
            order=order,
            limit=limit,
            offset=offset,
        )
    )
    assert isinstance(result, dict)
    return apply_list_overlay(
        corrections_store_from(request),
        domain=domain,
        result=result,
        unfiltered_first_page=q is None and not pairs and offset == 0,
    )


@router.get("/domains/{domain}/{canonical_id}/related")
def get_related(
    domain: PublicDomain,
    canonical_id: Annotated[str, Path(min_length=1, max_length=200)],
    relation_type: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    runtime: CanonicalV2AdminRuntime = Depends(get_canonical_v2_admin_runtime),
) -> object:
    if relation_type != _RELATIONS[domain]:
        raise _unprocessable("relation type is not allowed for this domain")
    return _runtime_call(
        lambda: runtime.related(
            domain=domain,
            canonical_id=canonical_id,
            relation_type=relation_type,
            limit=limit,
        )
    )


@router.get("/domains/{domain}/{canonical_id}")
def get_detail(
    request: Request,
    domain: PublicDomain,
    canonical_id: Annotated[str, Path(min_length=1, max_length=200)],
    runtime: CanonicalV2AdminRuntime = Depends(get_canonical_v2_admin_runtime),
) -> object:
    detail = _runtime_call(
        lambda: runtime.detail(domain=domain, canonical_id=canonical_id)
    )
    if detail is None:
        # manual added records have no projection; serve them from the overlay
        manual = corrections_store_from(request)
        if manual is not None:
            row = manual.get_added_record(canonical_id)
            if row is not None and row.domain == domain:
                return manual_detail_item(row)
        raise HTTPException(status_code=404, detail="Canonical V2 object not found")
    assert isinstance(detail, dict)
    return apply_detail_overlay(
        corrections_store_from(request), domain=domain, detail=detail
    )


__all__ = ["router"]
