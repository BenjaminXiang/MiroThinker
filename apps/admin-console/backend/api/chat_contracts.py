"""Stable HTTP envelopes shared by the V2 chat route and legacy comparison code."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


TargetDomain = Literal["professor", "paper", "company", "patent"]


class ChatCitation(BaseModel):
    type: Literal["professor", "paper", "patent", "company"]
    id: str
    label: str
    url: str | None = None


class CandidateOption(BaseModel):
    id: str
    domain: TargetDomain
    label: str
    hint: str


class ClarificationPayload(BaseModel):
    prompt: str
    options: list[CandidateOption]
    default_id: str
    omitted: int = 0


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    entity_id_hint: str | None = None


class ChatResponse(BaseModel):
    query: str
    query_type: str
    answer_text: str
    citations: list[ChatCitation] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    clarification: ClarificationPayload | None = None
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    answer_style: Literal["template", "llm_synthesized"] = "template"
    citation_map: dict[str, str] = Field(default_factory=dict)
    suggested_followups: list[str] = Field(default_factory=list, max_length=5)


class ChatFeedbackRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    query_type: str = Field(..., min_length=1, max_length=120)
    answer_text: str = Field(..., min_length=1, max_length=8000)
    answer_style: Literal["template", "llm_synthesized"] = "template"
    citations: list[ChatCitation] = Field(default_factory=list, max_length=30)
    citation_map: dict[str, str] = Field(default_factory=dict)
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    feedback_type: str = Field(default="incorrect_answer", max_length=80)
    note: str | None = Field(default=None, max_length=1000)


class ChatFeedbackResponse(BaseModel):
    issue_id: str
    status: Literal["filed"]
    reported_at: datetime | None = None


class ChatSessionResetResponse(BaseModel):
    session_id: str


__all__ = [
    "CandidateOption",
    "ChatCitation",
    "ChatFeedbackRequest",
    "ChatFeedbackResponse",
    "ChatRequest",
    "ChatResponse",
    "ChatSessionResetResponse",
    "ClarificationPayload",
    "TargetDomain",
]
