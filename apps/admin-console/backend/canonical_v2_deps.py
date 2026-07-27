"""Dedicated lazy dependencies for the isolated Canonical V2 operations surface."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Any, cast

from fastapi import HTTPException, Request
from backend.services.canonical_v2_review import ReviewWorkspace
from backend.services.canonical_v2_chat import CanonicalV2ChatAdapter
from src.data_agents.canonical_v2.knowledge_gap_postgres import (
    KnowledgeGapConfigurationError,
    KnowledgeGapPersistenceError,
    create_postgres_knowledge_gap_operations,
)


_REQUIRED_ENV = (
    "CANONICAL_V2_DATABASE_URL",
    "CANONICAL_V2_EXPECTED_DATABASE",
    "CANONICAL_V2_TARGET_KIND",
    "CANONICAL_V2_BACKUP_GATE_ROOT",
)


class CanonicalV2OperationsConfigurationError(RuntimeError):
    """The independent V2 operations composition is not explicitly configured."""


def _configuration() -> tuple[str, str, str, Path]:
    values = tuple(os.environ.get(name) for name in _REQUIRED_ENV)
    if not all(value and value.strip() for value in values):
        raise CanonicalV2OperationsConfigurationError(
            "all dedicated Canonical V2 operations settings are required"
        )
    database_url, expected_database, target_kind, backup_gate_root = (
        cast(str, value) for value in values
    )
    return (
        database_url,
        expected_database,
        target_kind,
        Path(backup_gate_root),
    )


@lru_cache(maxsize=1)
def _compose_operations() -> Any:
    database_url, expected_database, target_kind, backup_gate_root = _configuration()
    return create_postgres_knowledge_gap_operations(
        database_url=database_url,
        expected_database=expected_database,
        target_kind=target_kind,
        backup_gate_root=backup_gate_root,
    )


def get_knowledge_gap_operations() -> Any:
    """Return the lazy V2 composition or one bounded unconfigured response."""

    try:
        return _compose_operations()
    except CanonicalV2OperationsConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Canonical V2 operations are not configured",
        ) from exc
    except (KnowledgeGapConfigurationError, KnowledgeGapPersistenceError) as exc:
        # This boundary intentionally does not echo URLs, credentials, SQL, or
        # nested storage errors into an operator-facing response.
        raise HTTPException(
            status_code=503,
            detail="Canonical V2 operations are unavailable",
        ) from exc


def get_canonical_v2_chat_adapter(request: Request) -> CanonicalV2ChatAdapter:
    """Return only the explicitly installed application-state chat adapter."""

    adapter = getattr(request.app.state, "canonical_v2_chat_adapter", None)
    if not isinstance(adapter, CanonicalV2ChatAdapter):
        raise HTTPException(
            status_code=503,
            detail="canonical_v2_chat_runtime_unavailable",
        )
    return adapter


def _candidate_runtime(request: Request) -> Any:
    from backend.services.canonical_v2_admin import (
        CanonicalV2ConsumerIntegrityError,
        require_canonical_v2_consumer_runtime,
    )

    value = getattr(request.app.state, "canonical_v2_consumer_runtime", None)
    try:
        return require_canonical_v2_consumer_runtime(value)
    except CanonicalV2ConsumerIntegrityError as exc:
        raise HTTPException(
            status_code=503,
            detail="canonical_v2_runtime_unavailable",
        ) from exc


def get_canonical_v2_admin_runtime(request: Request) -> Any:
    """Resolve only the exact aggregate-owned Admin member."""

    return _candidate_runtime(request).admin_runtime


def get_canonical_v2_gap_operations(request: Request) -> Any:
    """Resolve only the exact aggregate-owned Accepted S10O member."""

    return _candidate_runtime(request).gap_operations


def get_canonical_v2_candidate_chat_adapter(
    request: Request,
) -> CanonicalV2ChatAdapter:
    """Resolve only the exact aggregate-owned Accepted S11A member."""

    return _candidate_runtime(request).chat_adapter


def get_canonical_v2_review_workspace(request: Request) -> ReviewWorkspace:
    """Return only the explicitly installed SQLite review workspace."""

    workspace = getattr(request.app.state, "canonical_v2_review_workspace", None)
    if not isinstance(workspace, ReviewWorkspace):
        raise HTTPException(status_code=503, detail="review_workspace_unavailable")
    return workspace


__all__ = [
    "CanonicalV2OperationsConfigurationError",
    "get_canonical_v2_admin_runtime",
    "get_canonical_v2_candidate_chat_adapter",
    "get_canonical_v2_chat_adapter",
    "get_canonical_v2_gap_operations",
    "get_canonical_v2_review_workspace",
    "get_knowledge_gap_operations",
]
