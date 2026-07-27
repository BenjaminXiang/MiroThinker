"""Thin same-origin HTTP adapter for the Canonical V2 human review workspace."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Path, Query, Request, Response
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.canonical_v2_deps import get_canonical_v2_review_workspace
from backend.services.canonical_v2_review import (
    DraftData,
    ExportMode,
    ExportReceipt,
    ExportReview,
    ReadExport,
    OpenWorkspace,
    ReviewErrorCode,
    ReviewWorkspace,
    ReviewWorkspaceError,
    SaveDraft,
    SealCalibration,
    SealedWorkspaceView,
    SubmitDecision,
    TaskKind,
    WorkspaceView,
)


router = APIRouter(prefix="/api/review")

REVIEW_SESSION_COOKIE = "canonical_v2_review_session"
_VIEW_RESPONSE = WorkspaceView | SealedWorkspaceView
_REVIEW_API_PREFIX = "/api/review/"


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OpenReviewSessionRequest(_StrictRequest):
    display_name: str = Field(min_length=1, max_length=128)
    staff_id: str = Field(min_length=2, max_length=64)


class SubmitReviewDecisionRequest(_StrictRequest):
    task_id: str = Field(min_length=1, max_length=256)
    task_kind: TaskKind
    decision: str = Field(min_length=1, max_length=64)
    rationale: str | None = Field(default=None, max_length=10_000)
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)


class SealReviewCalibrationRequest(_StrictRequest):
    expected_revision: Literal[60]
    idempotency_key: str = Field(min_length=1, max_length=128)


class CreateReviewExportRequest(_StrictRequest):
    mode: ExportMode
    idempotency_key: str = Field(min_length=1, max_length=128)


_ERROR_STATUS = {
    ReviewErrorCode.ARTIFACT_MISMATCH: 503,
    ReviewErrorCode.INVALID_REVIEWER: 422,
    ReviewErrorCode.INVALID_SESSION: 401,
    ReviewErrorCode.UNKNOWN_TASK: 404,
    ReviewErrorCode.STALE_REVISION: 409,
    ReviewErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ReviewErrorCode.INVALID_DECISION: 422,
    ReviewErrorCode.INVALID_COMMAND: 422,
    ReviewErrorCode.JUDGE_UNAVAILABLE: 503,
    ReviewErrorCode.JUDGE_RECOVERY_REQUIRED: 409,
    ReviewErrorCode.CALIBRATION_NOT_SEALED: 409,
    ReviewErrorCode.EXPORT_BLOCKED: 409,
    ReviewErrorCode.STORAGE_FAILURE: 503,
}


def review_error_response(
    *,
    status_code: int,
    code: str,
    current_revision: int | None = None,
) -> JSONResponse:
    payload: dict[str, str | int] = {"code": code}
    if current_revision is not None:
        payload["current_revision"] = current_revision
    return JSONResponse(status_code=status_code, content=payload)


def review_origin_is_exact(request: Request, *, expected_origin: str) -> bool:
    origins = [
        value.decode("latin-1")
        for name, value in request.scope.get("headers", ())
        if name.lower() == b"origin"
    ]
    return origins == [expected_origin]


async def review_workspace_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del request
    if not isinstance(exc, ReviewWorkspaceError):
        raise exc
    return review_error_response(
        status_code=_ERROR_STATUS[exc.code],
        code=exc.code.value,
        current_revision=exc.current_revision,
    )


async def review_validation_error_handler(
    request: Request,
    exc: Exception,
) -> Response:
    if not isinstance(exc, RequestValidationError):
        raise exc
    if request.url.path.startswith(_REVIEW_API_PREFIX):
        return review_error_response(status_code=422, code="invalid_request")
    return await request_validation_exception_handler(request, exc)


async def review_http_exception_handler(
    request: Request,
    exc: Exception,
) -> Response:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    if request.url.path.startswith(_REVIEW_API_PREFIX) and isinstance(exc.detail, str):
        return review_error_response(status_code=exc.status_code, code=exc.detail)
    return await http_exception_handler(request, exc)


def _session_token(
    token: Annotated[
        str | None,
        Cookie(alias=REVIEW_SESSION_COOKIE, max_length=512),
    ] = None,
) -> str:
    if token is None:
        raise HTTPException(status_code=401, detail=ReviewErrorCode.INVALID_SESSION.value)
    return token


@router.post(
    "/sessions",
    response_model=_VIEW_RESPONSE,
    response_model_exclude={"session_token"},
)
def open_review_session(
    payload: OpenReviewSessionRequest,
    response: Response,
    request: Request,
    workspace: ReviewWorkspace = Depends(get_canonical_v2_review_workspace),
) -> WorkspaceView | SealedWorkspaceView:
    view = workspace.open(
        OpenWorkspace(display_name=payload.display_name, staff_id=payload.staff_id)
    )
    token = view.session_token
    if token is None:
        raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
    response.set_cookie(
        REVIEW_SESSION_COOKIE,
        token,
        secure=bool(request.app.state.canonical_v2_review_secure_cookie),
        httponly=True,
        samesite="strict",
        path="/api/review",
    )
    return view


@router.get(
    "/workspace",
    response_model=_VIEW_RESPONSE,
    response_model_exclude={"session_token"},
)
def get_review_workspace(
    task_id: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
    token: str = Depends(_session_token),
    workspace: ReviewWorkspace = Depends(get_canonical_v2_review_workspace),
) -> WorkspaceView | SealedWorkspaceView:
    return workspace.open(OpenWorkspace(session_token=token, task_id=task_id))


@router.put(
    "/drafts/{task_id}",
    response_model=_VIEW_RESPONSE,
    response_model_exclude={"session_token"},
)
def save_review_draft(
    task_id: Annotated[str, Path(min_length=1, max_length=256)],
    payload: DraftData,
    token: str = Depends(_session_token),
    workspace: ReviewWorkspace = Depends(get_canonical_v2_review_workspace),
) -> WorkspaceView | SealedWorkspaceView:
    return workspace.record(
        SaveDraft(session_token=token, task_id=task_id, draft=payload)
    )


@router.post(
    "/decisions",
    response_model=_VIEW_RESPONSE,
    response_model_exclude={"session_token"},
)
def submit_review_decision(
    payload: SubmitReviewDecisionRequest,
    token: str = Depends(_session_token),
    workspace: ReviewWorkspace = Depends(get_canonical_v2_review_workspace),
) -> WorkspaceView | SealedWorkspaceView:
    return workspace.record(
        SubmitDecision(
            session_token=token,
            task_id=payload.task_id,
            task_kind=payload.task_kind,
            decision=payload.decision,
            rationale=payload.rationale,
            expected_revision=payload.expected_revision,
            idempotency_key=payload.idempotency_key,
        )
    )


@router.post(
    "/calibration/seal",
    response_model=SealedWorkspaceView,
    response_model_exclude={"session_token"},
)
def seal_review_calibration(
    payload: SealReviewCalibrationRequest,
    token: str = Depends(_session_token),
    workspace: ReviewWorkspace = Depends(get_canonical_v2_review_workspace),
) -> SealedWorkspaceView:
    view = workspace.record(
        SealCalibration(
            session_token=token,
            expected_revision=payload.expected_revision,
            idempotency_key=payload.idempotency_key,
        )
    )
    if not isinstance(view, SealedWorkspaceView):
        raise ReviewWorkspaceError(ReviewErrorCode.STORAGE_FAILURE)
    return view


@router.post("/exports", response_model=ExportReceipt)
def create_review_export(
    payload: CreateReviewExportRequest,
    token: str = Depends(_session_token),
    workspace: ReviewWorkspace = Depends(get_canonical_v2_review_workspace),
) -> ExportReceipt:
    return workspace.export(
        ExportReview(
            session_token=token,
            mode=payload.mode,
            idempotency_key=payload.idempotency_key,
        )
    )


@router.get("/exports/{export_id}")
def download_review_export(
    export_id: Annotated[
        str,
        Path(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
    ],
    token: str = Depends(_session_token),
    workspace: ReviewWorkspace = Depends(get_canonical_v2_review_workspace),
) -> Response:
    download = workspace.read_export(
        ReadExport(session_token=token, export_id=export_id)
    )
    return Response(
        content=download.content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{download.receipt.basename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


__all__ = [
    "REVIEW_SESSION_COOKIE",
    "review_error_response",
    "review_http_exception_handler",
    "review_origin_is_exact",
    "review_validation_error_handler",
    "review_workspace_error_handler",
    "router",
]
