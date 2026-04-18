"""Pydantic models for the Source Layer tables (V001).

Mirrors `alembic/versions/V001_init_source_layer.py`. See plan 005 §6.1.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .common import RunKind, RunStatus, SeedKind


class SeedRegistry(BaseModel):
    """One row of `seed_registry`."""

    model_config = ConfigDict(extra="forbid")

    seed_id: str
    seed_kind: SeedKind
    scope_key: str
    source_uri: str
    priority: int = 100
    refresh_policy: str  # enum validated by DB CHECK; keep loose in Python for now
    status: str = "active"
    last_processed_at: datetime | None = None
    config: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ImportBatch(BaseModel):
    """One row of `import_batch`."""

    model_config = ConfigDict(extra="forbid")

    batch_id: UUID | None = None
    seed_id: str
    source_file: str
    file_content_hash: str
    started_at: datetime
    finished_at: datetime | None = None
    rows_read: int | None = None
    records_parsed: int | None = None
    records_new: int | None = None
    records_updated: int | None = None
    records_merged: int | None = None
    records_failed: int | None = None
    run_status: RunStatus
    error_summary: dict[str, Any] | None = None
    triggered_by: str | None = None


class SourceRowLineage(BaseModel):
    """One row of `source_row_lineage`."""

    model_config = ConfigDict(extra="forbid")

    lineage_id: UUID | None = None
    batch_id: UUID
    source_row_number: int
    target_entity_type: str
    target_entity_id: str | None = None
    resolution_status: str
    resolution_reason: str | None = None
    raw_row_jsonb: dict[str, Any]
    created_at: datetime | None = None


class SourcePage(BaseModel):
    """One row of `source_page`. `url_host` is DB-computed; read-only from Python."""

    model_config = ConfigDict(extra="forbid")

    page_id: UUID | None = None
    url: str
    url_host: str | None = Field(default=None, description="DB GENERATED; do not set")
    page_role: str
    owner_scope_kind: str | None = None
    owner_scope_ref: str | None = None
    fetched_at: datetime
    http_status: int | None = None
    content_hash: str | None = None
    title: str | None = None
    clean_text_path: str | None = None
    is_official_source: bool = False
    fetch_run_id: UUID | None = None
    created_at: datetime | None = None


class PipelineRun(BaseModel):
    """One row of `pipeline_run`."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID | None = None
    run_kind: RunKind
    run_scope: dict[str, Any]
    seed_id: str | None = None
    parent_run_id: UUID | None = None
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    items_processed: int | None = None
    items_failed: int | None = None
    error_summary: dict[str, Any] | None = None
    triggered_by: str | None = None
    created_at: datetime | None = None


__all__ = [
    "ImportBatch",
    "PipelineRun",
    "SeedRegistry",
    "SourcePage",
    "SourceRowLineage",
    "date",  # re-export just to keep imports tidy
]
