"""Bounded read-only HTTP surface for the console's durable chat-gap ledger.

The build-line gap surface (``/api/canonical-v2/operations/gaps``) reads the
Postgres gap schemas, which the serving deployment does not have, so the feedback
a user files has no reader there. This module exposes the copy the console writes
to its own state directory — no Postgres, and nothing to configure beyond the
ledger directory every other console store already resolves.
"""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.storage.chat_gaps import open_chat_gap_store


router = APIRouter(prefix="/api/canonical-v2/admin")

LEDGER_UNAVAILABLE = "chat_gap_ledger_unavailable"


class ChatGapItem(BaseModel):
    signal_id: str
    session_id: str
    turn_id: str
    release_id: str
    feedback_type: str
    note: str | None
    query_trace_id: str | None
    answer_trace_id: str | None
    observed_at: str
    recorded_at: str


class ChatGapPage(BaseModel):
    """``total`` and ``counts`` describe the whole ledger, not the filtered page."""

    items: list[ChatGapItem]
    total: int
    counts: dict[str, int]


@router.get("/chat-gaps", response_model=ChatGapPage)
def list_chat_gaps(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    feedback_type: str | None = None,
) -> ChatGapPage:
    """List the filed signals newest first; an empty ledger is an empty page."""

    try:
        store = open_chat_gap_store()
    except (OSError, sqlite3.Error) as exc:
        # The ledger is the console's own file: an unusable state directory is a
        # deployment problem, not an unconfigured Postgres one.
        raise HTTPException(status_code=503, detail=LEDGER_UNAVAILABLE) from exc
    try:
        return ChatGapPage(
            items=store.list_recent(limit=limit, feedback_type=feedback_type),
            total=store.total(),
            counts=store.counts_by_type(),
        )
    finally:
        store.close()


__all__ = ["router"]
