from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.deps import get_store
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

router = APIRouter(prefix="/api")


class DomainEnum(str, Enum):
    professor = "professor"
    company = "company"
    paper = "paper"
    patent = "patent"


class PaginatedResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


class UpdateRecordRequest(BaseModel):
    core_facts: dict[str, Any] | None = None
    summary_fields: dict[str, Any] | None = None
    quality_status: (
        Literal["ready", "needs_review", "low_confidence", "needs_enrichment"] | None
    ) = None


class RelatedResponse(BaseModel):
    papers: list[dict[str, Any]]
    patents: list[dict[str, Any]]
    companies: list[dict[str, Any]]


class FilterOptionsResponse(BaseModel):
    options: list[str]


@router.get("/{domain}", response_model=PaginatedResponse)
def list_domain(
    domain: DomainEnum,
    q: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = "display_name",
    sort_order: Literal["asc", "desc"] = "asc",
    filters: str = "",
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> PaginatedResponse:
    offset = (page - 1) * page_size

    parsed_filters: dict[str, Any] | None = None
    if filters:
        try:
            parsed_filters = json.loads(filters)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="Invalid filters JSON")

    try:
        items, total = store.list_domain_filtered(
            domain.value,
            query=q,
            filters=parsed_filters,
            offset=offset,
            limit=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid sort_by. Allowed: id, display_name",
        )
    return PaginatedResponse(
        items=[item.model_dump(mode="json") for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{domain}/filters/{field}", response_model=FilterOptionsResponse)
def get_filter_options(
    domain: DomainEnum,
    field: str,
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> FilterOptionsResponse:
    options = store.get_filter_options(domain.value, field)
    return FilterOptionsResponse(options=options)


@router.get("/{domain}/{object_id}")
def get_domain_object(
    domain: DomainEnum,
    object_id: str,
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> dict[str, Any]:
    obj = store.get_object(domain.value, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return obj.model_dump(mode="json")


@router.patch("/{domain}/{object_id}")
def update_domain_object(
    domain: DomainEnum,
    object_id: str,
    body: UpdateRecordRequest,
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> dict[str, Any]:
    obj = store.get_object(domain.value, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")

    updates: dict[str, Any] = {}
    if body.core_facts is not None:
        merged_facts = {**obj.core_facts, **body.core_facts}
        updates["core_facts"] = merged_facts
    if body.summary_fields is not None:
        merged_summaries = {**obj.summary_fields, **body.summary_fields}
        updates["summary_fields"] = merged_summaries
    if body.quality_status is not None:
        updates["quality_status"] = body.quality_status

    if updates:
        # Update display_name if name changed in core_facts
        if "core_facts" in updates:
            new_name = updates["core_facts"].get("name")
            if new_name and isinstance(new_name, str):
                updates["display_name"] = new_name

        patched = obj.model_copy(update=updates)
        store.update_object(patched)
        return patched.model_dump(mode="json")

    return obj.model_dump(mode="json")


@router.delete("/{domain}/{object_id}", status_code=204)
def delete_domain_object(
    domain: DomainEnum,
    object_id: str,
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> None:
    obj = store.get_object(domain.value, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    store.delete_objects([object_id])


@router.get("/{domain}/{object_id}/related", response_model=RelatedResponse)
def get_related_objects(
    domain: DomainEnum,
    object_id: str,
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> RelatedResponse:
    obj = store.get_object(domain.value, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")

    papers: list[dict[str, Any]] = []
    patents: list[dict[str, Any]] = []
    companies: list[dict[str, Any]] = []

    if domain.value == "professor":
        related_papers = store.get_related_objects(
            source_domain="professor",
            source_id=object_id,
            target_domain="paper",
            relation_type="professor_papers",
        )
        papers = [p.model_dump(mode="json") for p in related_papers]

        related_patents = store.get_related_objects(
            source_domain="professor",
            source_id=object_id,
            target_domain="patent",
            relation_type="professor_patents",
        )
        patents = [p.model_dump(mode="json") for p in related_patents]

    elif domain.value == "company":
        related_patents = store.get_related_objects(
            source_domain="company",
            source_id=object_id,
            target_domain="patent",
            relation_type="company_patents",
        )
        patents = [p.model_dump(mode="json") for p in related_patents]

    elif domain.value == "paper":
        related_professors = store.get_related_objects(
            source_domain="paper",
            source_id=object_id,
            target_domain="professor",
            relation_type="paper_professors",
        )
        papers = [p.model_dump(mode="json") for p in related_professors]

    elif domain.value == "patent":
        # Reverse lookup: find companies and professors linked to this patent
        company_ids = obj.core_facts.get("company_ids") or []
        for cid in company_ids:
            comp = store.get_object("company", cid)
            if comp:
                companies.append(comp.model_dump(mode="json"))

        professor_ids = obj.core_facts.get("professor_ids") or []
        for pid in professor_ids:
            prof = store.get_object("professor", pid)
            if prof:
                papers.append(prof.model_dump(mode="json"))

    return RelatedResponse(papers=papers, patents=patents, companies=companies)
