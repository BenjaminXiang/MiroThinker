from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.deps import get_store
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

router = APIRouter(prefix="/api")


class DomainStats(BaseModel):
    name: str
    count: int
    quality: dict[str, int]


class DashboardResponse(BaseModel):
    domains: list[DomainStats]


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    store: SqliteReleasedObjectStore = Depends(get_store),
) -> DashboardResponse:
    counts = store.count_by_domain()
    domain_names = ["professor", "company", "paper", "patent"]
    domains = []
    for name in domain_names:
        count = counts.get(name, 0)
        quality = store.quality_breakdown(name) if count > 0 else {}
        domains.append(DomainStats(name=name, count=count, quality=quality))
    return DashboardResponse(domains=domains)
